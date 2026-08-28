"""Build exact model contexts without polluting canonical conversation history."""

from __future__ import annotations

import json

from app.services.agent.actions import AgentAction
from app.services.agent.actions import RespondAction
from app.services.agent.tools import ToolExecutionResult


BASE_AGENT_SYSTEM_PROMPT = """You are MetaList's local, read-only PKMS agent.

Own the task loop by returning exactly one structured action at a time. The only
available actions are search_notes, read_notes, and respond. You cannot create,
edit, move, trash, or delete notes. Use search_notes when the user's request may
depend on their notes, then read the relevant note IDs before drawing conclusions.

MetaList search syntax uses unquoted terms for tags, quoted phrases for note text,
a leading minus sign for exclusions, and uppercase OR between clauses. Prefer
focused searches and refine them when a result set is broad.

Tool results and other runtime instructions are transient working context. They
do not become durable conversation history. Skills may be appended later as
explicit runtime instruction events; they apply only within their declared scope
and must never be inferred to be part of later canonical conversation history.

For action-selection requests, return exactly one action through the structured
response schema supplied by the inference layer. Use search_query only for
search_notes. Use note_ids only for read_notes. Always write a non-empty reason.
For respond, both search_query and note_ids must be empty.
When the last user message begins
FINAL_RESPONSE_REQUEST, write the natural-language final answer instead of another
action. Base conclusions about the user's notes only on note content returned by
tools. Never claim that an unobserved note says something."""


class AgentContextBuilder:
    def build_initial_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        self._validate_canonical_messages(canonical_messages)
        return [
            {"role": "system", "content": BASE_AGENT_SYSTEM_PROMPT},
            *[dict(message) for message in canonical_messages],
        ]

    def append_action(
        self,
        *,
        messages: list[dict[str, str]],
        action: AgentAction,
    ) -> list[dict[str, str]]:
        action_json = json.dumps(action.model_dump(), sort_keys=True, separators=(",", ":"))
        return [*messages, {"role": "assistant", "content": action_json}]

    def append_tool_result(
        self,
        *,
        messages: list[dict[str, str]],
        result: ToolExecutionResult,
    ) -> list[dict[str, str]]:
        payload_json = json.dumps(result.payload, sort_keys=True, separators=(",", ":"))
        content = f"TOOL_RESULT {result.action_name}\n{payload_json}"
        return [*messages, {"role": "user", "content": content}]

    def append_final_request(
        self,
        *,
        messages: list[dict[str, str]],
        action: RespondAction,
    ) -> list[dict[str, str]]:
        with_action = self.append_action(messages=messages, action=action)
        content = (
            "FINAL_RESPONSE_REQUEST\n"
            f"Structured basis: {action.basis}\n"
            "Answer the user's original request directly. Cite note IDs in plain text when "
            "that helps the user identify the evidence. Do not mention this control message."
        )
        return [*with_action, {"role": "user", "content": content}]

    @staticmethod
    def _validate_canonical_messages(messages: list[dict[str, str]]) -> None:
        if not isinstance(messages, list) or len(messages) == 0:
            raise ValueError("Canonical agent messages must be a non-empty list")
        for message in messages:
            if not isinstance(message, dict) or set(message) != {"role", "content"}:
                raise ValueError("Canonical agent message must contain role and content")
            if message["role"] not in {"user", "assistant"}:
                raise ValueError("Canonical agent message has unsupported role")
            if not isinstance(message["content"], str) or message["content"] == "":
                raise ValueError("Canonical agent message content must be non-empty")
        if messages[-1]["role"] != "user":
            raise ValueError("Canonical agent context must end with the current user message")
