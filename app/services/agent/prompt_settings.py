"""Packaged agent prompts. Prompts are not user-editable."""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from app.services.agent.prompts import AGENT_SYSTEM_PROMPT
from app.services.agent.prompts import FINAL_RESPONSE_REQUEST_PROMPT
from app.services.agent.prompts import TOOL_RESULT_PROMPT


# Prompts used to be editable per namespace. They no longer are, so every user
# gets the behavior the evals measure; saved overrides under these keys are
# ignored and dropped (see client_state_service).
RETIRED_PROMPT_PREFERENCE_KEYS = (
    "pref.ai.prompt.system",
    "pref.ai.prompt.final_response",
    "pref.ai.prompt.tool_result",
)
MAX_AGENT_PROMPT_CHARACTERS = 32_000


@dataclass(frozen=True, slots=True)
class AgentPromptSet:
    system_prompt: str
    final_response_prompt: str
    tool_result_prompt: str

    def __post_init__(self) -> None:
        validate_system_prompt(self.system_prompt)
        validate_final_response_prompt(self.final_response_prompt)
        validate_tool_result_prompt(self.tool_result_prompt)

    def render_final_response_request(self, *, basis: str) -> str:
        assert isinstance(basis, str) and basis != ""
        return self.final_response_prompt.format(basis=basis)

    def render_tool_result(self, *, action_name: str, payload_json: str) -> str:
        assert isinstance(action_name, str) and action_name != ""
        assert isinstance(payload_json, str) and payload_json != ""
        return self.tool_result_prompt.format(
            action_name=action_name,
            payload_json=payload_json,
        )


def validate_system_prompt(value: str) -> str:
    return _validate_prompt_text(label="System prompt", value=value)


def validate_final_response_prompt(value: str) -> str:
    normalized = _validate_prompt_text(label="Final-response prompt", value=value)
    _validate_template_fields(
        label="Final-response prompt",
        value=normalized,
        required_fields=("basis",),
    )
    return normalized


def validate_tool_result_prompt(value: str) -> str:
    normalized = _validate_prompt_text(label="Tool-result prompt", value=value)
    _validate_template_fields(
        label="Tool-result prompt",
        value=normalized,
        required_fields=("action_name", "payload_json"),
    )
    return normalized


def _validate_prompt_text(*, label: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if value.strip() == "":
        raise ValueError(f"{label} must not be blank")
    if len(value) > MAX_AGENT_PROMPT_CHARACTERS:
        raise ValueError(
            f"{label} must not exceed {MAX_AGENT_PROMPT_CHARACTERS} characters"
        )
    return value


def _validate_template_fields(
    *,
    label: str,
    value: str,
    required_fields: tuple[str, ...],
) -> None:
    parsed_fields: list[str] = []
    for _, field_name, format_spec, conversion in Formatter().parse(value):
        if field_name is None:
            continue
        if field_name not in required_fields:
            raise ValueError(f"{label} has unsupported placeholder: {field_name}")
        if format_spec != "" or conversion is not None:
            raise ValueError(f"{label} placeholders cannot use formatting modifiers")
        parsed_fields.append(field_name)
    for required_field in required_fields:
        if parsed_fields.count(required_field) != 1:
            raise ValueError(
                f"{label} must contain exactly one {{{required_field}}} placeholder"
            )


DEFAULT_AGENT_PROMPTS = AgentPromptSet(
    system_prompt=AGENT_SYSTEM_PROMPT,
    final_response_prompt=FINAL_RESPONSE_REQUEST_PROMPT,
    tool_result_prompt=TOOL_RESULT_PROMPT,
)
