"""Validated namespace-scoped limits for agent note retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MAX_NOTE_CHARACTERS_PREFERENCE_KEY = "pref.ai.retrieval.max_note_characters"
MAX_PAGE_CHARACTERS_PREFERENCE_KEY = "pref.ai.retrieval.max_page_characters"
MAX_NOTES_PER_PAGE_PREFERENCE_KEY = "pref.ai.retrieval.max_notes_per_page"
MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY = (
    "pref.ai.retrieval.max_page_approximate_tokens"
)
MAX_RANKED_TAGS_PER_PAGE_PREFERENCE_KEY = (
    "pref.ai.retrieval.max_ranked_tags_per_page"
)
MAX_WORKING_SUMMARY_CHARACTERS_PREFERENCE_KEY = (
    "pref.ai.retrieval.max_working_summary_characters"
)
OPENAI_MAX_NOTE_CHARACTERS_PREFERENCE_KEY = (
    "pref.ai.openai.retrieval.max_note_characters"
)
OPENAI_MAX_PAGE_CHARACTERS_PREFERENCE_KEY = (
    "pref.ai.openai.retrieval.max_page_characters"
)
OPENAI_MAX_NOTES_PER_PAGE_PREFERENCE_KEY = (
    "pref.ai.openai.retrieval.max_notes_per_page"
)
OPENAI_MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY = (
    "pref.ai.openai.retrieval.max_page_approximate_tokens"
)
OPENAI_MAX_RANKED_TAGS_PER_PAGE_PREFERENCE_KEY = (
    "pref.ai.openai.retrieval.max_ranked_tags_per_page"
)
OPENAI_MAX_WORKING_SUMMARY_CHARACTERS_PREFERENCE_KEY = (
    "pref.ai.openai.retrieval.max_working_summary_characters"
)

DEFAULT_MAX_NOTE_CHARACTERS = 2_000
DEFAULT_MAX_PAGE_CHARACTERS = 20_000
DEFAULT_MAX_NOTES_PER_PAGE = 50
DEFAULT_MAX_PAGE_APPROXIMATE_TOKENS = 5_000
DEFAULT_MAX_RANKED_TAGS_PER_PAGE = 50
DEFAULT_MAX_WORKING_SUMMARY_CHARACTERS = 8_000
DEFAULT_OPENAI_MAX_PAGE_APPROXIMATE_TOKENS = 24_000
MIN_MAX_NOTE_CHARACTERS = 500
MAX_MAX_NOTE_CHARACTERS = 10_000
MIN_MAX_PAGE_CHARACTERS = 5_000
MAX_MAX_PAGE_CHARACTERS = 100_000
MIN_MAX_NOTES_PER_PAGE = 1
MAX_MAX_NOTES_PER_PAGE = 100
MIN_MAX_PAGE_APPROXIMATE_TOKENS = 500
MAX_MAX_PAGE_APPROXIMATE_TOKENS = 24_000
MIN_MAX_RANKED_TAGS_PER_PAGE = 1
MAX_MAX_RANKED_TAGS_PER_PAGE = 200
MIN_MAX_WORKING_SUMMARY_CHARACTERS = 2_000
MAX_MAX_WORKING_SUMMARY_CHARACTERS = 32_000


@dataclass(frozen=True, slots=True)
class AgentRetrievalSettings:
    max_note_characters: int
    max_page_characters: int
    max_notes_per_page: int
    max_page_approximate_tokens: int = DEFAULT_MAX_PAGE_APPROXIMATE_TOKENS
    max_ranked_tags_per_page: int = DEFAULT_MAX_RANKED_TAGS_PER_PAGE
    max_working_summary_characters: int = DEFAULT_MAX_WORKING_SUMMARY_CHARACTERS

    def __post_init__(self) -> None:
        _validate_integer_range(
            value=self.max_note_characters,
            label="Agent maximum note characters",
            minimum=MIN_MAX_NOTE_CHARACTERS,
            maximum=MAX_MAX_NOTE_CHARACTERS,
        )
        _validate_integer_range(
            value=self.max_page_characters,
            label="Agent maximum page characters",
            minimum=MIN_MAX_PAGE_CHARACTERS,
            maximum=MAX_MAX_PAGE_CHARACTERS,
        )
        _validate_integer_range(
            value=self.max_notes_per_page,
            label="Agent maximum result trees per page",
            minimum=MIN_MAX_NOTES_PER_PAGE,
            maximum=MAX_MAX_NOTES_PER_PAGE,
        )
        _validate_integer_range(
            value=self.max_page_approximate_tokens,
            label="Agent approximate tokens per evidence page",
            minimum=MIN_MAX_PAGE_APPROXIMATE_TOKENS,
            maximum=MAX_MAX_PAGE_APPROXIMATE_TOKENS,
        )
        _validate_integer_range(
            value=self.max_ranked_tags_per_page,
            label="Agent maximum ranked tags per facet page",
            minimum=MIN_MAX_RANKED_TAGS_PER_PAGE,
            maximum=MAX_MAX_RANKED_TAGS_PER_PAGE,
        )
        _validate_integer_range(
            value=self.max_working_summary_characters,
            label="Agent maximum working-summary characters",
            minimum=MIN_MAX_WORKING_SUMMARY_CHARACTERS,
            maximum=MAX_MAX_WORKING_SUMMARY_CHARACTERS,
        )


def validate_max_note_characters_preference(value: str) -> str:
    return _validate_integer_preference(
        value=value,
        label="Agent maximum note characters preference",
        minimum=MIN_MAX_NOTE_CHARACTERS,
        maximum=MAX_MAX_NOTE_CHARACTERS,
    )


def validate_max_notes_per_page_preference(value: str) -> str:
    return _validate_integer_preference(
        value=value,
        label="Agent maximum result trees per page preference",
        minimum=MIN_MAX_NOTES_PER_PAGE,
        maximum=MAX_MAX_NOTES_PER_PAGE,
    )


def validate_max_page_characters_preference(value: str) -> str:
    return _validate_integer_preference(
        value=value,
        label="Agent maximum page characters preference",
        minimum=MIN_MAX_PAGE_CHARACTERS,
        maximum=MAX_MAX_PAGE_CHARACTERS,
    )


def validate_max_page_approximate_tokens_preference(value: str) -> str:
    return _validate_integer_preference(
        value=value,
        label="Agent approximate tokens per evidence page preference",
        minimum=MIN_MAX_PAGE_APPROXIMATE_TOKENS,
        maximum=MAX_MAX_PAGE_APPROXIMATE_TOKENS,
    )


def validate_max_ranked_tags_per_page_preference(value: str) -> str:
    return _validate_integer_preference(
        value=value,
        label="Agent maximum ranked tags per facet page preference",
        minimum=MIN_MAX_RANKED_TAGS_PER_PAGE,
        maximum=MAX_MAX_RANKED_TAGS_PER_PAGE,
    )


def validate_max_working_summary_characters_preference(value: str) -> str:
    return _validate_integer_preference(
        value=value,
        label="Agent maximum working-summary characters preference",
        minimum=MIN_MAX_WORKING_SUMMARY_CHARACTERS,
        maximum=MAX_MAX_WORKING_SUMMARY_CHARACTERS,
    )


def resolve_agent_retrieval_settings(
    *,
    preferences: dict[str, str],
    provider: Literal["ollama", "openai"],
) -> AgentRetrievalSettings:
    if not isinstance(preferences, dict):
        raise TypeError("preferences must be a dict")
    preference_keys = _preference_keys_for_provider(provider=provider)
    defaults = _defaults_for_provider(provider=provider)
    raw_max_note_characters = preferences.get(
        preference_keys["max_note_characters"],
        str(defaults.max_note_characters),
    )
    raw_max_notes_per_page = preferences.get(
        preference_keys["max_notes_per_page"],
        str(defaults.max_notes_per_page),
    )
    raw_max_page_characters = preferences.get(
        preference_keys["max_page_characters"],
        str(defaults.max_page_characters),
    )
    raw_max_page_approximate_tokens = preferences.get(
        preference_keys["max_page_approximate_tokens"],
        str(defaults.max_page_approximate_tokens),
    )
    raw_max_ranked_tags_per_page = preferences.get(
        preference_keys["max_ranked_tags_per_page"],
        str(defaults.max_ranked_tags_per_page),
    )
    raw_max_working_summary_characters = preferences.get(
        preference_keys["max_working_summary_characters"],
        str(defaults.max_working_summary_characters),
    )
    validated_max_note_characters = validate_max_note_characters_preference(
        raw_max_note_characters
    )
    validated_max_notes_per_page = validate_max_notes_per_page_preference(
        raw_max_notes_per_page
    )
    validated_max_page_characters = validate_max_page_characters_preference(
        raw_max_page_characters
    )
    validated_max_page_approximate_tokens = (
        validate_max_page_approximate_tokens_preference(
            raw_max_page_approximate_tokens
        )
    )
    validated_max_ranked_tags_per_page = (
        validate_max_ranked_tags_per_page_preference(
            raw_max_ranked_tags_per_page
        )
    )
    validated_max_working_summary_characters = (
        validate_max_working_summary_characters_preference(
            raw_max_working_summary_characters
        )
    )
    return AgentRetrievalSettings(
        max_note_characters=int(validated_max_note_characters),
        max_page_characters=int(validated_max_page_characters),
        max_notes_per_page=int(validated_max_notes_per_page),
        max_page_approximate_tokens=int(
            validated_max_page_approximate_tokens
        ),
        max_ranked_tags_per_page=int(validated_max_ranked_tags_per_page),
        max_working_summary_characters=int(
            validated_max_working_summary_characters
        ),
    )


def _validate_integer_preference(
    *,
    value: str,
    label: str,
    minimum: int,
    maximum: int,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if value == "" or not value.isascii() or not value.isdecimal():
        raise ValueError(f"{label} must be a canonical positive integer")
    parsed = int(value)
    if str(parsed) != value:
        raise ValueError(f"{label} must be a canonical positive integer")
    _validate_integer_range(
        value=parsed,
        label=label,
        minimum=minimum,
        maximum=maximum,
    )
    return value


def _validate_integer_range(
    *,
    value: int,
    label: str,
    minimum: int,
    maximum: int,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{label} must be from {minimum} to {maximum}")


DEFAULT_AGENT_RETRIEVAL_SETTINGS = AgentRetrievalSettings(
    max_note_characters=DEFAULT_MAX_NOTE_CHARACTERS,
    max_page_characters=DEFAULT_MAX_PAGE_CHARACTERS,
    max_notes_per_page=DEFAULT_MAX_NOTES_PER_PAGE,
    max_page_approximate_tokens=DEFAULT_MAX_PAGE_APPROXIMATE_TOKENS,
    max_ranked_tags_per_page=DEFAULT_MAX_RANKED_TAGS_PER_PAGE,
    max_working_summary_characters=DEFAULT_MAX_WORKING_SUMMARY_CHARACTERS,
)

DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS = AgentRetrievalSettings(
    max_note_characters=DEFAULT_MAX_NOTE_CHARACTERS,
    max_page_characters=DEFAULT_MAX_PAGE_CHARACTERS,
    max_notes_per_page=DEFAULT_MAX_NOTES_PER_PAGE,
    max_page_approximate_tokens=DEFAULT_OPENAI_MAX_PAGE_APPROXIMATE_TOKENS,
    max_ranked_tags_per_page=DEFAULT_MAX_RANKED_TAGS_PER_PAGE,
    max_working_summary_characters=DEFAULT_MAX_WORKING_SUMMARY_CHARACTERS,
)


def _preference_keys_for_provider(
    *,
    provider: Literal["ollama", "openai"],
) -> dict[str, str]:
    if provider == "ollama":
        return {
            "max_note_characters": MAX_NOTE_CHARACTERS_PREFERENCE_KEY,
            "max_page_characters": MAX_PAGE_CHARACTERS_PREFERENCE_KEY,
            "max_notes_per_page": MAX_NOTES_PER_PAGE_PREFERENCE_KEY,
            "max_page_approximate_tokens": (
                MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY
            ),
            "max_ranked_tags_per_page": (
                MAX_RANKED_TAGS_PER_PAGE_PREFERENCE_KEY
            ),
            "max_working_summary_characters": (
                MAX_WORKING_SUMMARY_CHARACTERS_PREFERENCE_KEY
            ),
        }
    if provider == "openai":
        return {
            "max_note_characters": OPENAI_MAX_NOTE_CHARACTERS_PREFERENCE_KEY,
            "max_page_characters": OPENAI_MAX_PAGE_CHARACTERS_PREFERENCE_KEY,
            "max_notes_per_page": OPENAI_MAX_NOTES_PER_PAGE_PREFERENCE_KEY,
            "max_page_approximate_tokens": (
                OPENAI_MAX_PAGE_APPROXIMATE_TOKENS_PREFERENCE_KEY
            ),
            "max_ranked_tags_per_page": (
                OPENAI_MAX_RANKED_TAGS_PER_PAGE_PREFERENCE_KEY
            ),
            "max_working_summary_characters": (
                OPENAI_MAX_WORKING_SUMMARY_CHARACTERS_PREFERENCE_KEY
            ),
        }
    raise ValueError(f"Unsupported agent retrieval provider: {provider}")


def _defaults_for_provider(
    *,
    provider: Literal["ollama", "openai"],
) -> AgentRetrievalSettings:
    if provider == "ollama":
        return DEFAULT_AGENT_RETRIEVAL_SETTINGS
    if provider == "openai":
        return DEFAULT_OPENAI_AGENT_RETRIEVAL_SETTINGS
    raise ValueError(f"Unsupported agent retrieval provider: {provider}")
