import asyncio
import json

import httpx
import pytest

from app.services.ai_chat import AiChatActivityTimer
from app.services.ai_chat import AiChatSessionStore
from app.services.ollama_provider import OllamaProvider
from app.services.ollama_provider import OllamaProviderError
from app.services.ollama_provider import OllamaModelContext
from app.services.ollama_provider import normalize_ollama_base_url
from app.services.ollama_provider import resolve_ollama_think_value


def test_chat_history_is_scoped_to_server_session_key() -> None:
    store = AiChatSessionStore()

    first_turn = store.start_turn(
        session_key="session-a",
        user_content="What is 2 + 2?",
        provider="ollama",
        model="qwen3:latest",
    )
    store.append_delta(
        session_key="session-a",
        turn_id=first_turn,
        delta_kind="thinking",
        text="I should add the numbers.",
    )
    store.append_delta(
        session_key="session-a",
        turn_id=first_turn,
        delta_kind="content",
        text="4",
    )
    store.append_activity(
        session_key="session-a",
        turn_id=first_turn,
        action="model_request",
        status="started",
        label="Waiting for Ollama",
        approx_input_tokens=1_234,
        output_tokens_received=0,
        duration_ms=1_250.5,
    )
    store.complete_turn(
        session_key="session-a",
        turn_id=first_turn,
        final_content="4",
    )

    session_a = store.snapshot(session_key="session-a")
    session_b = store.snapshot(session_key="session-b")

    assert [message["role"] for message in session_a["messages"]] == ["user", "assistant"]
    assert session_a["messages"][1]["thinking"] == "I should add the numbers."
    assert session_a["messages"][1]["content"] == "4"
    assert session_a["messages"][1]["status"] == "complete"
    assert session_a["messages"][1]["activities"] == [
        {
            "action": "model_request",
            "status": "started",
            "label": "Waiting for Ollama",
            "approx_input_tokens": 1_234,
            "output_tokens_received": 0,
            "duration_ms": 1_250.5,
        }
    ]
    assert session_a["messages"][0]["activities"] == []
    assert session_b == {"messages": []}


def test_chat_store_builds_ollama_history_without_thinking_trace() -> None:
    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-a",
        user_content="Hello",
        provider="ollama",
        model="qwen3:latest",
    )
    store.append_delta(
        session_key="session-a",
        turn_id=turn_id,
        delta_kind="thinking",
        text="Private chain",
    )
    store.append_delta(
        session_key="session-a",
        turn_id=turn_id,
        delta_kind="content",
        text="Hi there",
    )
    store.append_activity(
        session_key="session-a",
        turn_id=turn_id,
        action="retry",
        status="started",
        label="Structured output invalid (ValidationError) · Instructor will retry",
        approx_input_tokens=1_567,
        output_tokens_received=0,
        duration_ms=250.0,
    )
    store.complete_turn(
        session_key="session-a",
        turn_id=turn_id,
        final_content="Hi there",
    )

    history = store.provider_messages(session_key="session-a")

    assert history == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]


def test_activity_timer_retains_completed_step_duration() -> None:
    timer = AiChatActivityTimer()
    started = timer.stamp(
        event={
            "action": "search_notes",
            "status": "started",
            "label": "Searching notes",
            "duration_ms": 0.0,
        },
        observed_at=10.0,
    )
    completed = timer.stamp(
        event={
            "action": "search_notes",
            "status": "completed",
            "label": "Search complete",
            "duration_ms": 0.0,
        },
        observed_at=11.75,
    )

    assert started["duration_ms"] == 0.0
    assert completed["duration_ms"] == 1_750.0


def test_activity_timer_preserves_authoritative_model_duration() -> None:
    timer = AiChatActivityTimer()
    event = timer.stamp(
        event={
            "action": "validation",
            "status": "completed",
            "label": "Structured action validated",
            "duration_ms": 2_778.334,
        },
        observed_at=10.0,
    )

    assert event["duration_ms"] == 2_778.334


def test_chat_store_removes_prior_note_citations_from_provider_history() -> None:
    note_id = "75193dae-9e05-4a4e-94bf-417ffde18957"
    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-a",
        user_content="Summarize my testosterone notes",
        provider="ollama",
        model="qwen3:latest",
    )
    store.append_delta(
        session_key="session-a",
        turn_id=turn_id,
        delta_kind="content",
        text=f"Sleep can affect testosterone. [[{note_id}]]",
    )
    store.complete_turn(
        session_key="session-a",
        turn_id=turn_id,
        final_content=f"Sleep can affect testosterone. [[{note_id}]]",
    )
    store.start_turn(
        session_key="session-a",
        user_content="Please describe Bayes' theorem briefly",
        provider="ollama",
        model="qwen3:latest",
    )

    history = store.provider_messages(session_key="session-a")

    assert history == [
        {"role": "user", "content": "Summarize my testosterone notes"},
        {"role": "assistant", "content": "Sleep can affect testosterone."},
        {"role": "user", "content": "Please describe Bayes' theorem briefly"},
    ]


def test_chat_store_excludes_failed_turn_from_later_provider_context() -> None:
    store = AiChatSessionStore()
    failed_turn_id = store.start_turn(
        session_key="session-a",
        user_content="This request failed",
        provider="ollama",
        model="qwen3:latest",
    )
    store.fail_turn(
        session_key="session-a",
        turn_id=failed_turn_id,
        error="Ollama disconnected",
    )
    store.start_turn(
        session_key="session-a",
        user_content="Try something else",
        provider="ollama",
        model="qwen3:latest",
    )

    history = store.provider_messages(session_key="session-a")

    assert history == [{"role": "user", "content": "Try something else"}]


def test_chat_store_rejects_parallel_turns_in_one_session() -> None:
    store = AiChatSessionStore()
    store.start_turn(
        session_key="session-a",
        user_content="First",
        provider="ollama",
        model="qwen3:latest",
    )

    with pytest.raises(RuntimeError, match="already streaming"):
        store.start_turn(
            session_key="session-a",
            user_content="Second",
            provider="ollama",
            model="qwen3:latest",
        )


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://localhost:11434/", "http://127.0.0.1:11434"),
        ("http://127.0.0.1:11434/api", "http://127.0.0.1:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
    ],
)
def test_ollama_base_url_accepts_only_explicit_loopback_hosts(base_url, expected) -> None:
    assert normalize_ollama_base_url(base_url) == expected


@pytest.mark.parametrize(
    "base_url",
    [
        "http://ollama.internal:11434",
        "http://192.168.1.10:11434",
        "http://127.0.0.2:11434",
        "http://localhost:0",
    ],
)
def test_ollama_base_url_rejects_non_loopback_or_invalid_hosts(base_url) -> None:
    with pytest.raises(ValueError):
        normalize_ollama_base_url(base_url)


def test_ollama_provider_lists_models_from_configured_host() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://127.0.0.1:11434/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3:8b", "model": "qwen3:8b"},
                    {"name": "gemma3:latest", "model": "gemma3:latest"},
                ]
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    models = asyncio.run(provider.list_models(base_url="http://127.0.0.1:11434"))

    assert models == ["gemma3:latest", "qwen3:8b"]


def test_ollama_provider_preloads_model_and_reports_active_context() -> None:
    requested_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/api/show":
            assert request.method == "POST"
            assert json.loads(request.content) == {"model": "qwen2.5:7b-instruct"}
            return httpx.Response(
                200,
                json={
                    "model_info": {
                        "qwen2.context_length": 32768,
                        "qwen2.embedding_length": 3584,
                    }
                },
            )
        if request.url.path == "/api/generate":
            assert request.method == "POST"
            assert json.loads(request.content) == {
                "model": "qwen2.5:7b-instruct",
                "stream": False,
            }
            return httpx.Response(200, json={"done": True, "response": ""})
        assert request.url.path == "/api/ps"
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen2.5:7b-instruct",
                        "model": "qwen2.5:7b-instruct",
                        "context_length": 4096,
                    }
                ]
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    model_context = asyncio.run(
        provider.inspect_model_context(
            base_url="http://127.0.0.1:11434",
            model="qwen2.5:7b-instruct",
        )
    )

    assert model_context == OllamaModelContext(
        model="qwen2.5:7b-instruct",
        maximum_tokens=32768,
        loaded_tokens=4096,
    )
    assert requested_urls == [
        "http://127.0.0.1:11434/api/show",
        "http://127.0.0.1:11434/api/generate",
        "http://127.0.0.1:11434/api/ps",
    ]


def test_ollama_provider_streams_model_pull_progress() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://127.0.0.1:11434/api/pull"
        assert json.loads(request.content) == {
            "model": "gemma3:4b",
            "stream": True,
            "insecure": False,
        }
        return httpx.Response(
            200,
            headers={"content-type": "application/x-ndjson"},
            content=(
                b'{"status":"pulling manifest"}\n'
                b'{"status":"pulling layer","total":100,"completed":25}\n'
                b'{"status":"success"}\n'
            ),
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    async def collect_events() -> list[dict[str, object]]:
        return [
            event
            async for event in provider.stream_pull(
                base_url="http://127.0.0.1:11434",
                model="gemma3:4b",
            )
        ]

    events = asyncio.run(collect_events())

    assert events == [
        {
            "type": "progress",
            "status": "pulling manifest",
            "completed": 0,
            "total": 0,
        },
        {
            "type": "progress",
            "status": "pulling layer",
            "completed": 25,
            "total": 100,
        },
        {
            "type": "done",
            "status": "success",
            "completed": 100,
            "total": 100,
        },
    ]


def test_ollama_provider_streams_thinking_and_content_separately() -> None:
    wire_requests: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(request.content)
        assert payload == {
            "model": "qwen3:8b",
            "messages": [{"role": "user", "content": "Count to two"}],
                "stream": True,
                "think": "low",
                "options": {"num_predict": 4_096},
            }
        return httpx.Response(
            200,
            headers={"content-type": "application/x-ndjson"},
            content=(
                b'{"message":{"role":"assistant","thinking":"One"},"done":false}\n'
                b'{"message":{"role":"assistant","thinking":", two"},"done":false}\n'
                b'{"message":{"role":"assistant","content":"1, 2"},"done":false}\n'
                b'{"message":{"role":"assistant","content":"!"},"done":true,'
                b'"prompt_eval_count":23,"eval_count":8}\n'
            ),
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    async def collect_chunks() -> list[dict[str, str]]:
        return [
            chunk
            async for chunk in provider.stream_chat(
                base_url="http://127.0.0.1:11434",
                model="qwen3:8b",
                thinking_level="low",
                messages=[{"role": "user", "content": "Count to two"}],
                max_output_tokens=4_096,
                on_request=wire_requests.append,
            )
        ]

    chunks = asyncio.run(collect_chunks())

    assert wire_requests == [
        {
            "method": "POST",
            "url": "http://127.0.0.1:11434/api/chat",
            "body": {
                "model": "qwen3:8b",
                "messages": [{"role": "user", "content": "Count to two"}],
                    "stream": True,
                    "think": "low",
                    "options": {"num_predict": 4_096},
                },
        }
    ]
    assert chunks == [
        {"type": "thinking_delta", "text": "One"},
        {"type": "thinking_delta", "text": ", two"},
        {"type": "content_delta", "text": "1, 2"},
        {"type": "content_delta", "text": "!"},
        {"type": "done", "usage": {"prompt_eval_count": 23, "eval_count": 8}},
    ]


def test_ollama_provider_preserves_http_error_detail_for_debugging() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        return httpx.Response(
            400,
            headers={"content-type": "application/json"},
            json={"error": "model rejected the chat template"},
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))

    async def collect_chunks() -> list[dict[str, object]]:
        return [
            chunk
            async for chunk in provider.stream_chat(
                base_url="http://127.0.0.1:11434",
                model="qwen2.5:7b-instruct",
                thinking_level="off",
                messages=[{"role": "user", "content": "Hello"}],
                max_output_tokens=4_096,
                on_request=lambda request: None,
            )
        ]

    with pytest.raises(
        OllamaProviderError,
        match=(
            "Ollama chat request failed with HTTP 400: "
            "model rejected the chat template"
        ),
    ):
        asyncio.run(collect_chunks())


def test_gpt_oss_requests_medium_thinking_level() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["think"] == "medium"
        return httpx.Response(
            200,
            headers={"content-type": "application/x-ndjson"},
            content=b'{"message":{"role":"assistant","content":"ok"},"done":true}\n',
        )

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    async def collect_chunks() -> list[dict[str, str]]:
        return [
            chunk
            async for chunk in provider.stream_chat(
                base_url="http://127.0.0.1:11434",
                model="gpt-oss:20b",
                thinking_level="medium",
                messages=[{"role": "user", "content": "Hello"}],
                max_output_tokens=4_096,
                on_request=lambda request: None,
            )
        ]

    chunks = asyncio.run(collect_chunks())

    assert chunks[-1] == {"type": "done"}


@pytest.mark.parametrize(
    ("thinking_level", "expected"),
    [
        ("off", False),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
    ],
)
def test_ollama_thinking_level_maps_to_native_api_value(thinking_level, expected) -> None:
    assert resolve_ollama_think_value(
        model="qwen3:8b",
        thinking_level=thinking_level,
    ) == expected


def test_gpt_oss_rejects_disabled_thinking() -> None:
    with pytest.raises(ValueError, match="does not support disabling thinking"):
        resolve_ollama_think_value(
            model="gpt-oss:20b",
            thinking_level="off",
        )
