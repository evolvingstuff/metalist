"""Validated namespace-scoped limits for agent note retrieval."""

from __future__ import annotations

from dataclasses import dataclass


MAX_NOTE_CHARACTERS_PREFERENCE_KEY = "pref.ai.retrieval.max_note_characters"
MAX_PAGE_CHARACTERS_PREFERENCE_KEY = "pref.ai.retrieval.max_page_characters"
MAX_NOTES_PER_PAGE_PREFERENCE_KEY = "pref.ai.retrieval.max_notes_per_page"

DEFAULT_MAX_NOTE_CHARACTERS = 2_000
DEFAULT_MAX_PAGE_CHARACTERS = 20_000
DEFAULT_MAX_NOTES_PER_PAGE = 50
MIN_MAX_NOTE_CHARACTERS = 500
MAX_MAX_NOTE_CHARACTERS = 10_000
MIN_MAX_PAGE_CHARACTERS = 5_000
MAX_MAX_PAGE_CHARACTERS = 100_000
MIN_MAX_NOTES_PER_PAGE = 1
MAX_MAX_NOTES_PER_PAGE = 100


@dataclass(frozen=True, slots=True)
class AgentRetrievalSettings:
    max_note_characters: int
    max_page_characters: int
    max_notes_per_page: int

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


def resolve_agent_retrieval_settings(
    *,
    preferences: dict[str, str],
) -> AgentRetrievalSettings:
    if not isinstance(preferences, dict):
        raise TypeError("preferences must be a dict")
    raw_max_note_characters = preferences.get(
        MAX_NOTE_CHARACTERS_PREFERENCE_KEY,
        str(DEFAULT_MAX_NOTE_CHARACTERS),
    )
    raw_max_notes_per_page = preferences.get(
        MAX_NOTES_PER_PAGE_PREFERENCE_KEY,
        str(DEFAULT_MAX_NOTES_PER_PAGE),
    )
    raw_max_page_characters = preferences.get(
        MAX_PAGE_CHARACTERS_PREFERENCE_KEY,
        str(DEFAULT_MAX_PAGE_CHARACTERS),
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
    return AgentRetrievalSettings(
        max_note_characters=int(validated_max_note_characters),
        max_page_characters=int(validated_max_page_characters),
        max_notes_per_page=int(validated_max_notes_per_page),
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
)
