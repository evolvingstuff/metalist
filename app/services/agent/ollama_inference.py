"""Instructor for typed Ollama output; direct Ollama for streamed prose."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import httpx
import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from instructor.v2.core.client import AsyncInstructor
from instructor.v2.core.errors import InstructorRetryException

from app.services.agent.inference import InferenceAttempt
from app.services.agent.inference import InferenceResponse
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.inference import StructuredInferenceError
from app.services.ollama_provider import OllamaProvider
from app.services.ollama_provider import normalize_ollama_base_url
from app.services.ollama_provider import resolve_ollama_think_value


_STRUCTURED_MAX_RETRIES = 1
_STRUCTURED_TIMEOUT_SECONDS = 300.0


@dataclass(slots=True)
class _PendingAttempt:
    request: dict[str, object]
    wire_request: dict[str, object]
    response: dict[str, object]
    error: str
    started_at: float
    duration_ms: float


class _InstructorTraceCapture:
    def __init__(
        self,
        *,
        on_progress: Callable[[StructuredInferenceProgress], None],
    ) -> None:
        self._attempts: list[_PendingAttempt] = []
        self._on_progress = on_progress

    def record_request(self, **kwargs: object) -> None:
        self._attempts.append(
            _PendingAttempt(
                request=_json_object(kwargs),
                wire_request={},
                response={},
                error="",
                started_at=time.perf_counter(),
                duration_ms=0.0,
            )
        )

    async def record_wire_request(self, request: httpx.Request) -> None:
        attempt = self._current_attempt()
        if attempt.wire_request:
            raise RuntimeError("Instructor emitted multiple HTTP requests for one attempt")
        raw_body = await request.aread()
        body = json.loads(raw_body)
        if not isinstance(body, dict):
            raise TypeError("Instructor wire request body must be an object")
        attempt.wire_request = {
            "method": request.method,
            "url": str(request.url),
            "body": body,
        }
        self._emit_progress(
            phase="attempt_started",
            failure_kind="",
            error_type="",
            error_message="",
        )

    def record_response(self, response: object) -> None:
        attempt = self._current_attempt()
        if not attempt.wire_request:
            raise RuntimeError("Instructor response arrived before its HTTP request")
        attempt.response = _json_object(response)
        attempt.duration_ms = (time.perf_counter() - attempt.started_at) * 1_000
        self._emit_progress(
            phase="response_received",
            failure_kind="",
            error_type="",
            error_message="",
        )

    def record_completion_error(self, error: Exception, **metadata: object) -> None:
        del metadata
        self._record_error(error=error, failure_kind="Ollama request failed")

    def record_parse_error(self, error: Exception, **metadata: object) -> None:
        del metadata
        self._record_error(error=error, failure_kind="Structured output invalid")

    def record_success(self) -> None:
        attempt = self._current_attempt()
        if not attempt.wire_request:
            raise RuntimeError("Instructor success arrived before its HTTP request")
        if attempt.error != "":
            raise RuntimeError("Instructor reported success after an attempt error")
        self._emit_progress(
            phase="attempt_succeeded",
            failure_kind="",
            error_type="",
            error_message="",
        )

    def _record_error(self, *, error: Exception, failure_kind: str) -> None:
        attempt = self._current_attempt()
        error_type = type(error).__name__
        error_message = str(error)
        formatted_error = f"{error_type}: {error_message}"
        if attempt.error == formatted_error:
            return
        attempt.error = formatted_error
        attempt.duration_ms = (time.perf_counter() - attempt.started_at) * 1_000
        attempt_number = len(self._attempts)
        phase = "retrying"
        if attempt_number == self.max_attempts:
            phase = "attempt_failed"
        self._emit_progress(
            phase=phase,
            failure_kind=failure_kind,
            error_type=error_type,
            error_message=error_message,
        )

    def freeze(self) -> list[InferenceAttempt]:
        return [
            InferenceAttempt(
                request=attempt.request,
                response=attempt.response,
                error=attempt.error,
                duration_ms=attempt.duration_ms,
            )
            for attempt in self._attempts
        ]

    def _current_attempt(self) -> _PendingAttempt:
        if not self._attempts:
            raise RuntimeError("Instructor emitted an event before a request")
        return self._attempts[-1]

    @property
    def max_attempts(self) -> int:
        return _STRUCTURED_MAX_RETRIES + 1

    def _emit_progress(
        self,
        *,
        phase: str,
        failure_kind: str,
        error_type: str,
        error_message: str,
    ) -> None:
        attempt = self._current_attempt()
        if not attempt.wire_request:
            raise RuntimeError("Instructor progress has no HTTP wire request")
        self._on_progress(
            StructuredInferenceProgress(
                phase=phase,
                attempt=len(self._attempts),
                max_attempts=self.max_attempts,
                failure_kind=failure_kind,
                error_type=error_type,
                error_message=error_message,
                duration_ms=attempt.duration_ms,
                wire_request=dict(attempt.wire_request),
            )
        )


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(mode="json"))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_value(model_dump(mode="json"))
    if isinstance(value, dict):
        converted: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError("Instructor trace object keys must be strings")
            converted[key] = _json_value(nested_value)
        return converted
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(f"Instructor trace value is not JSON-compatible: {type(value)}")


def _json_object(value: object) -> dict[str, object]:
    converted = _json_value(value)
    if not isinstance(converted, dict):
        raise TypeError("Instructor trace payload must be an object")
    return converted


def _extract_usage(raw_response: dict[str, object]) -> dict[str, int]:
    if "usage" not in raw_response:
        return {}
    raw_usage = raw_response["usage"]
    if not isinstance(raw_usage, dict):
        raise TypeError("Instructor completion usage must be an object")
    usage: dict[str, int] = {}
    for field_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if field_name not in raw_usage:
            continue
        value = raw_usage[field_name]
        if not isinstance(value, int) or value < 0:
            raise TypeError(f"Instructor completion {field_name} must be a non-negative integer")
        usage[field_name] = value
    return usage


def _extract_reasoning(raw_response: dict[str, object]) -> str:
    choices: object = []
    if "choices" in raw_response:
        choices = raw_response["choices"]
    if not isinstance(choices, list) or len(choices) == 0:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise TypeError("Instructor completion choice must be an object")
    message: object = {}
    if "message" in first_choice:
        message = first_choice["message"]
    if not isinstance(message, dict):
        raise TypeError("Instructor completion message must be an object")
    for field_name in ("reasoning", "reasoning_content", "thinking"):
        value: object = ""
        if field_name in message:
            value = message[field_name]
        if value != "":
            if not isinstance(value, str):
                raise TypeError("Instructor completion reasoning must be a string")
            return value
    return ""


def _create_instructor_client(
    *,
    base_url: str,
    model: str,
    capture: _InstructorTraceCapture,
) -> AsyncInstructor:
    normalized_base_url = normalize_ollama_base_url(base_url)
    http_client = httpx.AsyncClient(
        event_hooks={"request": [capture.record_wire_request]},
        follow_redirects=False,
        trust_env=False,
    )
    openai_client = AsyncOpenAI(
        api_key="ollama",
        base_url=f"{normalized_base_url}/v1",
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


def _attach_trace_capture(
    *,
    client: AsyncInstructor,
    capture: _InstructorTraceCapture,
) -> None:
    client.on("completion:kwargs", capture.record_request)
    client.on("completion:response", capture.record_response)
    client.on("completion:error", capture.record_completion_error)
    client.on("parse:error", capture.record_parse_error)


async def _create_structured_completion(
    *,
    client: AsyncInstructor,
    capture: _InstructorTraceCapture,
    response_model: type[BaseModel],
    messages: list[dict[str, str]],
    think_value: bool | str,
) -> tuple[BaseModel, object]:
    # lint: allow-PY001 rationale="translate exhausted external Instructor retries while preserving exact attempt traces"
    try:
        return await client.create_with_completion(
            response_model=response_model,
            messages=messages,
            max_retries=_STRUCTURED_MAX_RETRIES,
            timeout=_STRUCTURED_TIMEOUT_SECONDS,
            stream=False,
            temperature=0,
            extra_body={"think": think_value},
        )
    except InstructorRetryException as exc:
        raise StructuredInferenceError(
            attempts=capture.freeze(),
        ) from exc
    finally:
        await client.client.close()


class OllamaInferenceAdapter:
    def __init__(self, *, provider: OllamaProvider) -> None:
        self._provider = provider

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
        think_value = resolve_ollama_think_value(
            model=model,
            thinking_level=thinking_level,
        )
        capture = _InstructorTraceCapture(
            on_progress=on_progress,
        )
        client = _create_instructor_client(
            base_url=base_url,
            model=model,
            capture=capture,
        )
        _attach_trace_capture(client=client, capture=capture)
        parsed, raw_completion = await _create_structured_completion(
            client=client,
            capture=capture,
            response_model=response_model,
            messages=messages,
            think_value=think_value,
        )
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
        on_request: Callable[[dict[str, object]], None],
    ) -> AsyncIterator[dict[str, object]]:
        async for event in self._provider.stream_chat(
            base_url=base_url,
            model=model,
            thinking_level=thinking_level,
            messages=messages,
            on_request=on_request,
        ):
            yield event
