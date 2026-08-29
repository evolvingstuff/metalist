import pytest

from app.services.agent.prompt_settings import AgentPromptSet
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.prompt_settings import FINAL_RESPONSE_PROMPT_PREFERENCE_KEY
from app.services.agent.prompt_settings import SYSTEM_PROMPT_PREFERENCE_KEY
from app.services.agent.prompt_settings import TOOL_RESULT_PROMPT_PREFERENCE_KEY
from app.services.agent.prompt_settings import resolve_agent_prompt_set


def test_packaged_agent_prompts_are_valid_and_renderable() -> None:
    assert DEFAULT_AGENT_PROMPTS.system_prompt != ""
    normalized_system_prompt = " ".join(DEFAULT_AGENT_PROMPTS.system_prompt.split())
    assert "Prefer Markdown for final answers" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "LaTeX math delimiters" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "Mermaid code blocks" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "one bounded page" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "A broad synthesis is not complete merely because one page was read" in (
        normalized_system_prompt
    )
    assert "Reducing the result count" in normalized_system_prompt
    assert "is not by itself a reason to search again" in normalized_system_prompt
    assert "Never describe a retrieved subset as all matching notes" in (
        normalized_system_prompt
    )
    assert "read_notes_by_id" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "bypass retrieval limits" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "Never read or summarize an" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "gray search-redaction bars" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "Search the note index" in normalized_system_prompt
    assert "Every search_notes TOOL_RESULT is content-bearing" in (
        DEFAULT_AGENT_PROMPTS.system_prompt
    )
    assert "notes[].content_text" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "do not substitute general knowledge" in (
        DEFAULT_AGENT_PROMPTS.final_response_prompt.casefold()
    )
    assert "copy its exact `note_id` value from the relevant TOOL_RESULT" in (
        DEFAULT_AGENT_PROMPTS.system_prompt
    )
    assert "quoted preview of that specific" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert "group the clickable References section by top-level root note" in (
        normalized_system_prompt
    )
    assert "Citations are current-run evidence only" in normalized_system_prompt
    assert "Never reuse note IDs or citations from earlier turns" in (
        normalized_system_prompt
    )
    assert "the current run did not retrieve any notes" in normalized_system_prompt
    assert "Do not write" in normalized_system_prompt
    assert "your own References heading or list" in DEFAULT_AGENT_PROMPTS.system_prompt
    assert DEFAULT_AGENT_PROMPTS.render_final_response_request(
        basis="Use the retrieved note.",
    ).startswith("FINAL_RESPONSE_REQUEST\nStructured basis: Use the retrieved note.")
    assert "Never invent or imitate a UUID" in (
        DEFAULT_AGENT_PROMPTS.final_response_prompt
    )
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
        action_name="read_notes_by_id",
        payload_json='{"notes":[]}',
    ) == 'TOOL read_notes_by_id\n{"notes":[]}'


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
