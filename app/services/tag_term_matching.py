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


@dataclass(frozen=True, slots=True)
class TagContentMatch:
    phrase_match: bool
    matched_segment_count: int
    segment_count: int
    first_position: int
    normalized_length: int

    def sort_key(self) -> tuple[int, int, int, int, int]:
        phrase_match_score = 1 if self.phrase_match else 0
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

    segments = split_tag_term_segments(term)
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

    matched_segment_count = 0
    matched_positions: list[int] = []
    for segment in set(segments):
        if segment in token_positions:
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
        segment_count=len(segments),
        first_position=first_position,
        normalized_length=len(phrase),
    )


__all__ = [
    "TagContentMatch",
    "match_tag_term_in_normalized_content",
    "normalize_tag_match_text",
    "split_tag_term_segments",
    "tag_term_matches_prefix",
]
