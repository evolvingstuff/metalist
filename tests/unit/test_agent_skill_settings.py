import pytest

from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.skill_settings import validate_agent_skill_content


def test_packaged_skill_describes_one_direct_evidence_payload() -> None:
    skill = DEFAULT_AGENT_SKILLS.for_action("investigate_current_scope")
    normalized = " ".join(skill.content.split())

    assert "one authoritative evidence payload" in normalized
    assert "full agent-visible content" in normalized
    assert "longest leading prefix of complete result trees" in normalized
    assert "[[note_id]]" in normalized
    assert "working summary" not in normalized.casefold()
    assert "next page" not in normalized.casefold()


def test_skill_content_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        validate_agent_skill_content("   ")
