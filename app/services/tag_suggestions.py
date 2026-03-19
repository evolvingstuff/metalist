from __future__ import annotations

from typing import Dict, Iterable, List

from app.services.note_store import store as note_store
from app.services.ontology_rules_store import get_ontology
from app.services.search_index import search_index
from app.services.tag_term_matching import match_tag_term_in_normalized_content
from app.services.tag_term_matching import normalize_tag_match_text
from app.services.tag_term_matching import tag_term_matches_prefix
from app.utils.text_utils import strip_html


def _sanitize_anchor_tags(anchors: Iterable[str]) -> List[str]:
    if anchors is None:
        raise TypeError("anchors must be provided")

    cleaned: List[str] = []
    for tag in anchors:
        if not isinstance(tag, str):
            raise TypeError("anchors must be strings")
        if tag:
            cleaned.append(tag)
    return cleaned


def _build_search_query_for_suggestions(*, anchors: Iterable[str], prefix: str) -> str:
    if not isinstance(prefix, str):
        raise TypeError("prefix must be a string")

    parts: List[str] = []
    for anchor in anchors:
        if not isinstance(anchor, str):
            raise TypeError("anchors must be strings")
        if anchor:
            parts.append(anchor)

    if prefix != "":
        parts.append(prefix)
        return " ".join(parts)

    if parts:
        return " ".join(parts) + " "

    return ""


def suggest_tags_for_note(
    *,
    note_id: str,
    anchors: Iterable[str],
    prefix: str,
    content_html: str,
) -> List[str]:
    if not isinstance(note_id, str) or not note_id:
        raise TypeError("note_id must be a non-empty string")
    if not isinstance(prefix, str):
        raise TypeError("prefix must be a string")
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")

    anchor_list = _sanitize_anchor_tags(anchors)
    anchor_set = {tag for tag in anchor_list if not tag.startswith("@")}

    inherited_non_meta = note_store.get_inherited_non_meta_tag_terms(note_id)
    base_tags = frozenset(anchor_set | inherited_non_meta)

    plaintext = strip_html(content_html)
    ontology = get_ontology()
    if ontology.is_empty:
        effective_tags = base_tags
    else:
        effective_tags = ontology.infer_effective_tags(base_tags=base_tags, plaintext=plaintext)
    already_present = {tag for tag in effective_tags if not tag.startswith("@")}

    all_terms = search_index.list_non_meta_tag_terms()
    has_prefix = prefix != ""

    content_match_scores: Dict[str, tuple[int, int, int, int]] = {}
    normalized_content = normalize_tag_match_text(plaintext)
    for term in all_terms:
        if term in already_present:
            continue
        if has_prefix and not tag_term_matches_prefix(term=term, prefix=prefix):
            continue
        match = match_tag_term_in_normalized_content(term=term, normalized_content=normalized_content)
        if match is None:
            continue
        content_match_scores[term] = match.sort_key()

    cooccurrence: List[str] = []
    term_count = len(all_terms)
    if term_count > 0:
        query = _build_search_query_for_suggestions(anchors=anchor_list, prefix=prefix)
        cooccurrence = search_index.suggest_tag_completions(query=query, limit=term_count)

    content_first: List[str] = []
    remaining: List[str] = []
    cooccurrence_rank = {term: index for index, term in enumerate(cooccurrence)}
    for term in cooccurrence:
        if term in already_present:
            continue
        if term in content_match_scores:
            content_first.append(term)
            continue
        remaining.append(term)

    content_first.sort(
        key=lambda term: (
            -content_match_scores[term][0],
            -content_match_scores[term][1],
            -content_match_scores[term][2],
            -content_match_scores[term][3],
            cooccurrence_rank[term],
            term,
        )
    )

    suggestions = content_first + remaining

    if has_prefix:
        present_suffix: List[str] = []
        for term in already_present:
            if tag_term_matches_prefix(term=term, prefix=prefix):
                present_suffix.append(term)
        present_suffix.sort()
        suggestions.extend(present_suffix)

    return suggestions


__all__ = ["suggest_tags_for_note"]
