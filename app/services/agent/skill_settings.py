"""Packaged agent skill registry and namespace-scoped skill overrides."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.prompt_settings import MAX_AGENT_PROMPT_CHARACTERS
from app.services.agent.skills import SEARCH_NOTES_SKILL


SEARCH_NOTES_SKILL_ID = "search_notes"
SEARCH_NOTES_SKILL_PREFERENCE_KEY = "pref.ai.skill.search_notes"
AGENT_SKILL_PREFERENCE_KEYS = (SEARCH_NOTES_SKILL_PREFERENCE_KEY,)


@dataclass(frozen=True, slots=True)
class AgentSkill:
    skill_id: str
    title: str
    description: str
    trigger_action: str
    preference_key: str
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.skill_id, str) or self.skill_id == "":
            raise ValueError("Agent skill id must be non-empty")
        if not isinstance(self.title, str) or self.title == "":
            raise ValueError("Agent skill title must be non-empty")
        if not isinstance(self.description, str) or self.description == "":
            raise ValueError("Agent skill description must be non-empty")
        if not isinstance(self.trigger_action, str) or self.trigger_action == "":
            raise ValueError("Agent skill trigger action must be non-empty")
        if not isinstance(self.preference_key, str) or self.preference_key == "":
            raise ValueError("Agent skill preference key must be non-empty")
        validate_agent_skill_content(self.content)


@dataclass(frozen=True, slots=True)
class AgentSkillSet:
    skills: tuple[AgentSkill, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.skills, tuple) or len(self.skills) == 0:
            raise ValueError("Agent skill set must contain at least one skill")
        skill_ids = [skill.skill_id for skill in self.skills]
        if len(set(skill_ids)) != len(skill_ids):
            raise ValueError("Agent skill ids must be unique")
        trigger_actions = [skill.trigger_action for skill in self.skills]
        if len(set(trigger_actions)) != len(trigger_actions):
            raise ValueError("Agent skill trigger actions must be unique")

    def for_action(self, action_kind: str) -> AgentSkill:
        if not isinstance(action_kind, str) or action_kind == "":
            raise ValueError("Agent skill action kind must be non-empty")
        matching_skills = [
            skill for skill in self.skills if skill.trigger_action == action_kind
        ]
        if len(matching_skills) != 1:
            raise KeyError(f"Expected one agent skill for action {action_kind}")
        return matching_skills[0]


def validate_agent_skill_content(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Agent skill content must be a string")
    if value.strip() == "":
        raise ValueError("Agent skill content must not be blank")
    if len(value) > MAX_AGENT_PROMPT_CHARACTERS:
        raise ValueError(
            f"Agent skill content must not exceed {MAX_AGENT_PROMPT_CHARACTERS} characters"
        )
    return value


DEFAULT_AGENT_SKILLS = AgentSkillSet(
    skills=(
        AgentSkill(
            skill_id=SEARCH_NOTES_SKILL_ID,
            title="Search notes",
            description=(
                "Generates a focused query for search_notes, which returns complete "
                "matching note content."
            ),
            trigger_action="search_notes",
            preference_key=SEARCH_NOTES_SKILL_PREFERENCE_KEY,
            content=SEARCH_NOTES_SKILL,
        ),
    )
)


def resolve_agent_skill_set(*, preferences: dict[str, str]) -> AgentSkillSet:
    if not isinstance(preferences, dict):
        raise TypeError("Agent skill preferences must be a dictionary")
    resolved_skills: list[AgentSkill] = []
    for default_skill in DEFAULT_AGENT_SKILLS.skills:
        content = default_skill.content
        if default_skill.preference_key in preferences:
            content = preferences[default_skill.preference_key]
        resolved_skills.append(
            AgentSkill(
                skill_id=default_skill.skill_id,
                title=default_skill.title,
                description=default_skill.description,
                trigger_action=default_skill.trigger_action,
                preference_key=default_skill.preference_key,
                content=content,
            )
        )
    return AgentSkillSet(skills=tuple(resolved_skills))
