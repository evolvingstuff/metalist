"""Packaged agent skill registry. Skills are not user-editable."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.prompt_settings import MAX_AGENT_PROMPT_CHARACTERS
from app.services.agent.skills import load_skill
from app.services.agent.help_catalog import HELP_TOPICS


WEB_BROWSING_SKILL_ID = "web_browsing_v1"
STAGED_SUMMARY_SKILL_ID = "staged_summary_v1"
TAG_PROPOSALS_SKILL_ID = "tag_proposals_v1"
# Skills used to be editable per namespace. They no longer are, so every user
# gets the behavior the evals measure; saved overrides under these keys are
# ignored and dropped (see client_state_service).
RETIRED_SKILL_PREFERENCE_KEYS = (
    "pref.ai.skill.scoped_investigation_v7",
    "pref.ai.skill.staged_summary_v1",
    "pref.ai.prompt.tagging",
    "pref.ai.skill.web_browsing_v1",
    *(f"pref.ai.skill.help_{topic}_v1" for topic in HELP_TOPICS),
    "pref.ai.skill.narrow_context_v1",
    "pref.ai.skill.scoped_investigation_v6",
    "pref.ai.skill.select_relevant_evidence_v1",
    "pref.ai.skill.scoped_investigation_v5",
    "pref.ai.skill.scoped_investigation_v4",
    "pref.ai.skill.scoped_investigation_v3",
    "pref.ai.skill.scoped_investigation_v2",
    "pref.ai.skill.search_notes",
)


@dataclass(frozen=True, slots=True)
class AgentSkill:
    skill_id: str
    title: str
    description: str
    trigger_action: str
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
            skill_id=STAGED_SUMMARY_SKILL_ID,
            title="Summarize complete scope",
            description=(
                "Summarizes every permitted root tree through verified evidence "
                "batches and a citation-preserving synthesis."
            ),
            trigger_action="summarize_current_scope",
            content=load_skill("staged-summary.md"),
        ),
        AgentSkill(
            skill_id=TAG_PROPOSALS_SKILL_ID,
            title="Suggest tags",
            description=(
                "Suggests classification tags for the visible notes through "
                "validated, evidence-bounded batches."
            ),
            trigger_action="tag_proposals",
            content=load_skill("tag-proposals.md"),
        ),
        AgentSkill(
            skill_id=WEB_BROWSING_SKILL_ID,
            title="Web browsing",
            description=(
                "Opens public pages and Google result pages within the selected "
                "web-access mode."
            ),
            trigger_action="web_browsing",
            content=load_skill("web-browsing.md"),
        ),
        *(AgentSkill(
            skill_id=f"help_{topic}_v1", title=title, description=description,
            trigger_action=f"help_{topic}",
            content=load_skill(f"help-{topic}.md"),
        ) for topic, (title, description) in HELP_TOPICS.items()),
    )
)
