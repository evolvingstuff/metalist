import pytest

from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.retrieval_settings import DEFAULT_AGENT_RETRIEVAL_SETTINGS
from app.services.agent.retrieval_settings import MAX_NOTE_CHARACTERS_PREFERENCE_KEY
from app.services.agent.retrieval_settings import MAX_PAGE_CHARACTERS_PREFERENCE_KEY
from app.services.agent.retrieval_settings import MAX_NOTES_PER_PAGE_PREFERENCE_KEY
from app.services.agent.retrieval_settings import MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY
from app.services.agent.retrieval_settings import MAX_RANKED_TAGS_PER_PAGE_PREFERENCE_KEY
from app.services.agent.retrieval_settings import MAX_WORKING_SUMMARY_CHARACTERS_PREFERENCE_KEY
from app.services.agent.retrieval_settings import resolve_agent_retrieval_settings


def test_agent_retrieval_settings_use_bounded_defaults() -> None:
    assert resolve_agent_retrieval_settings(preferences={}) == (
        DEFAULT_AGENT_RETRIEVAL_SETTINGS
    )
    assert DEFAULT_AGENT_RETRIEVAL_SETTINGS.max_note_characters == 2_000
    assert DEFAULT_AGENT_RETRIEVAL_SETTINGS.max_page_characters == 20_000
    assert DEFAULT_AGENT_RETRIEVAL_SETTINGS.max_notes_per_page == 50
    assert DEFAULT_AGENT_RETRIEVAL_SETTINGS.max_page_approximate_tokens == 5_000
    assert DEFAULT_AGENT_RETRIEVAL_SETTINGS.max_ranked_tags_per_page == 50
    assert DEFAULT_AGENT_RETRIEVAL_SETTINGS.max_working_summary_characters == 8_000


def test_agent_retrieval_settings_resolve_namespace_preferences() -> None:
    settings = resolve_agent_retrieval_settings(
        preferences={
            MAX_NOTE_CHARACTERS_PREFERENCE_KEY: "4000",
            MAX_PAGE_CHARACTERS_PREFERENCE_KEY: "30000",
            MAX_NOTES_PER_PAGE_PREFERENCE_KEY: "3",
            MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY: "7000",
            MAX_RANKED_TAGS_PER_PAGE_PREFERENCE_KEY: "25",
            MAX_WORKING_SUMMARY_CHARACTERS_PREFERENCE_KEY: "12000",
        }
    )

    assert settings == AgentRetrievalSettings(
        max_note_characters=4_000,
        max_page_characters=30_000,
        max_notes_per_page=3,
        max_page_approximate_tokens=7_000,
        max_ranked_tags_per_page=25,
        max_working_summary_characters=12_000,
    )


@pytest.mark.parametrize(
    (
        "max_note_characters",
        "max_page_characters",
        "max_notes_per_page",
        "max_page_approximate_tokens",
    ),
    [
        (499, 20_000, 50, 5_000),
        (10_001, 20_000, 50, 5_000),
        (2_000, 4_999, 50, 5_000),
        (2_000, 100_001, 50, 5_000),
        (2_000, 20_000, 0, 5_000),
        (2_000, 20_000, 101, 5_000),
        (2_000, 20_000, 50, 499),
        (2_000, 20_000, 50, 24_001),
    ],
)
def test_agent_retrieval_settings_reject_out_of_range_values(
    max_note_characters: int,
    max_page_characters: int,
    max_notes_per_page: int,
    max_page_approximate_tokens: int,
) -> None:
    with pytest.raises(ValueError):
        AgentRetrievalSettings(
            max_note_characters=max_note_characters,
            max_page_characters=max_page_characters,
            max_notes_per_page=max_notes_per_page,
            max_page_approximate_tokens=max_page_approximate_tokens,
        )
