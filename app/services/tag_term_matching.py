from __future__ import annotations

from dataclasses import dataclass
import re

from app.config import TAG_SUGGESTION_CONNECTORS


_CONNECTOR_CHARS = TAG_SUGGESTION_CONNECTORS
if not isinstance(_CONNECTOR_CHARS, str):
    raise TypeError("TAG_SUGGESTION_CONNECTORS must be a string")
if _CONNECTOR_CHARS == "":
    raise ValueError("TAG_SUGGESTION_CONNECTORS must be non-empty")
if any(char.isspace() for char in _CONNECTOR_CHARS):
    raise ValueError("TAG_SUGGESTION_CONNECTORS must not include whitespace")

_CONNECTOR_RE = re.compile(f"[{re.escape(_CONNECTOR_CHARS)}]")
_MATCH_NOISE_RE = re.compile(r"[^\w@#+%&']+")
_WHITESPACE_RE = re.compile(r"\s+")
_NUMERIC_SEGMENT_RE = re.compile(r"^\d+$")
_LOW_SIGNAL_CONTENT_MATCH_SEGMENTS = frozenset(
    {
        "an",
        "and",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "or",
        "out",
        "per",
        "the",
        "than",
        "to",
        "too",
        "up",
        "via",
        "with",
    }
)
_LOW_SIGNAL_UPPERCASE_SINGLE_LETTER_SEGMENTS = frozenset({"a", "i"})


@dataclass(frozen=True, slots=True)
class TagContentMatch:
    phrase_match: bool
    matched_segment_count: int
    matched_segments: tuple[str, ...]
    segment_count: int
    raw_segment_count: int
    first_matched_raw_segment_index: int
    first_position: int
    normalized_length: int

    def sort_key(self) -> tuple[int, int, int, int, int, int, int]:
        phrase_match_score = 0
        if self.phrase_match:
            phrase_match_score = 1
        return (
            phrase_match_score,
            self.matched_segment_count,
            self.segment_count,
            -self.raw_segment_count,
            -self.first_matched_raw_segment_index,
            -self.first_position,
            self.normalized_length,
        )


def normalize_tag_match_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    casefolded = text.casefold()
    connectors_as_spaces = _CONNECTOR_RE.sub(" ", casefolded)
    stripped_noise = _MATCH_NOISE_RE.sub(" ", connectors_as_spaces)
    return _WHITESPACE_RE.sub(" ", stripped_noise).strip()


def split_tag_term_segments(term: str) -> tuple[str, ...]:
    if not isinstance(term, str):
        raise TypeError("term must be a string")

    normalized = normalize_tag_match_text(term)
    if normalized == "":
        return ()
    return tuple(segment for segment in normalized.split(" ") if segment)


def _split_tag_term_segments_preserving_case(term: str) -> tuple[str, ...]:
    if not isinstance(term, str):
        raise TypeError("term must be a string")

    connectors_as_spaces = _CONNECTOR_RE.sub(" ", term)
    stripped_noise = _MATCH_NOISE_RE.sub(" ", connectors_as_spaces)
    normalized_whitespace = _WHITESPACE_RE.sub(" ", stripped_noise).strip()
    if normalized_whitespace == "":
        return ()
    return tuple(segment for segment in normalized_whitespace.split(" ") if segment)


def _is_significant_content_match_segment(*, segment: str, raw_segment: str) -> bool:
    if not isinstance(segment, str):
        raise TypeError("segment must be a string")
    if not isinstance(raw_segment, str):
        raise TypeError("raw_segment must be a string")
    if len(segment) < 2:
        return (
            len(segment) == 1
            and raw_segment.isalpha()
            and raw_segment == raw_segment.upper()
            and raw_segment != raw_segment.lower()
            and segment not in _LOW_SIGNAL_UPPERCASE_SINGLE_LETTER_SEGMENTS
        )
    if _NUMERIC_SEGMENT_RE.fullmatch(segment):
        return False
    if segment in _LOW_SIGNAL_CONTENT_MATCH_SEGMENTS:
        return False
    return True


def list_significant_content_match_segments(term: str) -> tuple[str, ...]:
    if not isinstance(term, str):
        raise TypeError("term must be a string")

    raw_segments = _split_tag_term_segments_preserving_case(term)
    return tuple(
        raw_segment.casefold()
        for raw_segment in raw_segments
        if _is_significant_content_match_segment(
            segment=raw_segment.casefold(),
            raw_segment=raw_segment,
        )
    )


def _list_significant_content_match_segments_with_raw_indexes(
    term: str,
) -> tuple[tuple[str, ...], tuple[int, ...], int]:
    if not isinstance(term, str):
        raise TypeError("term must be a string")

    raw_segments = _split_tag_term_segments_preserving_case(term)
    significant_segments: list[str] = []
    significant_raw_indexes: list[int] = []
    for raw_index, raw_segment in enumerate(raw_segments):
        normalized_segment = raw_segment.casefold()
        if not _is_significant_content_match_segment(
            segment=normalized_segment,
            raw_segment=raw_segment,
        ):
            continue
        significant_segments.append(normalized_segment)
        significant_raw_indexes.append(raw_index)
    return (
        tuple(significant_segments),
        tuple(significant_raw_indexes),
        len(raw_segments),
    )


def tag_term_matches_prefix(*, term: str, prefix: str) -> bool:
    if not isinstance(term, str):
        raise TypeError("term must be a string")
    if not isinstance(prefix, str):
        raise TypeError("prefix must be a string")
    if prefix == "":
        return True

    prefix_casefold = prefix.casefold()
    if term.casefold().startswith(prefix_casefold):
        return True

    for segment in split_tag_term_segments(term):
        if segment.startswith(prefix_casefold):
            return True
    return False


def match_tag_term_in_normalized_content(*, term: str, normalized_content: str) -> TagContentMatch | None:
    if not isinstance(term, str):
        raise TypeError("term must be a string")
    if not isinstance(normalized_content, str):
        raise TypeError("normalized_content must be a string")

    segments, segment_raw_indexes, raw_segment_count = _list_significant_content_match_segments_with_raw_indexes(
        term
    )
    if not segments:
        return None

    phrase = " ".join(segments)
    content_tokens = normalized_content.split()
    token_positions: dict[str, int] = {}
    for index, token in enumerate(content_tokens):
        if token not in token_positions:
            token_positions[token] = index

    phrase_match = False
    phrase_position = -1
    if len(content_tokens) >= len(segments):
        for index in range(len(content_tokens) - len(segments) + 1):
            if tuple(content_tokens[index : index + len(segments)]) == segments:
                phrase_match = True
                phrase_position = index
                break

    matched_segments: list[str] = []
    matched_segment_count = 0
    matched_positions: list[int] = []
    matched_raw_indexes: list[int] = []
    for raw_index, segment in zip(segment_raw_indexes, segments):
        if segment in matched_segments:
            continue
        if segment in token_positions:
            matched_segments.append(segment)
            matched_segment_count += 1
            matched_positions.append(token_positions[segment])
            matched_raw_indexes.append(raw_index)

    required_matched_segment_count = max(1, len(segments) - 1)
    if matched_segment_count < required_matched_segment_count:
        return None

    assert matched_raw_indexes

    first_position = phrase_position
    if not phrase_match:
        assert matched_positions
        first_position = min(matched_positions)

    return TagContentMatch(
        phrase_match=phrase_match,
        matched_segment_count=matched_segment_count,
        matched_segments=tuple(matched_segments),
        segment_count=len(segments),
        raw_segment_count=raw_segment_count,
        first_matched_raw_segment_index=min(matched_raw_indexes),
        first_position=first_position,
        normalized_length=len(phrase),
    )


__all__ = [
    "TagContentMatch",
    "list_significant_content_match_segments",
    "match_tag_term_in_normalized_content",
    "normalize_tag_match_text",
    "split_tag_term_segments",
    "tag_term_matches_prefix",
]
