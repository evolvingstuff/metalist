import asyncio
from types import SimpleNamespace

import httpx
import instructor
from openai import AsyncOpenAI

from app.services.agent.actions import AgentRouteEnvelope
from app.services.agent.actions import SearchQueryEnvelope
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.ollama_inference import OllamaInferenceAdapter
from app.services.agent.ollama_inference import _response_finish_reason
from app.services.agent.ollama_inference import _structured_max_output_tokens


def test_structured_output_limits_are_bounded_by_response_type() -> None:
    assert _structured_max_output_tokens(AgentRouteEnvelope) == 512
    assert _structured_max_output_tokens(SearchQueryEnvelope) == 1_024


def test_structured_retry_can_identify_output_limit_truncation() -> None:
    response = {
        "choices": [
            {
                "message": {"role": "assistant", "content": '{"partial":'},
                "finish_reason": "length",
            }
        ]
    }

    assert _response_finish_reason(response) == "length"


class FakeInstructorClient:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.create_kwargs: dict[str, object] = {}
        self.client = SimpleNamespace(close=self.close)
        self.is_closed = False
        self.http_clients: list[httpx.AsyncClient] = []
        self.wire_request_hooks = []

    async def close(self) -> None:
        self.is_closed = True
        for http_client in self.http_clients:
            await http_client.aclose()

    def on(self, event_name: str, handler) -> None:
        self.handlers[event_name] = handler

    async def create_partial(self, **kwargs):
        self.create_kwargs = kwargs
        request_handler = self.handlers["completion:kwargs"]
        response_handler = self.handlers["completion:response"]
        request_handler(
            model="qwen2.5:7b-instruct",
            messages=kwargs["messages"],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "AgentRouteEnvelope",
                    "schema": AgentRouteEnvelope.model_json_schema(),
                },
            },
            extra_body=kwargs["extra_body"],
            max_tokens=kwargs["max_tokens"],
            temperature=kwargs["temperature"],
        )
        assert len(self.wire_request_hooks) == 1
        wire_request = httpx.Request(
            "POST",
            "http://127.0.0.1:11434/v1/chat/completions",
            json={
                "model": "qwen2.5:7b-instruct",
                "messages": kwargs["messages"],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "AgentRouteEnvelope",
                        "schema": AgentRouteEnvelope.model_json_schema(),
                    },
                },
                "stream": True,
                "temperature": kwargs["temperature"],
                "max_tokens": kwargs["max_tokens"],
                "think": kwargs["extra_body"]["think"],
            },
        )
        await self.wire_request_hooks[0](wire_request)
        response_chunks = [
            SimpleNamespace(
                model_dump=lambda **options: {
                "id": "chatcmpl-action",
                "model": "qwen2.5:7b-instruct",
                "choices": [
                    {
                        "delta": {
                            "content": (
                                '{"kind":"respond","note_ids":[],'
                                '"reason":"Reply to the greeting."}'
                            ),
                            "reasoning": "A greeting needs no note tools.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 31,
                    "completion_tokens": 8,
                    "total_tokens": 39,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
                }
            )
        ]

        async def chunk_iterator():
            for chunk in response_chunks:
                yield chunk

        class FakeStream:
            def __init__(self) -> None:
                self._iterator = chunk_iterator()

            def __aiter__(self):
                return self._iterator

        stream = FakeStream()
        response_handler(stream)
        async for _chunk in stream:
            pass
        response_model = kwargs["response_model"]
        yield response_model(
            kind="respond",
            note_ids=[],
            reason="Reply to the greeting.",
        )


def test_structured_inference_uses_instructor_ollama_and_captures_exact_attempt(
    monkeypatch,
) -> None:
    fake_client = FakeInstructorClient()
    factory_call: dict[str, object] = {}

    def fake_from_openai(openai_client: AsyncOpenAI, **kwargs):
        factory_call.update({"openai_client": openai_client, **kwargs})
        http_client = openai_client._client
        assert isinstance(http_client, httpx.AsyncClient)
        fake_client.http_clients.append(http_client)
        fake_client.wire_request_hooks = http_client.event_hooks["request"]
        return fake_client

    monkeypatch.setattr(instructor, "from_openai", fake_from_openai)
    adapter = OllamaInferenceAdapter(provider=SimpleNamespace())
    progress_events: list[StructuredInferenceProgress] = []

    response = asyncio.run(
        adapter.infer_structured(
            base_url="http://localhost:11434",
            model="qwen2.5:7b-instruct",
            thinking_level="off",
            messages=[
                {"role": "system", "content": "Choose one action."},
                {"role": "user", "content": "Are you there?"},
            ],
            response_model=AgentRouteEnvelope,
            on_progress=progress_events.append,
        )
    )

    openai_client = factory_call["openai_client"]
    assert isinstance(openai_client, AsyncOpenAI)
    assert str(openai_client.base_url) == "http://127.0.0.1:11434/v1/"
    assert openai_client.max_retries == 0
    assert factory_call["model"] == "qwen2.5:7b-instruct"
    assert factory_call["mode"] is instructor.Mode.JSON_SCHEMA
    assert fake_client.create_kwargs["response_model"] is AgentRouteEnvelope
    assert fake_client.create_kwargs["max_retries"] == 0
    assert fake_client.create_kwargs["max_tokens"] == 512
    assert fake_client.create_kwargs["extra_body"] == {"think": False}
    assert fake_client.create_kwargs["temperature"] == 0
    assert fake_client.is_closed is True
    assert response.content == (
        '{"kind":"respond","note_ids":[],'
        '"reason":"Reply to the greeting."}'
    )
    assert response.thinking == "A greeting needs no note tools."
    assert response.usage == {
        "prompt_tokens": 31,
        "completion_tokens": 8,
        "total_tokens": 39,
    }
    assert len(response.attempts) == 1
    assert response.attempts[0].request["model"] == "qwen2.5:7b-instruct"
    assert response.attempts[0].response["id"] == "chatcmpl-action"
    assert response.attempts[0].error == ""
    assert [progress.phase for progress in progress_events] == [
        "attempt_started",
        "output_progress",
        "response_received",
        "attempt_succeeded",
    ]
    assert progress_events[1].output_tokens_received > 0
    assert progress_events[-1].output_tokens_received > 0
    assert all(progress.attempt == 1 for progress in progress_events)
    assert all(progress.max_attempts == 2 for progress in progress_events)
    wire_request = progress_events[0].wire_request
    assert wire_request["method"] == "POST"
    assert wire_request["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert wire_request["body"]["think"] is False
    assert wire_request["body"]["max_tokens"] == 512
    assert wire_request["body"]["messages"][1] == {
        "role": "user",
        "content": "Are you there?",
    }
    assert wire_request["body"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "AgentRouteEnvelope",
            "schema": AgentRouteEnvelope.model_json_schema(),
        },
    }
    assert "extra_body" not in wire_request["body"]
