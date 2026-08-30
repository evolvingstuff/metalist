"""Packaged agent skill registry and namespace-scoped skill overrides."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.prompt_settings import MAX_AGENT_PROMPT_CHARACTERS
from app.services.agent.skills import SCOPED_INVESTIGATION_SKILL


SCOPED_INVESTIGATION_SKILL_ID = "scoped_investigation_v5"
SCOPED_INVESTIGATION_SKILL_PREFERENCE_KEY = (
    "pref.ai.skill.scoped_investigation_v5"
)
LEGACY_SELECT_RELEVANT_EVIDENCE_SKILL_PREFERENCE_KEY = (
    "pref.ai.skill.select_relevant_evidence_v1"
)
LEGACY_SCOPED_INVESTIGATION_V4_PREFERENCE_KEY = (
    "pref.ai.skill.scoped_investigation_v4"
)
LEGACY_SCOPED_INVESTIGATION_V3_PREFERENCE_KEY = (
    "pref.ai.skill.scoped_investigation_v3"
)
LEGACY_SCOPED_INVESTIGATION_V2_PREFERENCE_KEY = (
    "pref.ai.skill.scoped_investigation_v2"
)
LEGACY_SEARCH_NOTES_SKILL_PREFERENCE_KEY = "pref.ai.skill.search_notes"
AGENT_SKILL_PREFERENCE_KEYS = (
    SCOPED_INVESTIGATION_SKILL_PREFERENCE_KEY,
)
SUPERSEDED_AGENT_SKILL_PREFERENCE_KEYS = (
    LEGACY_SELECT_RELEVANT_EVIDENCE_SKILL_PREFERENCE_KEY,
    LEGACY_SCOPED_INVESTIGATION_V4_PREFERENCE_KEY,
    LEGACY_SCOPED_INVESTIGATION_V3_PREFERENCE_KEY,
    LEGACY_SCOPED_INVESTIGATION_V2_PREFERENCE_KEY,
    LEGACY_SEARCH_NOTES_SKILL_PREFERENCE_KEY,
)


@dataclass(frozen=True, slots=True)
class AgentSkill:
    skill_id: str
    title: str
    description: str
    trigger_action: str
    preference_key: str
    content: str
    superseded_preference_keys: tuple[str, ...] = ()

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
        if any(
            not isinstance(key, str) or key == ""
            for key in self.superseded_preference_keys
        ):
            raise ValueError("Superseded skill preference keys must be non-empty")
        if len(set(self.superseded_preference_keys)) != len(
            self.superseded_preference_keys
        ):
            raise ValueError("Superseded skill preference keys must be unique")


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
            skill_id=SCOPED_INVESTIGATION_SKILL_ID,
            title="Investigate current scope",
            description=(
                "Pages, refines, summarizes, and verifies evidence only inside the "
                "frozen active MetaList result scope."
            ),
            trigger_action="investigate_current_scope",
            preference_key=SCOPED_INVESTIGATION_SKILL_PREFERENCE_KEY,
            content=SCOPED_INVESTIGATION_SKILL,
            superseded_preference_keys=(
                *SUPERSEDED_AGENT_SKILL_PREFERENCE_KEYS,
            ),
        ),
    )
)


def resolve_agent_skill_set(*, preferences: dict[str, str]) -> AgentSkillSet:
    if not isinstance(preferences, dict):
        raise TypeError("Agent skill preferences must be a dictionary")
    if any(
        key in preferences for key in SUPERSEDED_AGENT_SKILL_PREFERENCE_KEYS
    ):
        raise ValueError(
            "Saved skill override is incompatible with the nested scoped "
            "investigation v5 action contract. Open AI Agent Settings to review "
            "and restore the new default."
        )
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
                superseded_preference_keys=default_skill.superseded_preference_keys,
            )
        )
    return AgentSkillSet(skills=tuple(resolved_skills))
