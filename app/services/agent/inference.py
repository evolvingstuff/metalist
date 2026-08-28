"""Provider-neutral inference contracts owned by MetaList."""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class InferenceAttempt:
    request: dict[str, object]
    response: dict[str, object]
    error: str
    duration_ms: float


@dataclass(frozen=True, slots=True)
class InferenceResponse:
    content: str
    thinking: str
    usage: dict[str, int]
    attempts: list[InferenceAttempt]


@dataclass(frozen=True, slots=True)
class StructuredInferenceProgress:
    phase: str
    attempt: int
    max_attempts: int
    failure_kind: str
    error_type: str
    error_message: str
    duration_ms: float
    wire_request: dict[str, object]


class StructuredInferenceError(RuntimeError):
    def __init__(self, *, attempts: list[InferenceAttempt]) -> None:
        assert attempts, "Structured inference failure must contain at least one attempt"
        attempt_count = len(attempts)
        if attempt_count == 1:
            attempt_summary = "1 attempt"
        else:
            attempt_summary = f"{attempt_count} attempts"
        super().__init__(
            f"Ollama could not produce a valid agent action after {attempt_summary}. "
            "Open Agent Debug for exact request and response details."
        )
        self.attempts = list(attempts)


class InferenceAdapter(Protocol):
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
        ...

    def stream_text(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
        on_request: Callable[[dict[str, object]], None],
    ) -> AsyncIterator[dict[str, object]]:
        ...
