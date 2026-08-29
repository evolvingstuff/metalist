import pytest

from app.services.agent.prompt_settings import AgentPromptSet
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.prompt_settings import FINAL_RESPONSE_PROMPT_PREFERENCE_KEY
from app.services.agent.prompt_settings import SYSTEM_PROMPT_PREFERENCE_KEY
from app.services.agent.prompt_settings import TOOL_RESULT_PROMPT_PREFERENCE_KEY
from app.services.agent.prompt_settings import resolve_agent_prompt_set


def test_packaged_agent_prompts_are_valid_and_renderable() -> None:
    assert DEFAULT_AGENT_PROMPTS.system_prompt != ""
    assert DEFAULT_AGENT_PROMPTS.render_final_response_request(
        basis="Use the retrieved note.",
    ).startswith("FINAL_RESPONSE_REQUEST\nStructured basis: Use the retrieved note.")
    assert DEFAULT_AGENT_PROMPTS.render_tool_result(
        action_name="search_notes",
        payload_json='{"notes":[]}',
    ) == 'TOOL_RESULT search_notes\n{"notes":[]}'


def test_resolve_agent_prompt_set_uses_namespace_overrides() -> None:
    prompts = resolve_agent_prompt_set(
        preferences={
            SYSTEM_PROMPT_PREFERENCE_KEY: "Custom system prompt",
            FINAL_RESPONSE_PROMPT_PREFERENCE_KEY: "FINAL {basis}",
            TOOL_RESULT_PROMPT_PREFERENCE_KEY: "TOOL {action_name}\n{payload_json}",
        }
    )

    assert prompts.system_prompt == "Custom system prompt"
    assert prompts.render_final_response_request(basis="basis") == "FINAL basis"
    assert prompts.render_tool_result(
        action_name="read_notes",
        payload_json='{"notes":[]}',
    ) == 'TOOL read_notes\n{"notes":[]}'


@pytest.mark.parametrize(
    ("final_response_prompt", "error"),
    [
        ("No placeholder", "exactly one {basis}"),
        ("{basis} and {basis}", "exactly one {basis}"),
        ("{basis} {unknown}", "unsupported placeholder: unknown"),
        ("{basis!r}", "formatting modifiers"),
    ],
)
def test_agent_prompt_set_rejects_invalid_final_response_template(
    final_response_prompt: str,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        AgentPromptSet(
            system_prompt="System",
            final_response_prompt=final_response_prompt,
            tool_result_prompt="{action_name}\n{payload_json}",
        )


@pytest.mark.parametrize(
    "tool_result_prompt",
    [
        "{action_name}",
        "{payload_json}",
        "{action_name} {payload_json} {extra}",
        "{action_name:>10} {payload_json}",
    ],
)
def test_agent_prompt_set_rejects_invalid_tool_result_template(
    tool_result_prompt: str,
) -> None:
    with pytest.raises(ValueError):
        AgentPromptSet(
            system_prompt="System",
            final_response_prompt="{basis}",
            tool_result_prompt=tool_result_prompt,
        )


def test_agent_prompt_set_rejects_blank_and_oversized_prompts() -> None:
    with pytest.raises(ValueError, match="System prompt must not be blank"):
        AgentPromptSet(
            system_prompt="  ",
            final_response_prompt="{basis}",
            tool_result_prompt="{action_name}\n{payload_json}",
        )
    with pytest.raises(ValueError, match="must not exceed 32000"):
        AgentPromptSet(
            system_prompt="x" * 32_001,
            final_response_prompt="{basis}",
            tool_result_prompt="{action_name}\n{payload_json}",
        )
