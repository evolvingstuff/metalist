import pytest
from pydantic import BaseModel, Field

from app.services.agent.tool_calling import AgentTool
from app.services.agent.tool_calling import estimate_tool_conversation_tokens
from app.services.agent.tool_calling import validate_tool_conversation


class _HelpArguments(BaseModel):
    topics: list[str] = Field(..., description="Help topic ids")


def _conversation() -> list[dict[str, object]]:
    return [
        {"role": "system", "content": "You are MetaList's assistant."},
        {"role": "user", "content": "What's new in 0.11.0?"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call-1", "name": "lookup_metalist_help", "arguments": '{"topics":["data"]}'},
        ]},
        {"role": "tool", "tool_call_id": "call-1", "name": "lookup_metalist_help", "content": "Release notes…"},
        {"role": "assistant", "content": "0.11.0 makes large namespaces faster."},
    ]


def test_a_tool_needs_a_snake_case_name_a_description_and_only_required_arguments() -> None:
    tool = AgentTool(name="lookup_metalist_help", description="Look up MetaList help.", arguments_model=_HelpArguments)
    assert tool.arguments_schema()["required"] == ["topics"]

    with pytest.raises(ValueError):
        AgentTool(name="Lookup Help", description="x", arguments_model=_HelpArguments)
    with pytest.raises(ValueError):
        AgentTool(name="lookup", description=" ", arguments_model=_HelpArguments)

    class OptionalArguments(BaseModel):
        query: str
        limit: int = 10

    # An optional argument would let the schema accept calls the tool cannot
    # describe precisely; every argument must be required.
    with pytest.raises(ValueError, match="must be required"):
        AgentTool(name="search", description="Search.", arguments_model=OptionalArguments)


def test_a_well_formed_tool_conversation_is_accepted_and_estimated() -> None:
    conversation = _conversation()
    validate_tool_conversation(conversation)
    assert estimate_tool_conversation_tokens(conversation) > estimate_tool_conversation_tokens(conversation[:2])


def test_malformed_tool_conversations_fail_fast() -> None:
    orphan_result = _conversation()
    orphan_result[3] = {**orphan_result[3], "tool_call_id": "call-unknown"}
    with pytest.raises(ValueError, match="no pending tool call"):
        validate_tool_conversation(orphan_result)

    bad_call = _conversation()
    bad_call[2] = {"role": "assistant", "content": "", "tool_calls": [{"id": "call-1", "name": "", "arguments": "{}"}]}
    with pytest.raises(ValueError):
        validate_tool_conversation(bad_call)

    with pytest.raises(ValueError):
        validate_tool_conversation([{"role": "user", "content": "Hi", "extra": 1}])
    with pytest.raises(ValueError):
        validate_tool_conversation([{"role": "robot", "content": "Hi"}])
    with pytest.raises(ValueError):
        validate_tool_conversation([])


def test_an_assistant_message_may_carry_opaque_provider_state() -> None:
    conversation = _conversation()
    conversation[2] = {**conversation[2], "provider_state": {"provider": "openai", "items": [{"type": "reasoning"}]}}
    validate_tool_conversation(conversation)

    conversation[2] = {**conversation[2], "provider_state": {"items": []}}
    with pytest.raises(ValueError):
        validate_tool_conversation(conversation)
