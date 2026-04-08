from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
import time
from typing import Callable, DefaultDict, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from loguru import logger

from app.services.content_formatting import _tokenize_tag_bar, _unwrap_tag_token, list_known_meta_tag_terms
from app.services.search_query import ParsedSearchQuery, parse_search_query
from app.services.tag_term_matching import tag_term_matches_prefix
from app.services.search_text import build_searchable_text_casefold_from_plaintext


_UNICODE_TRIGRAM_SENTINEL = 0xE000
_QUOTE_CHARS = {"'", '"'}


def _parse_search_query_for_suggestions(raw_input: str) -> tuple[Tuple[str, ...], Optional[str]]:
    if not isinstance(raw_input, str):
        raise TypeError(f"raw_input must be a string, got {type(raw_input)}")

    anchors: List[str] = []
    partial_prefix: Optional[str] = None
    has_trailing_whitespace = len(raw_input) > 0 and raw_input[-1].isspace()

    index = 0
    length = len(raw_input)
    while index < length:
        while index < length and raw_input[index].isspace():
            index += 1
        if index >= length:
            break

        prefix: Optional[str] = None
        if raw_input[index] in ("+", "-"):
            prefix = raw_input[index]
            index += 1
            if index >= length or raw_input[index].isspace():
                return tuple(anchors), None

        if raw_input[index] in _QUOTE_CHARS:
            quote_char = raw_input[index]
            index += 1
            closed = False
            while index < length:
                char = raw_input[index]
                if char == quote_char:
                    closed = True
                    index += 1
                    break
                if char == "\\" and index + 1 < length:
                    next_char = raw_input[index + 1]
                    if next_char in (quote_char, "\\"):
                        index += 2
                        continue
                index += 1
            if not closed:
                return tuple(anchors), None
            continue

        start = index
        while index < length and not raw_input[index].isspace():
            index += 1

        token = raw_input[start:index]
        if token == "":
            continue

        is_partial = index >= length and not raw_input[-1].isspace()
        if is_partial:
            partial_prefix = token
            continue

        if prefix == "-":
            continue
        anchors.append(token)

    if partial_prefix is None and has_trailing_whitespace:
        partial_prefix = ""
    return tuple(anchors), partial_prefix


@dataclass(frozen=True, slots=True)
class SearchRecord:
    note_id: str
    content_text: str
    tags: str
    tag_terms: FrozenSet[str]


def _canonical_codepoint(char: str) -> int:
    code = ord(char)
    if code < 128:
        return code
    return _UNICODE_TRIGRAM_SENTINEL


def _trigram_key(a: int, b: int, c: int) -> int:
    return (a << 32) | (b << 16) | c


def _extract_trigram_keys(text_casefold: str) -> Set[int]:
    if not isinstance(text_casefold, str):
        raise TypeError(f"text_casefold must be a string, got {type(text_casefold)}")

    if len(text_casefold) < 3:
        return set()

    keys: Set[int] = set()
    codes: List[int] = [_canonical_codepoint(ch) for ch in text_casefold]
    index = 0
    while index + 2 < len(codes):
        keys.add(_trigram_key(codes[index], codes[index + 1], codes[index + 2]))
        index += 1
    return keys


def extract_tags_for_search(tags: str) -> FrozenSet[str]:
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")

    terms: Set[str] = set()
    for token in _tokenize_tag_bar(tags):
        base, wrapper = _unwrap_tag_token(token)
        if wrapper is None:
            terms.add(base)
            continue
        for inner in base.split():
            if inner:
                terms.add(inner)
    return frozenset(terms)


class SearchIndex:
    """In-memory search index (tags + trigrams) built from current note content."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._revision = 0

        self._uuid_to_id: Dict[str, int] = {}
        self._id_to_uuid: List[str] = []
        self._alive: Set[int] = set()

        self._note_text_casefold: List[str] = []
        self._note_tag_terms: List[FrozenSet[str]] = []
        self._note_tag_terms_casefold: List[FrozenSet[str]] = []
        self._note_trigrams: List[Set[int]] = []

        self._tag_notes: DefaultDict[str, Set[int]] = defaultdict(set)
        self._tag_notes_casefold: DefaultDict[str, Set[int]] = defaultdict(set)
        self._tri_notes: DefaultDict[int, Set[int]] = defaultdict(set)

        self._result_cache: Dict[str, tuple[int, FrozenSet[str]]] = {}

    def rebuild(
        self,
        records: Iterable[SearchRecord],
        *,
        progress_update: Callable[[int], None],
        progress_interval: int,
    ) -> None:
        if progress_interval <= 0:
            raise ValueError("progress_interval must be > 0")
        t0 = time.perf_counter()
        materialized = list(records)
        with self._lock:
            self._uuid_to_id.clear()
            self._id_to_uuid.clear()
            self._alive.clear()
            self._note_text_casefold.clear()
            self._note_tag_terms.clear()
            self._note_tag_terms_casefold.clear()
            self._note_trigrams.clear()
            self._tag_notes.clear()
            self._tag_notes_casefold.clear()
            self._tri_notes.clear()
            self._result_cache.clear()

            self._revision += 1

            processed = 0
            last_reported = 0
            for record in materialized:
                self._insert_new_locked(
                    record.note_id,
                    record.content_text,
                    record.tags,
                    record.tag_terms,
                )
                processed += 1
                if processed - last_reported >= progress_interval:
                    last_reported = processed
                    progress_update(processed)

            if processed != last_reported:
                progress_update(processed)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.bind(
            metrics={
                "elapsed_ms": elapsed_ms,
                "note_count": len(materialized),
                "unique_tag_terms": len(self._tag_notes),
                "unique_trigrams": len(self._tri_notes),
                "revision": self._revision,
            }
        ).info("search.index.rebuild.finish")

    def upsert(self, *, note_id: str, content_text: str, tags: str, tag_terms: FrozenSet[str]) -> None:
        t0 = time.perf_counter()
        with self._lock:
            if note_id in self._uuid_to_id:
                note_int_id = self._uuid_to_id[note_id]
                if note_int_id not in self._alive:
                    # Notes can be deleted and later restored (undo/redo) with the same UUID.
                    # Treat this as a revive instead of an error.
                    self._alive.add(note_int_id)
                self._update_existing_locked(note_int_id, content_text, tags, tag_terms)
            else:
                self._insert_new_locked(note_id, content_text, tags, tag_terms)

            self._revision += 1
            self._result_cache.clear()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.bind(
            metrics={"elapsed_ms": elapsed_ms, "note_id": note_id, "revision": self._revision}
        ).info("search.index.upsert.finish")

    def update_tag_terms(self, *, note_id: str, tag_terms: FrozenSet[str]) -> None:
        self.bulk_update_tag_terms({note_id: tag_terms})

    def bulk_update_tag_terms(self, updates: Dict[str, FrozenSet[str]]) -> None:
        if not updates:
            return

        t0 = time.perf_counter()
        touched = 0
        with self._lock:
            for note_id, new_tag_terms in updates.items():
                note_int_id = self._uuid_to_id.get(note_id)
                if note_int_id is None:
                    continue
                if note_int_id not in self._alive:
                    continue

                old_tag_terms = self._note_tag_terms[note_int_id]
                if old_tag_terms == new_tag_terms:
                    continue

                for term in old_tag_terms:
                    bucket = self._tag_notes.get(term)
                    if bucket is None:
                        continue
                    bucket.discard(note_int_id)
                    folded_bucket = self._tag_notes_casefold.get(term.casefold())
                    if folded_bucket is not None:
                        folded_bucket.discard(note_int_id)
                for term in new_tag_terms:
                    self._tag_notes[term].add(note_int_id)
                    self._tag_notes_casefold[term.casefold()].add(note_int_id)

                self._note_tag_terms[note_int_id] = new_tag_terms
                self._note_tag_terms_casefold[note_int_id] = frozenset(
                    term.casefold() for term in new_tag_terms
                )
                touched += 1

            if touched:
                self._revision += 1
                self._result_cache.clear()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.bind(
            metrics={
                "elapsed_ms": elapsed_ms,
                "revision": self._revision,
                "touched": touched,
                "update_count": len(updates),
            }
        ).info("search.index.bulk_update_tag_terms.finish")

    def remove_many(self, note_ids: Set[str]) -> None:
        if not note_ids:
            return
        t0 = time.perf_counter()
        with self._lock:
            for note_id in note_ids:
                if note_id not in self._uuid_to_id:
                    continue
                note_int_id = self._uuid_to_id[note_id]
                self._remove_existing_locked(note_int_id)

            self._revision += 1
            self._result_cache.clear()

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.bind(
            metrics={"elapsed_ms": elapsed_ms, "count": len(note_ids), "revision": self._revision}
        ).info("search.index.remove_many.finish")

    def list_non_meta_tag_terms(self) -> FrozenSet[str]:
        """Return all tag terms currently indexed (excluding @meta tags)."""
        with self._lock:
            return frozenset(
                term
                for term in self._tag_notes.keys()
                if term and not term.startswith("@")
            )

    def list_non_meta_tag_suggestion_terms(self) -> FrozenSet[str]:
        with self._lock:
            representatives = self._build_suggestion_representatives_locked(
                anchor_casefold_set=frozenset(),
                partial_prefix="",
            )
            return frozenset(representatives.values())

    def list_tag_frequencies(self) -> Dict[str, int]:
        """Return tag term -> note count (excluding @meta tags)."""
        with self._lock:
            return {
                term: len(note_ids)
                for term, note_ids in self._tag_notes.items()
                if term and not term.startswith("@")
            }

    def suggest_tag_completions(self, *, query: str, limit: int) -> List[str]:
        if not isinstance(query, str):
            raise TypeError(f"query must be a string, got {type(query)}")
        if not isinstance(limit, int) or limit <= 0:
            raise TypeError("limit must be a positive integer")

        anchors, partial_prefix = _parse_search_query_for_suggestions(query)
        if partial_prefix is None:
            if query.strip() != "":
                return []
            partial_prefix = ""

        if partial_prefix.startswith("@"):
            with self._lock:
                return self._suggest_meta_tag_completions_locked(
                    partial_prefix=partial_prefix,
                    limit=limit,
                )

        anchor_casefold_set = frozenset(
            anchor.casefold()
            for anchor in anchors
            if anchor and not anchor.startswith("@")
        )

        with self._lock:
            representative_by_casefold = self._build_suggestion_representatives_locked(
                anchor_casefold_set=anchor_casefold_set,
                partial_prefix=partial_prefix,
            )
            candidate_casefolds = list(representative_by_casefold.keys())

            if not candidate_casefolds and partial_prefix != "":
                return []

            if not anchor_casefold_set:
                candidate_casefolds.sort(
                    key=lambda term_casefold: (
                        -len(self._tag_notes_casefold[term_casefold]),
                        *self._suggestion_term_tiebreak_locked(representative_by_casefold[term_casefold]),
                    )
                )
                return [
                    representative_by_casefold[term_casefold]
                    for term_casefold in candidate_casefolds[:limit]
                ]

            note_count = len(self._note_tag_terms)
            anchor_counts = [0] * note_count
            for anchor_casefold in anchor_casefold_set:
                note_ids = self._tag_notes_casefold.get(anchor_casefold)
                if not note_ids:
                    continue
                for note_id in note_ids:
                    if note_id in self._alive:
                        anchor_counts[note_id] += 1

            max_anchor_count = len(anchor_casefold_set)
            counts_by_anchor = [0] * (max_anchor_count + 1)
            for note_id in self._alive:
                count = anchor_counts[note_id]
                if count > max_anchor_count:
                    count = max_anchor_count
                counts_by_anchor[count] += 1

            support_counts = [0] * (max_anchor_count + 1)
            running = 0
            for k in range(max_anchor_count, 0, -1):
                running += counts_by_anchor[k]
                support_counts[k] = running

            scored: List[Tuple[int, float, int, str]] = []
            for term_casefold in candidate_casefolds:
                note_ids = self._tag_notes_casefold.get(term_casefold)
                if not note_ids:
                    continue
                candidate_count = 0
                max_k = 0
                intersection_count = 0
                for note_id in note_ids:
                    if note_id not in self._alive:
                        continue
                    candidate_count += 1
                    count = anchor_counts[note_id]
                    if count > max_k:
                        max_k = count
                        if count > 0:
                            intersection_count = 1
                        else:
                            intersection_count = 0
                    elif count == max_k and count > 0:
                        intersection_count += 1

                if candidate_count == 0:
                    continue

                if max_k == 0 and partial_prefix == "":
                    continue

                jaccard = 0.0
                if max_k > 0:
                    union_count = candidate_count + support_counts[max_k] - intersection_count
                    if union_count > 0:
                        jaccard = intersection_count / union_count

                representative = representative_by_casefold[term_casefold]
                lower_case_penalty, term_tiebreak = self._suggestion_term_tiebreak_locked(representative)
                scored.append((-max_k, -jaccard, lower_case_penalty, term_tiebreak))

            scored.sort()
            return [representative_by_casefold[term.casefold()] for _, __, ___, term in scored[:limit]]
    def query_note_ids(self, search: str) -> Set[str]:
        t0 = time.perf_counter()
        if not isinstance(search, str):
            raise TypeError(f"search must be a string, got {type(search)}")

        with self._lock:
            cached = self._result_cache.get(search)
            if cached is not None:
                cached_revision, cached_results = cached
                if cached_revision == self._revision:
                    total_ms = (time.perf_counter() - t0) * 1000
                    logger.bind(
                        query=search,
                        metrics={
                            "cache_hit": True,
                            "total_ms": total_ms,
                            "revision": self._revision,
                            "matched_count": len(cached_results),
                        },
                    ).info("search.query.finish")
                    return set(cached_results)

        parsed = parse_search_query(search)

        parse_ms = (time.perf_counter() - t0) * 1000

        has_terms = False
        if len(parsed.required_tags) > 0:
            has_terms = True
        if len(parsed.forbidden_tags) > 0:
            has_terms = True
        if len(parsed.required_text) > 0:
            has_terms = True
        if len(parsed.forbidden_text) > 0:
            has_terms = True
        if not has_terms:
            return set()

        t1 = time.perf_counter()
        with self._lock:
            candidate_ids = self._candidate_note_ids_locked(parsed)
            candidate_count = len(candidate_ids)
            if not candidate_ids:
                candidate_ms = (time.perf_counter() - t1) * 1000
                total_ms = (time.perf_counter() - t0) * 1000
                logger.bind(
                    query=search,
                    metrics={
                        "cache_hit": False,
                        "parse_ms": parse_ms,
                        "candidate_ms": candidate_ms,
                        "verify_ms": 0.0,
                        "total_ms": total_ms,
                        "candidate_count": 0,
                        "verified_count": 0,
                        "matched_count": 0,
                        "required_tag_count": len(parsed.required_tags),
                        "forbidden_tag_count": len(parsed.forbidden_tags),
                        "required_text_count": len(parsed.required_text),
                        "forbidden_text_count": len(parsed.forbidden_text),
                        "revision": self._revision,
                    },
                ).info("search.query.finish")
                return set()

            t2 = time.perf_counter()
            matched_note_ids: Set[str] = set()
            verified = 0
            for note_int_id in candidate_ids:
                verified += 1
                if note_int_id not in self._alive:
                    continue
                if not self._verify_note_matches_locked(note_int_id, parsed):
                    continue
                matched_note_ids.add(self._id_to_uuid[note_int_id])

            candidate_ms = (t2 - t1) * 1000
            verify_ms = (time.perf_counter() - t2) * 1000
            total_ms = (time.perf_counter() - t0) * 1000

            frozen = frozenset(matched_note_ids)
            self._result_cache[search] = (self._revision, frozen)

        logger.bind(
            query=search,
            metrics={
                "cache_hit": False,
                "parse_ms": parse_ms,
                "candidate_ms": candidate_ms,
                "verify_ms": verify_ms,
                "total_ms": total_ms,
                "candidate_count": candidate_count,
                "verified_count": verified,
                "matched_count": len(matched_note_ids),
                "required_tag_count": len(parsed.required_tags),
                "forbidden_tag_count": len(parsed.forbidden_tags),
                "required_text_count": len(parsed.required_text),
                "forbidden_text_count": len(parsed.forbidden_text),
                "revision": self._revision,
            },
        ).info("search.query.finish")
        return matched_note_ids

    # Internal ----------------------------------------------------------------

    def _insert_new_locked(
        self,
        note_id: str,
        content_text: str,
        tags: str,
        tag_terms: FrozenSet[str],
    ) -> None:
        note_int_id = len(self._id_to_uuid)
        self._uuid_to_id[note_id] = note_int_id
        self._id_to_uuid.append(note_id)
        self._alive.add(note_int_id)

        text_casefold, trigrams = self._build_note_text_state(content_text, tags)
        self._note_text_casefold.append(text_casefold)
        self._note_tag_terms.append(tag_terms)
        self._note_tag_terms_casefold.append(frozenset(term.casefold() for term in tag_terms))
        self._note_trigrams.append(trigrams)

        for term in tag_terms:
            self._tag_notes[term].add(note_int_id)
            self._tag_notes_casefold[term.casefold()].add(note_int_id)
        for trigram in trigrams:
            self._tri_notes[trigram].add(note_int_id)

    def _update_existing_locked(
        self,
        note_int_id: int,
        content_text: str,
        tags: str,
        new_tag_terms: FrozenSet[str],
    ) -> None:
        if note_int_id not in self._alive:
            raise RuntimeError("Cannot update deleted note")

        new_text_casefold, new_trigrams = self._build_note_text_state(content_text, tags)
        old_tag_terms = self._note_tag_terms[note_int_id]
        old_trigrams = self._note_trigrams[note_int_id]

        if old_tag_terms != new_tag_terms:
            for term in old_tag_terms:
                bucket = self._tag_notes.get(term)
                if bucket is None:
                    continue
                bucket.discard(note_int_id)
                folded_bucket = self._tag_notes_casefold.get(term.casefold())
                if folded_bucket is not None:
                    folded_bucket.discard(note_int_id)
            for term in new_tag_terms:
                self._tag_notes[term].add(note_int_id)
                self._tag_notes_casefold[term.casefold()].add(note_int_id)
            self._note_tag_terms[note_int_id] = new_tag_terms
            self._note_tag_terms_casefold[note_int_id] = frozenset(
                term.casefold() for term in new_tag_terms
            )

        if old_trigrams != new_trigrams:
            for trigram in old_trigrams:
                bucket = self._tri_notes.get(trigram)
                if bucket is None:
                    continue
                bucket.discard(note_int_id)
            for trigram in new_trigrams:
                self._tri_notes[trigram].add(note_int_id)
            self._note_trigrams[note_int_id] = new_trigrams

        self._note_text_casefold[note_int_id] = new_text_casefold

    def _remove_existing_locked(self, note_int_id: int) -> None:
        if note_int_id not in self._alive:
            return
        self._alive.remove(note_int_id)

        for term in self._note_tag_terms[note_int_id]:
            bucket = self._tag_notes.get(term)
            if bucket is None:
                continue
            bucket.discard(note_int_id)
            folded_bucket = self._tag_notes_casefold.get(term.casefold())
            if folded_bucket is not None:
                folded_bucket.discard(note_int_id)
        for trigram in self._note_trigrams[note_int_id]:
            bucket = self._tri_notes.get(trigram)
            if bucket is None:
                continue
            bucket.discard(note_int_id)

        self._note_text_casefold[note_int_id] = ""
        self._note_tag_terms[note_int_id] = frozenset()
        self._note_tag_terms_casefold[note_int_id] = frozenset()
        self._note_trigrams[note_int_id] = set()

    def _build_note_text_state(self, content_text: str, tags: str) -> Tuple[str, Set[int]]:
        if not isinstance(content_text, str):
            raise TypeError(f"content_text must be a string, got {type(content_text)}")
        if not isinstance(tags, str):
            raise TypeError(f"tags must be a string, got {type(tags)}")

        text_casefold = build_searchable_text_casefold_from_plaintext(content_text, tags)
        trigrams = _extract_trigram_keys(text_casefold)
        return text_casefold, trigrams

    def _build_suggestion_representatives_locked(
        self,
        *,
        anchor_casefold_set: FrozenSet[str],
        partial_prefix: str,
    ) -> Dict[str, str]:
        partial_prefix_casefold = partial_prefix.casefold()
        representatives: Dict[str, str] = {}
        for term in self._tag_notes.keys():
            if not term or term.startswith("@"):
                continue
            term_casefold = term.casefold()
            if term_casefold in anchor_casefold_set:
                continue
            if partial_prefix != "" and term_casefold == partial_prefix_casefold:
                continue
            if partial_prefix != "" and not tag_term_matches_prefix(term=term, prefix=partial_prefix):
                continue
            if term_casefold not in representatives:
                representatives[term_casefold] = term
                continue
            current = representatives[term_casefold]
            if self._is_better_suggestion_variant_locked(candidate=term, incumbent=current):
                representatives[term_casefold] = term
        return representatives

    def _is_better_suggestion_variant_locked(self, *, candidate: str, incumbent: str) -> bool:
        candidate_count = len(self._tag_notes[candidate])
        incumbent_count = len(self._tag_notes[incumbent])
        if candidate_count != incumbent_count:
            return candidate_count > incumbent_count
        candidate_penalty, candidate_tiebreak = self._suggestion_term_tiebreak_locked(candidate)
        incumbent_penalty, incumbent_tiebreak = self._suggestion_term_tiebreak_locked(incumbent)
        if candidate_penalty != incumbent_penalty:
            return candidate_penalty < incumbent_penalty
        return candidate_tiebreak < incumbent_tiebreak

    def _suggestion_term_tiebreak_locked(self, term: str) -> Tuple[int, str]:
        lower_case_penalty = 0
        if term != term.casefold():
            lower_case_penalty = 1
        return (lower_case_penalty, term)

    def _suggest_meta_tag_completions_locked(self, *, partial_prefix: str, limit: int) -> List[str]:
        partial_prefix_casefold = partial_prefix.casefold()
        candidates: List[Tuple[int, int, str, str]] = []
        for term in list_known_meta_tag_terms():
            if partial_prefix != "" and term.casefold() == partial_prefix_casefold:
                continue
            if partial_prefix != "" and not term.casefold().startswith(partial_prefix_casefold):
                continue
            usage_count = len(self._tag_notes_casefold.get(term.casefold(), set()))
            lower_case_penalty, term_tiebreak = self._suggestion_term_tiebreak_locked(term)
            candidates.append((-usage_count, lower_case_penalty, term_tiebreak, term))
        candidates.sort()
        return [term for _, __, ___, term in candidates[:limit]]

    def _candidate_note_ids_locked(self, parsed: ParsedSearchQuery) -> Set[int]:
        constraints: List[Set[int]] = []

        for tag in parsed.required_tags:
            posting = self._tag_notes_casefold.get(tag.casefold())
            if posting is None:
                return set()
            constraints.append(posting)

        short_text_terms: List[str] = []
        for term in parsed.required_text:
            term_casefold = term.casefold()
            if len(term_casefold) < 3:
                short_text_terms.append(term_casefold)
                continue
            trigram_keys = _extract_trigram_keys(term_casefold)
            if not trigram_keys:
                continue
            for trigram in trigram_keys:
                posting = self._tri_notes.get(trigram)
                if posting is None:
                    return set()
                constraints.append(posting)

        candidate_ids: Optional[Set[int]] = None
        if constraints:
            ordered = sorted(constraints, key=len)
            candidate_ids = set(ordered[0])
            for constraint in ordered[1:]:
                candidate_ids.intersection_update(constraint)
                if not candidate_ids:
                    return set()

        if candidate_ids is None:
            candidate_ids = set(self._alive)

        if parsed.forbidden_tags:
            for tag in parsed.forbidden_tags:
                posting = self._tag_notes_casefold.get(tag.casefold())
                if posting is None:
                    continue
                candidate_ids.difference_update(posting)

        if short_text_terms:
            verified: Set[int] = set()
            for note_int_id in candidate_ids:
                if note_int_id not in self._alive:
                    continue
                text_casefold = self._note_text_casefold[note_int_id]
                missing = False
                for term in short_text_terms:
                    if term not in text_casefold:
                        missing = True
                        break
                if missing:
                    continue
                verified.add(note_int_id)
            candidate_ids = verified

        return candidate_ids

    def _verify_note_matches_locked(self, note_int_id: int, parsed: ParsedSearchQuery) -> bool:
        text_casefold = self._note_text_casefold[note_int_id]
        for term in parsed.required_text:
            if term.casefold() not in text_casefold:
                return False
        for term in parsed.forbidden_text:
            if term.casefold() in text_casefold:
                return False
        note_tag_terms_casefold = self._note_tag_terms_casefold[note_int_id]
        for tag in parsed.forbidden_tags:
            if tag.casefold() in note_tag_terms_casefold:
                return False
        return True


search_index = SearchIndex()
