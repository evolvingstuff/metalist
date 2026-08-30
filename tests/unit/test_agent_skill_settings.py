import pytest

from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.skill_settings import LEGACY_SCOPED_INVESTIGATION_V4_PREFERENCE_KEY
from app.services.agent.skill_settings import LEGACY_SCOPED_INVESTIGATION_V2_PREFERENCE_KEY
from app.services.agent.skill_settings import LEGACY_SCOPED_INVESTIGATION_V3_PREFERENCE_KEY
from app.services.agent.skill_settings import LEGACY_SEARCH_NOTES_SKILL_PREFERENCE_KEY
from app.services.agent.skill_settings import (
    LEGACY_SELECT_RELEVANT_EVIDENCE_SKILL_PREFERENCE_KEY,
)
from app.services.agent.skill_settings import SCOPED_INVESTIGATION_SKILL_PREFERENCE_KEY
from app.services.agent.skill_settings import resolve_agent_skill_set
from app.services.agent.skill_settings import validate_agent_skill_content


def test_packaged_investigation_skill_explains_scope_and_bounded_navigation() -> None:
    skill = DEFAULT_AGENT_SKILLS.for_action("investigate_current_scope")

    assert skill.title == "Investigate current scope"
    assert skill.preference_key == SCOPED_INVESTIGATION_SKILL_PREFERENCE_KEY
    normalized_skill = " ".join(skill.content.split())
    assert "immutable MetaList result scope" in normalized_skill
    assert "recursively nested `children`" in normalized_skill
    assert "contentless structural objects" in normalized_skill
    assert "directly assigned raw `tags`" in normalized_skill
    assert "untagged note omits the `tags` field" in normalized_skill
    assert "Do not infer additional, inherited, or ontology-implied tags" in normalized_skill
    assert "complete replacement working summary" in normalized_skill
    assert "Pydantic AI" not in skill.content
    assert "`foo OR bar baz`" in skill.content
    assert "lorem ipsum" in skill.content
    assert "project-foo" in skill.content
    assert "Do not prefix tags with `#`" in skill.content
    assert "page_next" in skill.content
    assert "inspect_tag_facets" in skill.content
    assert "backtrack" in skill.content
    assert "reopen_sources" in skill.content
    assert "generally more recent or more highly ranked by the user" in normalized_skill
    assert "ranking hint rather than proof of relevance" in normalized_skill


def test_one_page_evidence_selection_skill_is_no_longer_active() -> None:
    with pytest.raises(KeyError, match="Expected one agent skill"):
        DEFAULT_AGENT_SKILLS.for_action("evidence_selection")


def test_old_evidence_selection_override_is_explicitly_incompatible() -> None:
    with pytest.raises(ValueError, match="incompatible with the nested scoped investigation v5"):
        resolve_agent_skill_set(
            preferences={
                LEGACY_SELECT_RELEVANT_EVIDENCE_SKILL_PREFERENCE_KEY: (
                    "Old evidence-selection instructions"
                )
            }
        )


def test_resolve_agent_skill_set_uses_namespace_override() -> None:
    skills = resolve_agent_skill_set(
        preferences={
            SCOPED_INVESTIGATION_SKILL_PREFERENCE_KEY: "Custom investigation instructions"
        }
    )

    assert (
        skills.for_action("investigate_current_scope").content
        == "Custom investigation instructions"
    )


def test_legacy_search_skill_override_is_explicitly_incompatible() -> None:
    with pytest.raises(ValueError, match="incompatible with the nested scoped investigation v5"):
        resolve_agent_skill_set(
            preferences={
                LEGACY_SEARCH_NOTES_SKILL_PREFERENCE_KEY: "Old instructions"
            }
        )


def test_flat_v2_investigation_override_is_explicitly_incompatible() -> None:
    with pytest.raises(ValueError, match="nested scoped investigation v5"):
        resolve_agent_skill_set(
            preferences={
                LEGACY_SCOPED_INVESTIGATION_V2_PREFERENCE_KEY: (
                    "Old flat-page instructions"
                )
            }
        )


def test_inherited_tag_v3_override_is_explicitly_incompatible() -> None:
    with pytest.raises(ValueError, match="nested scoped investigation v5"):
        resolve_agent_skill_set(
            preferences={
                LEGACY_SCOPED_INVESTIGATION_V3_PREFERENCE_KEY: (
                    "Old inherited-tag instructions"
                )
            }
        )


def test_verbose_v4_investigation_override_is_explicitly_incompatible() -> None:
    with pytest.raises(ValueError, match="nested scoped investigation v5"):
        resolve_agent_skill_set(
            preferences={
                LEGACY_SCOPED_INVESTIGATION_V4_PREFERENCE_KEY: (
                    "Old verbose note-payload instructions"
                )
            }
        )


def test_agent_skill_content_rejects_blank_and_oversized_values() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        validate_agent_skill_content("  ")
    with pytest.raises(ValueError, match="must not exceed 32000"):
        validate_agent_skill_content("x" * 32_001)
