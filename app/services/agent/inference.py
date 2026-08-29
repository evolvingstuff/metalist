"""Provider-neutral inference contracts owned by MetaList."""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


MINIMUM_AGENT_CONTEXT_TOKENS = 16_384
TARGET_AGENT_CONTEXT_TOKENS = 32_768


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
class InferenceContextWindow:
    model: str
    maximum_tokens: int
    loaded_tokens: int
    required_tokens: int

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or self.model.strip() == "":
            raise ValueError("Inference context model must be non-empty")
        for label, value in (
            ("maximum_tokens", self.maximum_tokens),
            ("loaded_tokens", self.loaded_tokens),
            ("required_tokens", self.required_tokens),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Inference context {label} must be positive")

    @property
    def is_sufficient(self) -> bool:
        return self.loaded_tokens >= self.required_tokens


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
            f"Ollama could not produce a valid structured response after {attempt_summary}. "
            "Open Agent Debug for exact request and response details."
        )
        self.attempts = list(attempts)


class InferenceAdapter(Protocol):
    async def inspect_context_window(
        self,
        *,
        base_url: str,
        model: str,
    ) -> InferenceContextWindow:
        ...

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
