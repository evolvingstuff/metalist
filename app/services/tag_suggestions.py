from __future__ import annotations

from collections import Counter
from typing import Dict, FrozenSet, Iterable, List, Tuple

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
        current_count = 0
        if current in exact_tag_counts:
            current_count = exact_tag_counts[current]
        candidate_count = 0
        if term in exact_tag_counts:
            candidate_count = exact_tag_counts[term]
        if candidate_count > current_count:
            by_casefold[term_casefold] = term
            continue
        if candidate_count < current_count:
            continue
        current_penalty = 1
        if current == current.casefold():
            current_penalty = 0
        candidate_penalty = 1
        if term == term.casefold():
            candidate_penalty = 0
        if candidate_penalty < current_penalty:
            by_casefold[term_casefold] = term
            continue
        if candidate_penalty == current_penalty and term < current:
            by_casefold[term_casefold] = term
    return list(by_casefold.values())


def _sanitize_tag_terms(*, tags: Iterable[str], field_name: str) -> List[str]:
    if tags is None:
        raise TypeError(f"{field_name} must be provided")

    cleaned: List[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError(f"{field_name} must be strings")
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


def _build_cooccurrence_query_anchors(
    *,
    explicit_anchors: Iterable[str],
    inherited_non_meta: Iterable[str],
) -> List[str]:
    merged: List[str] = []
    seen_casefold: set[str] = set()

    for tag in explicit_anchors:
        tag_casefold = tag.casefold()
        if tag_casefold in seen_casefold:
            continue
        seen_casefold.add(tag_casefold)
        merged.append(tag)

    for tag in sorted(inherited_non_meta, key=lambda value: (value.casefold(), value)):
        if tag.startswith("@"):
            continue
        tag_casefold = tag.casefold()
        if tag_casefold in seen_casefold:
            continue
        seen_casefold.add(tag_casefold)
        merged.append(tag)

    return merged


def _score_content_match(match: TagContentMatch) -> int:
    if not isinstance(match, TagContentMatch):
        raise TypeError("match must be a TagContentMatch")

    score = 0
    if match.phrase_match:
        score += 1000
    score += match.matched_segment_count * 100
    score += match.segment_count * 10
    score += max(0, 100 - min(match.first_position, 100))
    score += match.normalized_length
    return score


def _get_note_record_or_none(note_id: str):
    if not hasattr(note_store, "get_note"):
        return None
    if hasattr(note_store, "has_note") and not note_store.has_note(note_id):
        return None
    return note_store.get_note(note_id)


def _can_iterate_saved_notes() -> bool:
    return hasattr(note_store, "list_note_ids") and hasattr(note_store, "get_note")


def _list_saved_note_ids() -> List[str]:
    if not _can_iterate_saved_notes():
        return []
    note_ids = note_store.list_note_ids()
    if not isinstance(note_ids, list):
        raise TypeError("note_store.list_note_ids() must return a list")
    return note_ids


def _suggestion_tiebreak(term: str) -> Tuple[int, str]:
    lower_case_penalty = 1
    if term == term.casefold():
        lower_case_penalty = 0
    return (lower_case_penalty, term)


def _lookup_count(counts: Dict[str, int], term: str) -> int:
    if term in counts:
        return counts[term]
    return 0


def _collect_explicit_tag_statistics() -> Tuple[List[str], Dict[str, int]]:
    if not _can_iterate_saved_notes():
        exact_tag_counts = search_index.list_tag_frequencies()
        all_terms = list(search_index.list_non_meta_tag_suggestion_terms())
        all_terms.sort(
            key=lambda term: (
                -_lookup_count(exact_tag_counts, term),
                *_suggestion_tiebreak(term),
            )
        )
        return all_terms, exact_tag_counts

    exact_tag_counts: Counter[str] = Counter()
    for note_id in _list_saved_note_ids():
        record = note_store.get_note(note_id)
        for tag in record.non_meta_tag_terms:
            if tag:
                exact_tag_counts[tag] += 1

    preferred_terms = _select_preferred_case_variants(
        terms=exact_tag_counts.keys(),
        exact_tag_counts=dict(exact_tag_counts),
    )
    representative_by_casefold = {term.casefold(): term for term in preferred_terms}
    representative_counts: Counter[str] = Counter()
    for term, count in exact_tag_counts.items():
        representative = representative_by_casefold[term.casefold()]
        representative_counts[representative] += count

    all_terms = list(representative_counts.keys())
    all_terms.sort(
        key=lambda term: (
            -representative_counts[term],
            *_suggestion_tiebreak(term),
        )
    )
    return all_terms, dict(representative_counts)


def _build_saved_note_effective_non_meta_tags(
    *,
    note_id: str,
    ontology,
) -> FrozenSet[str]:
    if not _can_iterate_saved_notes():
        return frozenset()

    record = note_store.get_note(note_id)
    inherited_non_meta = note_store.get_inherited_non_meta_tag_terms(note_id)
    base_tags = frozenset(record.non_meta_tag_terms | inherited_non_meta)
    if ontology.is_empty:
        return base_tags
    inferred = ontology.infer_effective_tags(
        base_tags=base_tags,
        plaintext=strip_html(record.content),
    )
    return frozenset(tag for tag in inferred if not tag.startswith("@"))


def _list_subtree_note_ids(note_id: str) -> List[str]:
    if not hasattr(note_store, "get_children"):
        return []

    ordered: List[str] = []
    seen: set[str] = set()
    to_visit: List[str] = [note_id]
    while to_visit:
        current_id = to_visit.pop()
        if current_id in seen:
            continue
        seen.add(current_id)
        if _get_note_record_or_none(current_id) is None:
            continue
        ordered.append(current_id)
        child_ids = note_store.get_children(current_id)
        for child_id in reversed(child_ids):
            to_visit.append(child_id)
    return ordered


def _list_ancestor_note_ids(note_id: str) -> List[str]:
    ancestors: List[str] = []
    seen: set[str] = set()
    current_id = note_id
    while True:
        record = _get_note_record_or_none(current_id)
        if record is None or record.parent_id is None:
            return ancestors
        parent_id = record.parent_id
        if parent_id in seen:
            raise RuntimeError(f"Cycle detected while collecting ancestors for {note_id}")
        seen.add(parent_id)
        ancestors.append(parent_id)
        current_id = parent_id


def _summarize_note_group(note_ids: Iterable[str]) -> tuple[Counter[str], str]:
    explicit_counts: Counter[str] = Counter()
    plaintext_parts: List[str] = []
    for note_id in note_ids:
        record = _get_note_record_or_none(note_id)
        if record is None:
            continue
        plaintext = strip_html(record.content)
        if plaintext:
            plaintext_parts.append(plaintext)
        for tag in record.non_meta_tag_terms:
            if tag:
                explicit_counts[tag] += 1
    return explicit_counts, normalize_tag_match_text(" ".join(plaintext_parts))


def _collect_content_match_scores(
    *,
    candidate_terms: Iterable[str],
    normalized_content: str,
) -> Dict[str, TagContentMatch]:
    if normalized_content == "":
        return {}

    matches: Dict[str, TagContentMatch] = {}
    for term in candidate_terms:
        match = match_tag_term_in_normalized_content(term=term, normalized_content=normalized_content)
        if match is None:
            continue
        matches[term] = match
    return matches


def _rank_terms_by_local_context(
    *,
    note_id: str,
    candidate_terms: List[str],
    cooccurrence_rank: Dict[str, int],
) -> List[str]:
    current_record = _get_note_record_or_none(note_id)
    if current_record is None:
        return []

    candidate_by_casefold = {term.casefold(): term for term in candidate_terms}
    local_scores: Counter[str] = Counter()

    current_note_content_matches = _collect_content_match_scores(
        candidate_terms=candidate_terms,
        normalized_content=normalize_tag_match_text(strip_html(current_record.content)),
    )
    for term, match in current_note_content_matches.items():
        local_scores[term] += 20000 + _score_content_match(match)

    current_subtree_ids = _list_subtree_note_ids(note_id)
    descendant_ids = [candidate_id for candidate_id in current_subtree_ids if candidate_id != note_id]
    descendant_explicit_counts, descendant_content = _summarize_note_group(descendant_ids)
    for term, count in descendant_explicit_counts.items():
        canonical_term = candidate_by_casefold.get(term.casefold())
        if canonical_term is None:
            continue
        local_scores[canonical_term] += 12000 + (count * 200)
    descendant_content_matches = _collect_content_match_scores(
        candidate_terms=candidate_terms,
        normalized_content=descendant_content,
    )
    for term, match in descendant_content_matches.items():
        local_scores[term] += 9000 + _score_content_match(match)

    sibling_subtree_ids: List[str] = []
    if current_record.parent_id is not None:
        parent_subtree_ids = _list_subtree_note_ids(current_record.parent_id)
        current_subtree_set = set(current_subtree_ids)
        sibling_subtree_ids = [
            candidate_id for candidate_id in parent_subtree_ids
            if candidate_id not in current_subtree_set
        ]
    sibling_explicit_counts, sibling_content = _summarize_note_group(sibling_subtree_ids)
    for term, count in sibling_explicit_counts.items():
        canonical_term = candidate_by_casefold.get(term.casefold())
        if canonical_term is None:
            continue
        local_scores[canonical_term] += 6000 + (count * 150)
    sibling_content_matches = _collect_content_match_scores(
        candidate_terms=candidate_terms,
        normalized_content=sibling_content,
    )
    for term, match in sibling_content_matches.items():
        local_scores[term] += 4500 + _score_content_match(match)

    ancestor_ids = _list_ancestor_note_ids(note_id)
    _, ancestor_content = _summarize_note_group(ancestor_ids)
    ancestor_content_matches = _collect_content_match_scores(
        candidate_terms=candidate_terms,
        normalized_content=ancestor_content,
    )
    for term, match in ancestor_content_matches.items():
        local_scores[term] += 1500 + _score_content_match(match)

    ranked_terms = [term for term in candidate_terms if local_scores[term] > 0]
    ranked_terms.sort(
        key=lambda term: (
            -local_scores[term],
            cooccurrence_rank.get(term, len(cooccurrence_rank)),
            term,
        )
    )
    return ranked_terms


def _rank_terms_by_context_overlap(
    *,
    note_id: str,
    candidate_terms: List[str],
    current_effective_tags: FrozenSet[str],
    exact_tag_counts: Dict[str, int],
) -> List[str]:
    if not _can_iterate_saved_notes():
        return []
    if not current_effective_tags:
        return []

    ontology = get_ontology()
    current_effective_casefold = {tag.casefold() for tag in current_effective_tags}
    candidate_by_casefold = {term.casefold(): term for term in candidate_terms}
    overlap_max_by_term: Dict[str, int] = {}
    overlap_support_by_term: Counter[str] = Counter()

    for other_note_id in _list_saved_note_ids():
        if other_note_id == note_id:
            continue
        record = note_store.get_note(other_note_id)
        if not record.non_meta_tag_terms:
            continue

        other_effective_tags = _build_saved_note_effective_non_meta_tags(
            note_id=other_note_id,
            ontology=ontology,
        )
        if not other_effective_tags:
            continue
        other_effective_casefold = {tag.casefold() for tag in other_effective_tags}
        overlap_count = len(current_effective_casefold & other_effective_casefold)
        if overlap_count <= 0:
            continue

        for explicit_tag in record.non_meta_tag_terms:
            canonical_term = candidate_by_casefold.get(explicit_tag.casefold())
            if canonical_term is None:
                continue
            previous_max = 0
            if canonical_term in overlap_max_by_term:
                previous_max = overlap_max_by_term[canonical_term]
            if overlap_count > previous_max:
                overlap_max_by_term[canonical_term] = overlap_count
                overlap_support_by_term[canonical_term] = 1
                continue
            if overlap_count == previous_max:
                overlap_support_by_term[canonical_term] += 1

    ranked_terms = list(overlap_max_by_term.keys())
    ranked_terms.sort(
        key=lambda term: (
            -overlap_max_by_term[term],
            -overlap_support_by_term[term],
            -_lookup_count(exact_tag_counts, term),
            *_suggestion_tiebreak(term),
        )
    )
    return ranked_terms


def suggest_tags_for_note(
    *,
    note_id: str,
    anchors: Iterable[str],
    explicit_tags: Iterable[str],
    prefix: str,
    content_html: str,
) -> List[str]:
    if not isinstance(note_id, str) or not note_id:
        raise TypeError("note_id must be a non-empty string")
    if not isinstance(prefix, str):
        raise TypeError("prefix must be a string")
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")

    anchor_list = _sanitize_tag_terms(tags=anchors, field_name="anchors")
    explicit_tag_list = _sanitize_tag_terms(tags=explicit_tags, field_name="explicit_tags")
    anchor_set = {tag for tag in anchor_list if not tag.startswith("@")}
    explicit_tag_casefold_set = {tag.casefold() for tag in explicit_tag_list if not tag.startswith("@")}

    inherited_non_meta = note_store.get_inherited_non_meta_tag_terms(note_id)
    base_tags = frozenset(anchor_set | inherited_non_meta)

    plaintext = strip_html(content_html)
    ontology = get_ontology()
    if ontology.is_empty:
        effective_tags = base_tags
    else:
        effective_tags = ontology.infer_effective_tags(base_tags=base_tags, plaintext=plaintext)
    inherited_or_inferred_tags = {
        tag for tag in effective_tags
        if not tag.startswith("@") and tag.casefold() not in explicit_tag_casefold_set
    }
    suppressed_casefold = set(explicit_tag_casefold_set)
    suppressed_casefold.update(tag.casefold() for tag in inherited_or_inferred_tags)

    all_terms, exact_tag_counts = _collect_explicit_tag_statistics()
    has_prefix = prefix != ""

    if has_prefix and prefix.startswith("@"):
        meta_query = _build_search_query_for_suggestions(anchors=anchor_list, prefix=prefix)
        meta_suggestions = search_index.suggest_tag_completions(query=meta_query, limit=100)
        return meta_suggestions

    normalized_content = normalize_tag_match_text(plaintext)
    candidate_terms: List[str] = []
    for term in all_terms:
        if term.casefold() in suppressed_casefold:
            continue
        if has_prefix and not tag_term_matches_prefix(term=term, prefix=prefix):
            continue
        candidate_terms.append(term)

    content_match_scores = _collect_content_match_scores(
        candidate_terms=candidate_terms,
        normalized_content=normalized_content,
    )

    cooccurrence_rank: Dict[str, int] = {}
    cooccurrence: List[str] = []
    if not _can_iterate_saved_notes():
        term_count = len(all_terms)
        if term_count > 0:
            cooccurrence_query_anchors = _build_cooccurrence_query_anchors(
                explicit_anchors=anchor_list,
                inherited_non_meta=inherited_non_meta,
            )
            query = _build_search_query_for_suggestions(
                anchors=cooccurrence_query_anchors,
                prefix=prefix,
            )
            cooccurrence = search_index.suggest_tag_completions(query=query, limit=term_count)
            cooccurrence = [
                term for term in cooccurrence
                if term.casefold() in {candidate.casefold() for candidate in candidate_terms}
            ]
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
    local_first = _rank_terms_by_local_context(
        note_id=note_id,
        candidate_terms=candidate_terms,
        cooccurrence_rank=cooccurrence_rank,
    )
    overlap_first = _rank_terms_by_context_overlap(
        note_id=note_id,
        candidate_terms=candidate_terms,
        current_effective_tags=frozenset(
            tag for tag in effective_tags
            if not tag.startswith("@")
        ),
        exact_tag_counts=exact_tag_counts,
    )

    remaining: List[str] = []
    seen_terms = set(content_first)
    for term in local_first:
        if term in seen_terms:
            continue
        seen_terms.add(term)
    for term in overlap_first:
        if term in seen_terms:
            continue
        seen_terms.add(term)
    for term in cooccurrence:
        if term in seen_terms:
            continue
        if term.casefold() in suppressed_casefold:
            continue
        if has_prefix and not tag_term_matches_prefix(term=term, prefix=prefix):
            continue
        remaining.append(term)
        seen_terms.add(term)

    for term in candidate_terms:
        if term in seen_terms:
            continue
        remaining.append(term)
        seen_terms.add(term)

    hierarchy_only = [term for term in local_first if term not in content_first]
    overlap_only = [
        term for term in overlap_first
        if term not in content_first and term not in hierarchy_only
    ]
    suggestions = content_first + hierarchy_only + overlap_only + remaining

    if has_prefix:
        present_suffix: List[str] = []
        preferred_present_terms = _select_preferred_case_variants(
            terms=inherited_or_inferred_tags,
            exact_tag_counts=exact_tag_counts,
        )
        for term in preferred_present_terms:
            if tag_term_matches_prefix(term=term, prefix=prefix):
                present_suffix.append(term)
        present_suffix.sort()
        suggestions.extend(present_suffix)

    return suggestions


__all__ = ["suggest_tags_for_note"]
