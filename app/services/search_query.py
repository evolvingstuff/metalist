from __future__ import annotations

import re
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Set, Tuple


@dataclass(frozen=True, slots=True)
class ParsedSearchQuery:
    required_tags: FrozenSet[str]
    forbidden_tags: FrozenSet[str]
    required_text: Tuple[str, ...]
    forbidden_text: Tuple[str, ...]


def parse_search_query(normalized_text: str) -> ParsedSearchQuery:
    if not isinstance(normalized_text, str):
        raise TypeError(f"search query must be a string, got {type(normalized_text)}")

    text = normalized_text.strip()
    if text == "":
        return ParsedSearchQuery(
            required_tags=frozenset(),
            forbidden_tags=frozenset(),
            required_text=(),
            forbidden_text=(),
        )

    required_tags: Set[str] = set()
    forbidden_tags: Set[str] = set()
    required_text: List[str] = []
    forbidden_text: List[str] = []

    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break

        prefix: Optional[str] = None
        if text[index] in ("+", "-"):
            prefix = text[index]
            index += 1
            if index >= len(text) or text[index].isspace():
                raise ValueError("Dangling prefix in search query")

        if text[index] in ('"', "'"):
            quote_char = text[index]
            if prefix == "+":
                prefix = None
            if prefix not in (None, "-"):
                raise ValueError(f"Invalid prefix {prefix!r} for quoted term")
            index += 1

            normalized_inner, next_index = _read_quoted_inner(text, index, quote_char)
            if next_index is None:
                raise ValueError(f"Unclosed quote {quote_char!r} in search query")
            if normalized_inner == "":
                raise ValueError("Empty quoted text term in search query")

            phrase = _normalize_phrase(_unescape_quoted_inner(normalized_inner, quote_char))
            if phrase == "":
                raise ValueError("Empty quoted text term in search query")
            if prefix == "-":
                forbidden_text.append(phrase)
            else:
                required_text.append(phrase)
            index = next_index
            continue

        start = index
        while index < len(text) and not text[index].isspace():
            index += 1
        token = text[start:index]
        if token == "":
            raise ValueError("Empty tag term in search query")

        if prefix == "-":
            forbidden_tags.add(token)
        else:
            required_tags.add(token)

    return ParsedSearchQuery(
        required_tags=frozenset(required_tags),
        forbidden_tags=frozenset(forbidden_tags),
        required_text=tuple(required_text),
        forbidden_text=tuple(forbidden_text),
    )


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_phrase(text: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", text)
    return normalized.strip()


def _read_quoted_inner(text: str, start_index: int, quote_char: str) -> tuple[str, Optional[int]]:
    index = start_index
    normalized_inner = ""
    while index < len(text):
        char = text[index]
        if char == quote_char:
            return normalized_inner, index + 1
        if char == "\\":
            if index + 1 < len(text):
                next_char = text[index + 1]
                if next_char == quote_char or next_char == "\\":
                    normalized_inner += f"\\{next_char}"
                    index += 2
                    continue
            normalized_inner += char
            index += 1
            continue
        normalized_inner += char
        index += 1
    return normalized_inner, None


def _unescape_quoted_inner(normalized_inner: str, quote_char: str) -> str:
    output = ""
    index = 0
    while index < len(normalized_inner):
        char = normalized_inner[index]
        if char != "\\":
            output += char
            index += 1
            continue
        if index + 1 < len(normalized_inner):
            next_char = normalized_inner[index + 1]
            if next_char == quote_char or next_char == "\\":
                output += next_char
                index += 2
                continue
        output += char
        index += 1
    return output

