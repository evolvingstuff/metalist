from __future__ import annotations

from typing import Dict, Iterable, List

from app.services.note_store import store as note_store
from app.services.ontology_rules_store import get_ontology
from app.services.search_index import search_index
from app.services.tag_term_matching import TagContentMatch
from app.services.tag_term_matching import match_tag_term_in_normalized_content
from app.services.tag_term_matching import normalize_tag_match_text
from app.services.tag_term_matching import tag_term_matches_prefix
from app.utils.text_utils import strip_html


def _select_preferred_case_variants(*, terms: Iterable[str], exact_tag_counts: Dict[str, int]) -> List[str]:
    by_casefold: Dict[str, str] = {}
    for term in terms:
        term_casefold = term.casefold()
        if term_casefold not in by_casefold:
            by_casefold[term_casefold] = term
            continue
        current = by_casefold[term_casefold]
        current_count = exact_tag_counts[current] if current in exact_tag_counts else 0
        candidate_count = exact_tag_counts[term] if term in exact_tag_counts else 0
        if candidate_count > current_count:
            by_casefold[term_casefold] = term
            continue
        if candidate_count < current_count:
            continue
        current_penalty = 0 if current == current.casefold() else 1
        candidate_penalty = 0 if term == term.casefold() else 1
        if candidate_penalty < current_penalty:
            by_casefold[term_casefold] = term
            continue
        if candidate_penalty == current_penalty and term < current:
            by_casefold[term_casefold] = term
    return list(by_casefold.values())


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
    anchor_casefold_set = {tag.casefold() for tag in anchor_set}

    inherited_non_meta = note_store.get_inherited_non_meta_tag_terms(note_id)
    base_tags = frozenset(anchor_set | inherited_non_meta)

    plaintext = strip_html(content_html)
    ontology = get_ontology()
    if ontology.is_empty:
        effective_tags = base_tags
    else:
        effective_tags = ontology.infer_effective_tags(base_tags=base_tags, plaintext=plaintext)
    already_present = {tag for tag in effective_tags if not tag.startswith("@")}
    already_present_casefold = {tag.casefold() for tag in already_present}

    all_terms = search_index.list_non_meta_tag_suggestion_terms()
    has_prefix = prefix != ""

    content_match_scores: Dict[str, TagContentMatch] = {}
    normalized_content = normalize_tag_match_text(plaintext)
    for term in all_terms:
        if term.casefold() in already_present_casefold:
            continue
        if has_prefix and not tag_term_matches_prefix(term=term, prefix=prefix):
            continue
        match = match_tag_term_in_normalized_content(term=term, normalized_content=normalized_content)
        if match is None:
            continue
        content_match_scores[term] = match

    cooccurrence: List[str] = []
    term_count = len(all_terms)
    if term_count > 0:
        query = _build_search_query_for_suggestions(anchors=anchor_list, prefix=prefix)
        cooccurrence = search_index.suggest_tag_completions(query=query, limit=term_count)

    cooccurrence_rank = {term: index for index, term in enumerate(cooccurrence)}
    content_first = list(content_match_scores.keys())

    content_first.sort(
        key=lambda term: (
            -(1 if content_match_scores[term].phrase_match else 0),
            -content_match_scores[term].matched_segment_count,
            -content_match_scores[term].segment_count,
            content_match_scores[term].first_position,
            -content_match_scores[term].normalized_length,
            cooccurrence_rank.get(term, len(cooccurrence)),
            term,
        )
    )

    remaining: List[str] = []
    for term in cooccurrence:
        if term.casefold() in already_present_casefold:
            continue
        if term in content_match_scores:
            continue
        remaining.append(term)

    suggestions = content_first + remaining

    if has_prefix:
        present_suffix: List[str] = []
        exact_tag_counts = search_index.list_tag_frequencies()
        preferred_present_terms = _select_preferred_case_variants(
            terms=already_present,
            exact_tag_counts=exact_tag_counts,
        )
        for term in preferred_present_terms:
            if term.casefold() in anchor_casefold_set:
                continue
            if tag_term_matches_prefix(term=term, prefix=prefix):
                present_suffix.append(term)
        present_suffix.sort()
        suggestions.extend(present_suffix)

    return suggestions


__all__ = ["suggest_tags_for_note"]
