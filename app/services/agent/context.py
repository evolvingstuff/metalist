"""Build exact model contexts without polluting canonical conversation history."""

from __future__ import annotations

import json

from app.services.agent.actions import AgentAction
from app.services.agent.actions import RespondAction
from app.services.agent.prompt_settings import AgentPromptSet
from app.services.agent.skill_settings import AgentSkill
from app.services.agent.tools import ToolExecutionResult


class AgentContextBuilder:
    def build_initial_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
    ) -> list[dict[str, str]]:
        self._validate_canonical_messages(canonical_messages)
        return [
            {"role": "system", "content": prompts.system_prompt},
            *[dict(message) for message in canonical_messages],
        ]

    def activate_skill(
        self,
        *,
        messages: list[dict[str, str]],
        skill: AgentSkill,
    ) -> list[dict[str, str]]:
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError("Skill activation requires an existing agent context")
        if messages[0].get("role") != "system":
            raise ValueError("Skill activation requires the base system prompt first")
        skill_message = (
            f"ACTIVE_SKILL {skill.skill_id}\n"
            f"Trigger action: {skill.trigger_action}\n\n"
            f"{skill.content}"
        )
        return [
            dict(messages[0]),
            {"role": "system", "content": skill_message},
            *[dict(message) for message in messages[1:]],
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
        prompts: AgentPromptSet,
    ) -> list[dict[str, str]]:
        payload_json = json.dumps(result.payload, sort_keys=True, separators=(",", ":"))
        content = prompts.render_tool_result(
            action_name=result.action_name,
            payload_json=payload_json,
        )
        return [*messages, {"role": "user", "content": content}]

    def append_final_request(
        self,
        *,
        messages: list[dict[str, str]],
        action: RespondAction,
        prompts: AgentPromptSet,
    ) -> list[dict[str, str]]:
        with_action = self.append_action(messages=messages, action=action)
        content = prompts.render_final_response_request(basis=action.basis)
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
