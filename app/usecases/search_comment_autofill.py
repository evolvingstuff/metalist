from __future__ import annotations

from typing import Optional, Sequence

from app.services.search_query import parse_search_query
from app.services.search_text import build_searchable_text_casefold
from app.services.store import store


def _is_ascii_printable(text: str) -> bool:
    return all(32 <= ord(ch) <= 126 for ch in text)


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _build_comment_tokens(required_text_terms: Sequence[str]) -> str:
    tokens: list[str] = []
    for term in _dedupe_preserve_order(required_text_terms):
        if not isinstance(term, str):
            raise TypeError(f"search term must be a string, got {type(term)}")
        if not _is_ascii_printable(term):
            continue
        if "/*" in term or "*/" in term:
            continue
        tokens.append(f"/*{term}*/")
    return " ".join(tokens)


def _extract_positive_text_terms(search_query: Optional[str]) -> tuple[str, ...]:
    if search_query is None:
        return ()
    if not isinstance(search_query, str):
        raise TypeError(f"search_query must be a string or None, got {type(search_query)}")
    if search_query.strip() == "":
        return ()
    parsed = parse_search_query(search_query)
    return parsed.required_text


def compute_initial_tags_for_new_note(
    *,
    parent_id: Optional[str],
    search_query: Optional[str],
) -> str:
    required_text_terms = _extract_positive_text_terms(search_query)
    if not required_text_terms:
        return ""

    if parent_id is None:
        return _build_comment_tokens(required_text_terms)

    current_id = parent_id
    while current_id is not None:
        ancestor = store.get(current_id)
        ancestor_text = build_searchable_text_casefold(ancestor.content, ancestor.tags)
        if all(term.casefold() in ancestor_text for term in required_text_terms):
            return ""
        current_id = ancestor.parent_id

    return _build_comment_tokens(required_text_terms)
