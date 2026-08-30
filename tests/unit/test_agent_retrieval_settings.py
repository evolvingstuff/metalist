import pytest

from app.services.agent.retrieval_settings import (
    DEFAULT_AGENT_RETRIEVAL_SETTINGS,
    DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS,
    MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY,
    OPENAI_MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY,
    AgentRetrievalSettings,
    resolve_agent_retrieval_settings,
    validate_max_page_approximate_tokens_preference,
    validate_openai_max_page_approximate_tokens_preference,
)


def test_defaults_define_only_one_evidence_token_limit() -> None:
    assert DEFAULT_AGENT_RETRIEVAL_SETTINGS == AgentRetrievalSettings(
        max_page_approximate_tokens=5_000,
    )
    assert DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS == AgentRetrievalSettings(
        max_page_approximate_tokens=250_000,
    )


def test_provider_preferences_are_independent() -> None:
    preferences = {
        MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY: "7000",
        OPENAI_MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY: "500000",
    }
    assert resolve_agent_retrieval_settings(
        preferences=preferences,
        provider="ollama",
    ).max_page_approximate_tokens == 7_000
    assert resolve_agent_retrieval_settings(
        preferences=preferences,
        provider="openai",
    ).max_page_approximate_tokens == 500_000


def test_legacy_openai_default_migrates_to_current_default() -> None:
    settings = resolve_agent_retrieval_settings(
        preferences={
            OPENAI_MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY: "24000",
        },
        provider="openai",
    )
    assert settings == DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS


@pytest.mark.parametrize("value", ["", "0499", "499", "24001", "1.5"])
def test_ollama_evidence_token_limit_rejects_invalid_values(value: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        validate_max_page_approximate_tokens_preference(value)


@pytest.mark.parametrize("value", ["", "0499", "499", "500001", "1.5"])
def test_openai_evidence_token_limit_rejects_invalid_values(value: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        validate_openai_max_page_approximate_tokens_preference(value)
