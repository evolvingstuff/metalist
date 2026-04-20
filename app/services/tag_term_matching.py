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
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "off",
        "on",
        "or",
        "out",
        "the",
        "to",
        "up",
        "with",
    }
)


@dataclass(frozen=True, slots=True)
class TagContentMatch:
    phrase_match: bool
    matched_segment_count: int
    matched_segments: tuple[str, ...]
    segment_count: int
    first_position: int
    normalized_length: int

    def sort_key(self) -> tuple[int, int, int, int, int]:
        phrase_match_score = 0
        if self.phrase_match:
            phrase_match_score = 1
        return (
            phrase_match_score,
            self.matched_segment_count,
            self.segment_count,
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

    segments = list_significant_content_match_segments(term)
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
    for segment in dict.fromkeys(segments):
        if segment in token_positions:
            matched_segments.append(segment)
            matched_segment_count += 1
            matched_positions.append(token_positions[segment])

    if not phrase_match and matched_segment_count == 0:
        return None

    first_position = phrase_position
    if not phrase_match:
        assert matched_positions
        first_position = min(matched_positions)

    return TagContentMatch(
        phrase_match=phrase_match,
        matched_segment_count=matched_segment_count,
        matched_segments=tuple(matched_segments),
        segment_count=len(segments),
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
