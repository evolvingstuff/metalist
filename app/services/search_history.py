from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from threading import RLock
from typing import Optional

from app.db.search_history_sql import (
    delete_all_search_history_rows,
    delete_search_history_rows,
    fetch_all_search_history_rows,
    insert_search_history_row,
    update_search_history_row,
    update_search_history_score_fields,
)
from app.db.session import begin_writer
from app.security.encryption import (
    get_encryption_service,
    get_encryption_service_with_token,
    is_encryption_required,
)
from app.services.search_index import search_index
from app.services.tag_term_matching import tag_term_matches_prefix

SEARCH_HISTORY_DECAY_FACTOR = 0.98
SEARCH_HISTORY_PRIORITY_SLOTS = 3
MAX_SEARCH_HISTORY_ROWS = 500
_SEARCH_HISTORY_PRUNE_SCORE_THRESHOLD = 0.01
_UUID_TERM_RE = re.compile(
    r"^(?:\[\[)?[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}(?:\]\])?$"
)


@dataclass(frozen=True, slots=True)
class NormalizedSearchHistoryQuery:
    query_hash: str
    query_key: str
    root_tag: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchHistoryEntry:
    query_hash: str
    query_key: str
    root_tag: str
    tags: tuple[str, ...]
    score: float
    created_at: datetime
    last_interacted_at: datetime
    updated_at: datetime


class SearchHistoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._stored_rows_by_hash: dict[str, dict[str, object]] = {}
        self._entries_by_hash: dict[str, SearchHistoryEntry] | None = {}

    def bootstrap(self, *, connection) -> None:
        rows = fetch_all_search_history_rows(connection)
        stored_rows_by_hash = _rows_by_hash(rows)
        entries_by_hash = _build_entries_by_hash(
            stored_rows_by_hash=stored_rows_by_hash,
            token="",
            require_success=False,
        )
        with self._lock:
            self._stored_rows_by_hash = stored_rows_by_hash
            self._entries_by_hash = entries_by_hash

    def ensure_decrypted(self, *, token: str) -> None:
        if not isinstance(token, str):
            raise TypeError("token must be a string")
        with self._lock:
            if self._entries_by_hash is not None:
                return
            self._entries_by_hash = _build_entries_by_hash(
                stored_rows_by_hash=self._stored_rows_by_hash,
                token=token,
                require_success=True,
            )

    def reset(self) -> None:
        with self._lock:
            self._stored_rows_by_hash = {}
            self._entries_by_hash = {}

    def clear_persisted_state_for_tests(self) -> None:
        with begin_writer() as connection:
            delete_all_search_history_rows(connection)
        self.reset()

    def record_interaction(self, *, normalized: NormalizedSearchHistoryQuery, token: str) -> bool:
        encryption_service = _resolve_encryption_service(token)
        if encryption_service is None and is_encryption_required():
            raise RuntimeError("Search history interaction requires an active DEK")

        now = datetime.now(timezone.utc)
        encrypted_fields = _serialize_search_history_fields(
            encryption_service=encryption_service,
            normalized=normalized,
        )

        with self._lock:
            self.ensure_decrypted(token=token)
            if self._entries_by_hash is None:
                raise RuntimeError("Search history store must be decrypted before writes")

            entries_by_hash = dict(self._entries_by_hash)
            current_entry = None
            if normalized.query_hash in entries_by_hash:
                current_entry = entries_by_hash[normalized.query_hash]
            updated_entries_by_hash: dict[str, SearchHistoryEntry] = {}
            rows_to_delete: list[str] = []
            score_updates: list[SearchHistoryEntry] = []

            for query_hash, entry in entries_by_hash.items():
                decayed_score = entry.score * SEARCH_HISTORY_DECAY_FACTOR
                if query_hash == normalized.query_hash:
                    continue
                if decayed_score < _SEARCH_HISTORY_PRUNE_SCORE_THRESHOLD:
                    rows_to_delete.append(query_hash)
                    continue
                updated_entry = SearchHistoryEntry(
                    query_hash=entry.query_hash,
                    query_key=entry.query_key,
                    root_tag=entry.root_tag,
                    tags=entry.tags,
                    score=decayed_score,
                    created_at=entry.created_at,
                    last_interacted_at=entry.last_interacted_at,
                    updated_at=now,
                )
                updated_entries_by_hash[query_hash] = updated_entry
                score_updates.append(updated_entry)

            if current_entry is None:
                current_entry = SearchHistoryEntry(
                    query_hash=normalized.query_hash,
                    query_key=normalized.query_key,
                    root_tag=normalized.root_tag,
                    tags=normalized.tags,
                    score=1.0,
                    created_at=now,
                    last_interacted_at=now,
                    updated_at=now,
                )
                row_mode = "insert"
            else:
                current_entry = SearchHistoryEntry(
                    query_hash=current_entry.query_hash,
                    query_key=normalized.query_key,
                    root_tag=normalized.root_tag,
                    tags=normalized.tags,
                    score=(current_entry.score * SEARCH_HISTORY_DECAY_FACTOR) + 1.0,
                    created_at=current_entry.created_at,
                    last_interacted_at=now,
                    updated_at=now,
                )
                row_mode = "update"

            updated_entries_by_hash[normalized.query_hash] = current_entry
            cap_delete_hashes = _select_excess_hashes_for_cap(updated_entries_by_hash)
            for query_hash in cap_delete_hashes:
                updated_entries_by_hash.pop(query_hash)
            rows_to_delete.extend(cap_delete_hashes)

            with begin_writer() as connection:
                if rows_to_delete:
                    delete_search_history_rows(connection, rows_to_delete)
                for entry in score_updates:
                    if entry.query_hash in cap_delete_hashes:
                        continue
                    update_search_history_score_fields(
                        connection,
                        query_hash=entry.query_hash,
                        score=entry.score,
                        updated_at=entry.updated_at,
                    )
                if row_mode == "insert":
                    insert_search_history_row(
                        connection,
                        query_hash=current_entry.query_hash,
                        query_key=encrypted_fields["query_key"],
                        query_key_encryption_nonce=encrypted_fields["query_key_encryption_nonce"],
                        query_key_encryption_tag=encrypted_fields["query_key_encryption_tag"],
                        root_tag=encrypted_fields["root_tag"],
                        root_tag_encryption_nonce=encrypted_fields["root_tag_encryption_nonce"],
                        root_tag_encryption_tag=encrypted_fields["root_tag_encryption_tag"],
                        tags_json=encrypted_fields["tags_json"],
                        tags_json_encryption_nonce=encrypted_fields["tags_json_encryption_nonce"],
                        tags_json_encryption_tag=encrypted_fields["tags_json_encryption_tag"],
                        score=current_entry.score,
                        created_at=current_entry.created_at,
                        last_interacted_at=current_entry.last_interacted_at,
                        updated_at=current_entry.updated_at,
                    )
                else:
                    update_search_history_row(
                        connection,
                        query_hash=current_entry.query_hash,
                        query_key=encrypted_fields["query_key"],
                        query_key_encryption_nonce=encrypted_fields["query_key_encryption_nonce"],
                        query_key_encryption_tag=encrypted_fields["query_key_encryption_tag"],
                        root_tag=encrypted_fields["root_tag"],
                        root_tag_encryption_nonce=encrypted_fields["root_tag_encryption_nonce"],
                        root_tag_encryption_tag=encrypted_fields["root_tag_encryption_tag"],
                        tags_json=encrypted_fields["tags_json"],
                        tags_json_encryption_nonce=encrypted_fields["tags_json_encryption_nonce"],
                        tags_json_encryption_tag=encrypted_fields["tags_json_encryption_tag"],
                        score=current_entry.score,
                        last_interacted_at=current_entry.last_interacted_at,
                        updated_at=current_entry.updated_at,
                    )

            self._entries_by_hash = updated_entries_by_hash
            self._stored_rows_by_hash = _serialize_entries_for_memory(
                entries_by_hash=updated_entries_by_hash,
                encryption_service=encryption_service,
            )

        return True

    def list_recent_tags(self, *, limit: int, token: str) -> list[str]:
        with self._lock:
            self.ensure_decrypted(token=token)
            if self._entries_by_hash is None:
                raise RuntimeError("Search history store must be decrypted before reads")
            entries = list(self._entries_by_hash.values())
        return _list_recent_search_tags_from_entries(entries=entries, limit=limit)

    def rewrite_persisted_entries(
        self,
        *,
        connection,
        encryption_service: object,
        force_plaintext: bool,
    ) -> int:
        service = _coerce_encryption_service(encryption_service)
        if service is None and not force_plaintext:
            raise RuntimeError("Search history encryption migration requires an active DEK")
        if service is None and force_plaintext:
            raise RuntimeError("Search history decryption migration requires an active DEK")

        with self._lock:
            if self._entries_by_hash is None:
                self._entries_by_hash = _build_entries_by_hash(
                    stored_rows_by_hash=self._stored_rows_by_hash,
                    token="",
                    require_success=True,
                )
            if self._entries_by_hash is None:
                raise RuntimeError("Search history store must be decrypted before rewrite")

            rewritten_count = 0
            encryption_target = service
            if force_plaintext:
                encryption_target = None
            stored_rows_by_hash: dict[str, dict[str, object]] = {}
            for entry in self._entries_by_hash.values():
                old_row = self._stored_rows_by_hash.get(entry.query_hash)
                if old_row is not None:
                    if force_plaintext and _row_is_fully_plaintext(old_row):
                        stored_rows_by_hash[entry.query_hash] = old_row
                        continue
                    if not force_plaintext and _row_is_fully_encrypted(old_row):
                        stored_rows_by_hash[entry.query_hash] = old_row
                        continue

                fields = _serialize_search_history_fields(
                    encryption_service=encryption_target,
                    normalized=NormalizedSearchHistoryQuery(
                        query_hash=entry.query_hash,
                        query_key=entry.query_key,
                        root_tag=entry.root_tag,
                        tags=entry.tags,
                    ),
                )
                updated_at = datetime.now(timezone.utc)
                update_search_history_row(
                    connection,
                    query_hash=entry.query_hash,
                    query_key=fields["query_key"],
                    query_key_encryption_nonce=fields["query_key_encryption_nonce"],
                    query_key_encryption_tag=fields["query_key_encryption_tag"],
                    root_tag=fields["root_tag"],
                    root_tag_encryption_nonce=fields["root_tag_encryption_nonce"],
                    root_tag_encryption_tag=fields["root_tag_encryption_tag"],
                    tags_json=fields["tags_json"],
                    tags_json_encryption_nonce=fields["tags_json_encryption_nonce"],
                    tags_json_encryption_tag=fields["tags_json_encryption_tag"],
                    score=entry.score,
                    last_interacted_at=entry.last_interacted_at,
                    updated_at=updated_at,
                )
                stored_rows_by_hash[entry.query_hash] = _build_stored_row(
                    entry=SearchHistoryEntry(
                        query_hash=entry.query_hash,
                        query_key=entry.query_key,
                        root_tag=entry.root_tag,
                        tags=entry.tags,
                        score=entry.score,
                        created_at=entry.created_at,
                        last_interacted_at=entry.last_interacted_at,
                        updated_at=updated_at,
                    ),
                    serialized_fields=fields,
                )
                rewritten_count += 1

            self._stored_rows_by_hash = stored_rows_by_hash
        return rewritten_count


def _build_preferred_case_variant_map(*, exact_tag_counts: dict[str, int]) -> dict[str, str]:
    preferred: dict[str, str] = {}
    for term in exact_tag_counts.keys():
        if term == "" or term.startswith("@"):
            continue
        term_casefold = term.casefold()
        if term_casefold not in preferred:
            preferred[term_casefold] = term
            continue
        current = preferred[term_casefold]
        current_count = exact_tag_counts[current]
        candidate_count = exact_tag_counts[term]
        if candidate_count > current_count:
            preferred[term_casefold] = term
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
            preferred[term_casefold] = term
            continue
        if candidate_penalty == current_penalty and term < current:
            preferred[term_casefold] = term
    return preferred


def normalize_search_history_query(query: str) -> NormalizedSearchHistoryQuery | None:
    if not isinstance(query, str):
        raise TypeError(f"query must be a string, got {type(query)}")

    tags_by_casefold: dict[str, str] = {}
    text = query.strip()
    if text == "":
        return None

    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break

        prefix = ""
        if text[index] in ("+", "-"):
            prefix = text[index]
            index += 1
            if index >= len(text) or text[index].isspace():
                raise ValueError("Dangling prefix in search query")

        if text[index] in ('"', "'"):
            quote_char = text[index]
            index += 1
            while index < len(text):
                char = text[index]
                if char == quote_char:
                    index += 1
                    break
                if char == "\\" and index + 1 < len(text):
                    next_char = text[index + 1]
                    if next_char == quote_char or next_char == "\\":
                        index += 2
                        continue
                index += 1
            else:
                raise ValueError(f"Unclosed quote {quote_char!r} in search query")
            continue

        start = index
        while index < len(text) and not text[index].isspace():
            index += 1
        token = text[start:index]
        if token == "":
            raise ValueError("Empty tag term in search query")
        if prefix == "-":
            continue
        if _UUID_TERM_RE.fullmatch(token) is not None:
            continue
        token_casefold = token.casefold()
        if token_casefold not in tags_by_casefold:
            tags_by_casefold[token_casefold] = token

    if not tags_by_casefold:
        return None

    normalized_tags = tuple(
        tags_by_casefold[key]
        for key in sorted(tags_by_casefold.keys(), key=lambda term: (term, tags_by_casefold[term]))
    )
    query_key = " ".join(normalized_tags)
    return NormalizedSearchHistoryQuery(
        query_hash=_hash_query_key(query_key),
        query_key=query_key,
        root_tag=normalized_tags[0],
        tags=normalized_tags,
    )


def record_search_interaction(*, query: str, interaction_type: str, token: str) -> bool:
    if interaction_type not in {"search", "tag", "scroll", "edit", "command"}:
        raise ValueError(f"Unsupported interaction_type: {interaction_type}")
    if not isinstance(token, str) or token == "":
        raise ValueError("token must be a non-empty string")

    normalized = normalize_search_history_query(query)
    if normalized is None:
        return False
    if len(search_index.query_note_ids(query)) == 0:
        return False

    return search_history_store.record_interaction(
        normalized=normalized,
        token=token,
    )


def list_recent_search_tags(*, limit: int, token: str) -> list[str]:
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if not isinstance(token, str) or token == "":
        raise ValueError("token must be a non-empty string")

    return search_history_store.list_recent_tags(limit=limit, token=token)


def prioritize_blank_search_suggestions(
    *,
    base_suggestions: list[str],
    recent_tags: list[str],
    priority_slots: int,
) -> list[str]:
    return _merge_prioritized_search_suggestions(
        base_suggestions=base_suggestions,
        priority_tags=recent_tags,
        priority_slots=priority_slots,
    )


def is_first_search_tag_suggestion_context(query: str) -> bool:
    return _extract_first_search_tag_prefix(query) is not None


def prioritize_first_search_tag_suggestions(
    *,
    query: str,
    base_suggestions: list[str],
    recent_tags: list[str],
    priority_slots: int,
) -> list[str]:
    prefix = _extract_first_search_tag_prefix(query)
    if prefix is None:
        return _merge_prioritized_search_suggestions(
            base_suggestions=base_suggestions,
            priority_tags=[],
            priority_slots=priority_slots,
        )

    prefix_casefold = prefix.casefold()
    matching_recent_tags = [
        tag
        for tag in recent_tags
        if prefix == ""
        or (tag.casefold() != prefix_casefold and tag_term_matches_prefix(term=tag, prefix=prefix))
    ]
    return _merge_prioritized_search_suggestions(
        base_suggestions=base_suggestions,
        priority_tags=matching_recent_tags,
        priority_slots=priority_slots,
    )


def _extract_first_search_tag_prefix(query: str) -> str | None:
    if not isinstance(query, str):
        raise TypeError(f"query must be a string, got {type(query)}")

    if query.strip() == "":
        return ""

    text = query.lstrip()
    if text[-1].isspace():
        return None
    if any(char.isspace() for char in text):
        return None

    if text[0] in ("+", "-"):
        text = text[1:]
        if text == "":
            return None

    if text[0] in ('"', "'"):
        return None

    return text


def _merge_prioritized_search_suggestions(
    *,
    base_suggestions: list[str],
    priority_tags: list[str],
    priority_slots: int,
) -> list[str]:
    if not isinstance(base_suggestions, list):
        raise TypeError("base_suggestions must be a list")
    if not isinstance(priority_tags, list):
        raise TypeError("priority_tags must be a list")
    if not isinstance(priority_slots, int) or priority_slots < 0:
        raise ValueError("priority_slots must be a non-negative integer")

    prioritized: list[str] = []
    seen_casefold: set[str] = set()

    for tag in priority_tags:
        if not isinstance(tag, str) or tag == "":
            raise TypeError("priority_tags entries must be non-empty strings")
        tag_casefold = tag.casefold()
        if tag_casefold in seen_casefold:
            continue
        seen_casefold.add(tag_casefold)
        prioritized.append(tag)
        if len(prioritized) >= priority_slots:
            break

    merged = list(prioritized)
    for tag in base_suggestions:
        if not isinstance(tag, str) or tag == "":
            raise TypeError("base_suggestions entries must be non-empty strings")
        tag_casefold = tag.casefold()
        if tag_casefold in seen_casefold:
            continue
        seen_casefold.add(tag_casefold)
        merged.append(tag)
    return merged


def encrypt_all_search_history_for_active_dek(*, connection, encryption_service: object) -> int:
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError("Search history encryption migration requires an active DEK")
    return search_history_store.rewrite_persisted_entries(
        connection=connection,
        encryption_service=service,
        force_plaintext=False,
    )


def decrypt_all_search_history_for_plaintext(*, connection, encryption_service: object) -> int:
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError("Search history decryption migration requires an active DEK")
    return search_history_store.rewrite_persisted_entries(
        connection=connection,
        encryption_service=service,
        force_plaintext=True,
    )


def _rows_by_hash(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    rows_by_hash: dict[str, dict[str, object]] = {}
    for row in rows:
        query_hash = row["query_hash"]
        if not isinstance(query_hash, str) or query_hash == "":
            raise TypeError("search_interaction_history.query_hash must be a non-empty string")
        if query_hash in rows_by_hash:
            raise RuntimeError(f"duplicate search history query_hash: {query_hash}")
        rows_by_hash[query_hash] = row
    return rows_by_hash


def _build_entries_by_hash(
    *,
    stored_rows_by_hash: dict[str, dict[str, object]],
    token: str,
    require_success: bool,
) -> dict[str, SearchHistoryEntry] | None:
    service = _resolve_encryption_service(token)
    if service is None:
        has_encrypted_rows = any(_row_is_fully_encrypted(row) for row in stored_rows_by_hash.values())
        if has_encrypted_rows:
            if require_success:
                raise RuntimeError("Search history decryption requires an active DEK")
            return None

    entries_by_hash: dict[str, SearchHistoryEntry] = {}
    for row in stored_rows_by_hash.values():
        entry = _deserialize_search_history_entry(
            encryption_service=service,
            row=row,
        )
        entries_by_hash[entry.query_hash] = entry
    return entries_by_hash


def _serialize_entries_for_memory(
    *,
    entries_by_hash: dict[str, SearchHistoryEntry],
    encryption_service: object,
) -> dict[str, dict[str, object]]:
    stored_rows_by_hash: dict[str, dict[str, object]] = {}
    for entry in entries_by_hash.values():
        fields = _serialize_search_history_fields(
            encryption_service=encryption_service,
            normalized=NormalizedSearchHistoryQuery(
                query_hash=entry.query_hash,
                query_key=entry.query_key,
                root_tag=entry.root_tag,
                tags=entry.tags,
            ),
        )
        stored_rows_by_hash[entry.query_hash] = _build_stored_row(
            entry=entry,
            serialized_fields=fields,
        )
    return stored_rows_by_hash


def _build_stored_row(
    *,
    entry: SearchHistoryEntry,
    serialized_fields: dict[str, object],
) -> dict[str, object]:
    return {
        "query_hash": entry.query_hash,
        "query_key": serialized_fields["query_key"],
        "query_key_encryption_nonce": serialized_fields["query_key_encryption_nonce"],
        "query_key_encryption_tag": serialized_fields["query_key_encryption_tag"],
        "root_tag": serialized_fields["root_tag"],
        "root_tag_encryption_nonce": serialized_fields["root_tag_encryption_nonce"],
        "root_tag_encryption_tag": serialized_fields["root_tag_encryption_tag"],
        "tags_json": serialized_fields["tags_json"],
        "tags_json_encryption_nonce": serialized_fields["tags_json_encryption_nonce"],
        "tags_json_encryption_tag": serialized_fields["tags_json_encryption_tag"],
        "score": entry.score,
        "created_at": entry.created_at,
        "last_interacted_at": entry.last_interacted_at,
        "updated_at": entry.updated_at,
    }


def _select_excess_hashes_for_cap(entries_by_hash: dict[str, SearchHistoryEntry]) -> list[str]:
    if len(entries_by_hash) <= MAX_SEARCH_HISTORY_ROWS:
        return []
    ranked_worst_first = sorted(
        entries_by_hash.values(),
        key=lambda entry: (
            entry.score,
            entry.last_interacted_at.timestamp(),
            entry.updated_at.timestamp(),
            entry.query_key,
            entry.query_hash,
        ),
    )
    excess_count = len(entries_by_hash) - MAX_SEARCH_HISTORY_ROWS
    return [entry.query_hash for entry in ranked_worst_first[:excess_count]]


def _list_recent_search_tags_from_entries(*, entries: list[SearchHistoryEntry], limit: int) -> list[str]:
    exact_tag_counts = search_index.list_tag_frequencies()
    preferred_terms_by_casefold = _build_preferred_case_variant_map(
        exact_tag_counts=exact_tag_counts,
    )
    if not preferred_terms_by_casefold:
        return []

    filtered_entries: list[SearchHistoryEntry] = []
    for entry in entries:
        filtered_tags = tuple(
            preferred_terms_by_casefold[tag.casefold()]
            for tag in entry.tags
            if tag.casefold() in preferred_terms_by_casefold
        )
        if not filtered_tags:
            continue
        filtered_entries.append(
            SearchHistoryEntry(
                query_hash=entry.query_hash,
                query_key=entry.query_key,
                root_tag=entry.root_tag,
                tags=filtered_tags,
                score=entry.score,
                created_at=entry.created_at,
                last_interacted_at=entry.last_interacted_at,
                updated_at=entry.updated_at,
            )
        )

    filtered_entries.sort(
        key=lambda entry: (
            -entry.score,
            -entry.last_interacted_at.timestamp(),
            entry.query_key,
        )
    )

    tag_scores_by_casefold: dict[str, float] = {}
    tag_last_interacted_at_by_casefold: dict[str, float] = {}
    tag_display_by_casefold: dict[str, str] = {}
    tag_first_seen_order_by_casefold: dict[str, int] = {}
    next_tag_order = 0
    for entry in filtered_entries:
        seen_casefold_in_entry: set[str] = set()
        for tag in entry.tags:
            tag_casefold = tag.casefold()
            if tag_casefold in seen_casefold_in_entry:
                continue
            seen_casefold_in_entry.add(tag_casefold)
            if tag_casefold in tag_scores_by_casefold:
                tag_scores_by_casefold[tag_casefold] += entry.score
            else:
                tag_scores_by_casefold[tag_casefold] = entry.score
            entry_last_interacted_at = entry.last_interacted_at.timestamp()
            if tag_casefold not in tag_last_interacted_at_by_casefold:
                tag_last_interacted_at_by_casefold[tag_casefold] = entry_last_interacted_at
            elif entry_last_interacted_at > tag_last_interacted_at_by_casefold[tag_casefold]:
                tag_last_interacted_at_by_casefold[tag_casefold] = entry_last_interacted_at
            tag_display_by_casefold[tag_casefold] = tag
            if tag_casefold not in tag_first_seen_order_by_casefold:
                tag_first_seen_order_by_casefold[tag_casefold] = next_tag_order
                next_tag_order += 1

    ranked_casefolds = sorted(
        tag_scores_by_casefold.keys(),
        key=lambda tag_casefold: (
            -tag_scores_by_casefold[tag_casefold],
            -tag_last_interacted_at_by_casefold[tag_casefold],
            tag_first_seen_order_by_casefold[tag_casefold],
        ),
    )
    return [tag_display_by_casefold[tag_casefold] for tag_casefold in ranked_casefolds[:limit]]


def _hash_query_key(query_key: str) -> str:
    digest = hashlib.sha256(query_key.encode("utf-8")).hexdigest()
    assert digest != ""
    return digest


def _serialize_search_history_fields(
    *,
    encryption_service: object,
    normalized: NormalizedSearchHistoryQuery,
) -> dict[str, object]:
    tags_json = json.dumps(list(normalized.tags), separators=(",", ":"), ensure_ascii=False)
    query_key, query_key_nonce, query_key_tag = _encrypt_text_for_storage(
        encryption_service=encryption_service,
        plaintext=normalized.query_key,
    )
    root_tag, root_tag_nonce, root_tag_tag = _encrypt_text_for_storage(
        encryption_service=encryption_service,
        plaintext=normalized.root_tag,
    )
    encoded_tags_json, tags_json_nonce, tags_json_tag = _encrypt_text_for_storage(
        encryption_service=encryption_service,
        plaintext=tags_json,
    )
    return {
        "query_key": query_key,
        "query_key_encryption_nonce": query_key_nonce,
        "query_key_encryption_tag": query_key_tag,
        "root_tag": root_tag,
        "root_tag_encryption_nonce": root_tag_nonce,
        "root_tag_encryption_tag": root_tag_tag,
        "tags_json": encoded_tags_json,
        "tags_json_encryption_nonce": tags_json_nonce,
        "tags_json_encryption_tag": tags_json_tag,
    }


def _deserialize_search_history_entry(
    *,
    encryption_service: object,
    row: dict[str, object],
) -> SearchHistoryEntry:
    query_hash = row["query_hash"]
    if not isinstance(query_hash, str) or query_hash == "":
        raise TypeError("search_interaction_history.query_hash must be a non-empty string")

    query_key = _decrypt_text_field(
        encryption_service=encryption_service,
        value=row["query_key"],
        nonce=row["query_key_encryption_nonce"],
        tag=row["query_key_encryption_tag"],
        field_name="query_key",
        query_hash=query_hash,
    )
    root_tag = _decrypt_text_field(
        encryption_service=encryption_service,
        value=row["root_tag"],
        nonce=row["root_tag_encryption_nonce"],
        tag=row["root_tag_encryption_tag"],
        field_name="root_tag",
        query_hash=query_hash,
    )
    tags_json = _decrypt_text_field(
        encryption_service=encryption_service,
        value=row["tags_json"],
        nonce=row["tags_json_encryption_nonce"],
        tag=row["tags_json_encryption_tag"],
        field_name="tags_json",
        query_hash=query_hash,
    )
    tags_payload = json.loads(tags_json)
    if not isinstance(tags_payload, list):
        raise TypeError(f"search_interaction_history.tags_json must decode to a list: query_hash={query_hash}")
    tags: list[str] = []
    for tag in tags_payload:
        if not isinstance(tag, str) or tag == "":
            raise TypeError(f"search_interaction_history.tags_json contains invalid tag: query_hash={query_hash}")
        tags.append(tag)

    score = row["score"]
    if not isinstance(score, float):
        raise TypeError(f"search_interaction_history.score must be a float: {type(score)}")

    created_at = row["created_at"]
    last_interacted_at = row["last_interacted_at"]
    updated_at = row["updated_at"]
    if not isinstance(created_at, datetime):
        raise TypeError("search_interaction_history.created_at must be datetime")
    if not isinstance(last_interacted_at, datetime):
        raise TypeError("search_interaction_history.last_interacted_at must be datetime")
    if not isinstance(updated_at, datetime):
        raise TypeError("search_interaction_history.updated_at must be datetime")

    return SearchHistoryEntry(
        query_hash=query_hash,
        query_key=query_key,
        root_tag=root_tag,
        tags=tuple(tags),
        score=score,
        created_at=created_at,
        last_interacted_at=last_interacted_at,
        updated_at=updated_at,
    )


def _row_is_fully_plaintext(row: dict[str, object]) -> bool:
    return (
        _field_has_encryption(
            nonce=row["query_key_encryption_nonce"],
            tag=row["query_key_encryption_tag"],
            query_hash=row["query_hash"],
            field_name="query_key",
        )
        is False
        and _field_has_encryption(
            nonce=row["root_tag_encryption_nonce"],
            tag=row["root_tag_encryption_tag"],
            query_hash=row["query_hash"],
            field_name="root_tag",
        )
        is False
        and _field_has_encryption(
            nonce=row["tags_json_encryption_nonce"],
            tag=row["tags_json_encryption_tag"],
            query_hash=row["query_hash"],
            field_name="tags_json",
        )
        is False
    )


def _row_is_fully_encrypted(row: dict[str, object]) -> bool:
    return (
        _field_has_encryption(
            nonce=row["query_key_encryption_nonce"],
            tag=row["query_key_encryption_tag"],
            query_hash=row["query_hash"],
            field_name="query_key",
        )
        is True
        and _field_has_encryption(
            nonce=row["root_tag_encryption_nonce"],
            tag=row["root_tag_encryption_tag"],
            query_hash=row["query_hash"],
            field_name="root_tag",
        )
        is True
        and _field_has_encryption(
            nonce=row["tags_json_encryption_nonce"],
            tag=row["tags_json_encryption_tag"],
            query_hash=row["query_hash"],
            field_name="tags_json",
        )
        is True
    )


def _field_has_encryption(*, nonce: object, tag: object, query_hash: object, field_name: str) -> bool:
    if nonce is None and tag is None:
        return False
    if not isinstance(nonce, bytes) or not isinstance(tag, bytes):
        raise RuntimeError(
            "Encrypted search history field metadata invalid: "
            f"query_hash={query_hash} field={field_name} nonce={nonce is not None} tag={tag is not None}"
        )
    return True


def _resolve_encryption_service(token: Optional[str]):
    service = None
    if token is not None and token != "":
        service = get_encryption_service_with_token(token)
    if service is None:
        service = get_encryption_service()
    return service


def _encrypt_text_for_storage(
    *,
    encryption_service: object,
    plaintext: str,
) -> tuple[str, Optional[bytes], Optional[bytes]]:
    if not isinstance(plaintext, str):
        raise TypeError(f"plaintext must be a string, got {type(plaintext)}")

    service = _coerce_encryption_service(encryption_service)
    if service is None:
        return plaintext, None, None
    return service.encrypt_for_storage(plaintext)


def _decrypt_text_field(
    *,
    encryption_service: object,
    value: object,
    nonce: object,
    tag: object,
    field_name: str,
    query_hash: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"search_interaction_history.{field_name} must be a string: query_hash={query_hash}")
    if nonce is None and tag is None:
        return value
    if (nonce is None) != (tag is None):
        raise RuntimeError(
            "Encrypted search history metadata missing: "
            f"query_hash={query_hash} field={field_name} nonce={nonce is not None} tag={tag is not None}"
        )
    if not isinstance(nonce, bytes) or not isinstance(tag, bytes):
        raise RuntimeError(
            "Encrypted search history metadata invalid: "
            f"query_hash={query_hash} field={field_name}"
        )

    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError(f"Encrypted search history requires an active DEK: query_hash={query_hash}")
    return service.decrypt_from_storage(value, nonce, tag)


def _coerce_encryption_service(encryption_service: object):
    if encryption_service is None:
        return None
    dek = getattr(encryption_service, "dek", None)
    if not isinstance(dek, bytes):
        return None
    return encryption_service


search_history_store = SearchHistoryStore()
