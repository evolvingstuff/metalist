import pytest

from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.skill_settings import SEARCH_NOTES_SKILL_PREFERENCE_KEY
from app.services.agent.skill_settings import resolve_agent_skill_set
from app.services.agent.skill_settings import validate_agent_skill_content


def test_packaged_search_skill_explains_query_syntax_and_bounded_pages() -> None:
    skill = DEFAULT_AGENT_SKILLS.for_action("search_notes")

    assert skill.title == "Search notes"
    assert skill.preference_key == SEARCH_NOTES_SKILL_PREFERENCE_KEY
    normalized_skill = " ".join(skill.content.split())
    assert "at least one positive tag" in skill.content
    assert "The final user message is the current request" in normalized_skill
    assert "A topic change does not require an exclusion" in normalized_skill
    assert "Never carry an earlier topic into a new query merely to negate it" in (
        normalized_skill
    )
    assert "Pydantic AI" not in skill.content
    assert "`foo OR bar baz`" in skill.content
    assert '`foo OR "foo"`' in skill.content
    assert '`foo bar OR "foo bar"`' in skill.content
    assert '`-"lorem ipsum"`' in skill.content
    assert "both tags and note text" in normalized_skill
    assert "explicitly asks for tag-only or text-only scope" in normalized_skill
    assert "Use page `1`" in skill.content
    assert "`next_page` value" in skill.content
    assert "Broad synthesis requests normally require additional relevant pages" in (
        normalized_skill
    )
    assert "say which pages informed the answer" in normalized_skill
    assert "configured number of top-level result" in skill.content
    assert "do not issue another search merely to narrow" in normalized_skill
    assert "generally more recent or more highly ranked by the user" in normalized_skill
    assert "ranking hint, not proof of relevance" in normalized_skill
    assert "gray" in skill.content
    assert "created/updated timestamps" in skill.content


def test_resolve_agent_skill_set_uses_namespace_override() -> None:
    skills = resolve_agent_skill_set(
        preferences={SEARCH_NOTES_SKILL_PREFERENCE_KEY: "Custom search instructions"}
    )

    assert skills.for_action("search_notes").content == "Custom search instructions"


def test_agent_skill_content_rejects_blank_and_oversized_values() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        validate_agent_skill_content("  ")
    with pytest.raises(ValueError, match="must not exceed 32000"):
        validate_agent_skill_content("x" * 32_001)
