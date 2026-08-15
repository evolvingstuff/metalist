from __future__ import annotations

from app.services.search_index import extract_tags_for_search, search_index
from app.services.search_query import parse_search_query
from app.services.search_text import build_searchable_text_casefold
from app.services.store import store
from app.services.tag_case import (
    build_preferred_tag_case_map,
    dedupe_tag_terms_by_casefold,
    prefer_existing_tag_case,
)


def compute_inherited_non_meta_tag_terms(parent_id: str | None) -> set[str]:
    inherited: set[str] = set()
    current_id = parent_id
    while current_id is not None:
        ancestor = store.get(current_id)
        for term in extract_tags_for_search(ancestor.tags):
            if term.startswith("@"):  # meta tags do not inherit
                continue
            inherited.add(term)
        current_id = ancestor.parent_id
    return inherited


def ensure_tags_match_search_query(
    *,
    parent_id: str | None,
    content: str,
    tags: str,
    search_query: str,
) -> str:
    if not isinstance(content, str):
        raise TypeError(f"content must be a string, got {type(content)}")
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")
    if not isinstance(search_query, str):
        raise TypeError(f"search_query must be a string, got {type(search_query)}")

    parsed = parse_search_query(search_query)
    first_clause = parsed.first_clause
    if not first_clause.required_tags and not first_clause.required_text:
        return tags

    inherited_non_meta = compute_inherited_non_meta_tag_terms(parent_id)
    explicit_terms = extract_tags_for_search(tags)
    inherited_non_meta_casefold = {term.casefold() for term in inherited_non_meta}
    explicit_terms_casefold = {term.casefold() for term in explicit_terms}
    preferred_by_casefold = build_preferred_tag_case_map(search_index.list_tag_frequencies())

    additions: list[str] = []
    required_tag_terms = dedupe_tag_terms_by_casefold(
        [
            prefer_existing_tag_case(term, preferred_by_casefold)
            for term in sorted(first_clause.required_tags)
        ]
    )
    for term in required_tag_terms:
        if term.startswith("@"):
            if term.casefold() in explicit_terms_casefold:
                continue
            additions.append(term)
            continue
        if term.casefold() in inherited_non_meta_casefold or term.casefold() in explicit_terms_casefold:
            continue
        additions.append(term)

    next_tags = tags.strip()
    if additions:
        if next_tags == "":
            next_tags = " ".join(additions)
        else:
            next_tags = f"{next_tags} {' '.join(additions)}"

    if not first_clause.required_text:
        return next_tags

    searchable = build_searchable_text_casefold(content, next_tags)
    missing_phrases: list[str] = []
    for phrase in first_clause.required_text:
        if phrase.casefold() in searchable:
            continue
        missing_phrases.append(phrase)

    if not missing_phrases:
        return next_tags

    comment_tokens: list[str] = []
    for phrase in missing_phrases:
        if not isinstance(phrase, str):
            raise TypeError(f"search phrase must be a string, got {type(phrase)}")
        if "/*" in phrase or "*/" in phrase:
            continue
        comment_tokens.append(f"/*{phrase}*/")

    if not comment_tokens:
        return next_tags

    suffix = " ".join(comment_tokens)
    if next_tags == "":
        return suffix
    return f"{next_tags} {suffix}"


__all__ = ["compute_inherited_non_meta_tag_terms", "ensure_tags_match_search_query"]
