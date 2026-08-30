"""OpenAI inference adapter using Instructor for typed output."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from collections.abc import Callable
from typing import cast

import httpx
import instructor
from openai import APIError
from openai import AsyncOpenAI
from pydantic import BaseModel

from instructor.v2.core.client import AsyncInstructor

from app.services.agent.inference import InferenceContextWindow
from app.services.agent.inference import InferenceProviderError
from app.services.agent.inference import InferenceResponse
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.inference import TARGET_AGENT_CONTEXT_TOKENS
from app.services.agent.ollama_inference import _InstructorTraceCapture
from app.services.agent.ollama_inference import _attach_trace_capture
from app.services.agent.ollama_inference import _create_structured_completion
from app.services.agent.ollama_inference import _extract_reasoning
from app.services.agent.ollama_inference import _extract_usage
from app.services.agent.ollama_inference import _json_object
from app.services.agent.ollama_inference import _structured_max_output_tokens


OPENAI_API_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL_CONTEXT_TOKENS = 1_050_000
OPENAI_MODELS = (
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)


class OpenAIProviderError(InferenceProviderError):
    """Expected OpenAI API or transport failure."""


def validate_openai_model(model: str) -> str:
    if not isinstance(model, str):
        raise TypeError("OpenAI model must be text")
    normalized = model.strip()
    if normalized not in OPENAI_MODELS:
        raise ValueError(f"Unsupported OpenAI model: {model}")
    return normalized


def resolve_openai_reasoning_effort(thinking_level: str) -> str:
    mapping = {
        "off": "none",
        "low": "low",
        "medium": "medium",
        "high": "high",
    }
    if thinking_level not in mapping:
        raise ValueError(f"Unsupported OpenAI thinking level: {thinking_level}")
    return mapping[thinking_level]


def _validate_base_url(base_url: str) -> None:
    if base_url != OPENAI_API_BASE_URL:
        raise ValueError("OpenAI inference requires the official API base URL")


def _create_instructor_client(
    *,
    api_key: str,
    model: str,
    capture: _InstructorTraceCapture,
) -> AsyncInstructor:
    http_client = httpx.AsyncClient(
        event_hooks={"request": [capture.record_wire_request]},
        follow_redirects=False,
        trust_env=False,
    )
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url=OPENAI_API_BASE_URL,
        http_client=http_client,
        max_retries=0,
    )
    return cast(
        AsyncInstructor,
        instructor.from_openai(
            openai_client,
            model=model,
            mode=instructor.Mode.JSON_SCHEMA,
        ),
    )


def _provider_error_message(exc: APIError) -> str:
    detail = " ".join(str(exc).split())
    if detail == "":
        return "OpenAI API request failed"
    return f"OpenAI API request failed: {detail[:500]}"


class OpenAIInferenceAdapter:
    def __init__(self, *, api_key: str) -> None:
        if not isinstance(api_key, str) or api_key == "":
            raise ValueError("OpenAI inference requires an API key")
        self._api_key = api_key

    @property
    def provider_label(self) -> str:
        return "OpenAI"

    async def inspect_context_window(
        self,
        *,
        base_url: str,
        model: str,
    ) -> InferenceContextWindow:
        _validate_base_url(base_url)
        normalized_model = validate_openai_model(model)
        return InferenceContextWindow(
            model=normalized_model,
            maximum_tokens=OPENAI_MODEL_CONTEXT_TOKENS,
            loaded_tokens=OPENAI_MODEL_CONTEXT_TOKENS,
            required_tokens=TARGET_AGENT_CONTEXT_TOKENS,
        )

    async def infer_structured(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        on_progress: Callable[[StructuredInferenceProgress], None],
    ) -> InferenceResponse:
        _validate_base_url(base_url)
        normalized_model = validate_openai_model(model)
        reasoning_effort = resolve_openai_reasoning_effort(thinking_level)
        capture = _InstructorTraceCapture(on_progress=on_progress)
        client = _create_instructor_client(
            api_key=self._api_key,
            model=normalized_model,
            capture=capture,
        )
        _attach_trace_capture(client=client, capture=capture)
        # lint: allow-PY001 rationale="OpenAI API and transport failures are external provider failures"
        try:
            parsed, raw_completion = await _create_structured_completion(
                client=client,
                capture=capture,
                response_model=response_model,
                messages=messages,
                request_options={
                    "max_completion_tokens": _structured_max_output_tokens(response_model),
                    "reasoning_effort": reasoning_effort,
                    "store": False,
                },
            )
        # lint: allow-PY001 rationale="translate external OpenAI API failures into the provider-neutral contract"
        except APIError as exc:
            raise OpenAIProviderError(_provider_error_message(exc)) from exc
        if not isinstance(parsed, response_model):
            raise TypeError("Instructor returned the wrong structured response type")
        capture.record_success()
        raw_response = _json_object(raw_completion)
        attempts = capture.freeze()
        if len(attempts) == 0:
            raise RuntimeError("Instructor returned without recording an inference attempt")
        return InferenceResponse(
            content=parsed.model_dump_json(),
            thinking=_extract_reasoning(raw_response),
            usage=_extract_usage(raw_response),
            attempts=attempts,
        )

    async def stream_text(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
        on_request: Callable[[dict[str, object]], None],
    ) -> AsyncIterator[dict[str, object]]:
        _validate_base_url(base_url)
        normalized_model = validate_openai_model(model)
        reasoning_effort = resolve_openai_reasoning_effort(thinking_level)
        if (
            not isinstance(max_output_tokens, int)
            or isinstance(max_output_tokens, bool)
            or max_output_tokens < 1
        ):
            raise ValueError("OpenAI maximum output tokens must be positive")

        async def capture_wire_request(request: httpx.Request) -> None:
            raw_body = await request.aread()
            body = json.loads(raw_body)
            if not isinstance(body, dict):
                raise TypeError("OpenAI wire request body must be an object")
            on_request(
                {
                    "method": request.method,
                    "url": str(request.url),
                    "body": body,
                }
            )

        http_client = httpx.AsyncClient(
            event_hooks={"request": [capture_wire_request]},
            follow_redirects=False,
            trust_env=False,
        )
        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=OPENAI_API_BASE_URL,
            http_client=http_client,
            max_retries=0,
        )
        did_finish = False
        # lint: allow-PY001 rationale="OpenAI streaming and transport failures are external provider failures"
        try:
            stream = await client.chat.completions.create(
                model=normalized_model,
                messages=cast(object, messages),
                reasoning_effort=cast(object, reasoning_effort),
                max_completion_tokens=max_output_tokens,
                stream=True,
                stream_options={"include_usage": True},
                store=False,
            )
            async for chunk in stream:
                if chunk.usage is not None:
                    usage_payload = chunk.usage.model_dump()
                    usage: dict[str, int] = {}
                    for field_name in (
                        "prompt_tokens",
                        "completion_tokens",
                        "total_tokens",
                    ):
                        if field_name not in usage_payload:
                            continue
                        value = usage_payload[field_name]
                        if not isinstance(value, int):
                            raise TypeError(
                                f"OpenAI usage {field_name} must be an integer"
                            )
                        usage[field_name] = value
                    yield {"type": "done", "usage": usage}
                    did_finish = True
                    continue
                for choice in chunk.choices:
                    content = choice.delta.content
                    if content is not None and content != "":
                        yield {"type": "content_delta", "text": content}
        # lint: allow-PY001 rationale="translate external OpenAI stream failures into the provider-neutral contract"
        except APIError as exc:
            raise OpenAIProviderError(_provider_error_message(exc)) from exc
        finally:
            await client.close()
        if not did_finish:
            raise OpenAIProviderError("OpenAI response stream ended before completion")
