import pytest

from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.skill_settings import validate_agent_skill_content


def test_packaged_skills_are_the_ones_the_agent_uses() -> None:
    actions = [skill.trigger_action for skill in DEFAULT_AGENT_SKILLS.skills]
    assert actions[:3] == ["summarize_current_scope", "tag_proposals", "web_browsing"]
    assert all(action.startswith("help_") for action in actions[3:])
    # The single-payload investigation skill went away with up-front routing.
    with pytest.raises(KeyError):
        DEFAULT_AGENT_SKILLS.for_action("investigate_current_scope")


def test_skill_content_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        validate_agent_skill_content("   ")
