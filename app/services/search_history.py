from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Optional

from app.db.search_history_session import begin_search_history_writer, connect_search_history_reader
from app.db.search_history_sql import (
    delete_search_history_rows,
    fetch_all_search_history_rows,
    insert_search_history_row,
    update_search_history_row,
    update_search_history_score_fields,
)
from app.security.encryption import (
    get_encryption_service,
    get_encryption_service_with_token,
    is_encryption_required,
)
from app.services.search_index import search_index

SEARCH_HISTORY_DECAY_FACTOR = 0.98
SEARCH_HISTORY_PRIORITY_SLOTS = 3
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

    tags: list[str] = []
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
        tags.append(token)

    if not tags:
        return None

    normalized_tags = tuple(tags)
    query_key = " ".join(normalized_tags)
    return NormalizedSearchHistoryQuery(
        query_hash=_hash_query_key(query_key),
        query_key=query_key,
        root_tag=normalized_tags[0],
        tags=normalized_tags,
    )


def record_search_interaction(*, query: str, interaction_type: str, token: str) -> bool:
    if interaction_type not in {"scroll", "edit", "command"}:
        raise ValueError(f"Unsupported interaction_type: {interaction_type}")
    if not isinstance(token, str) or token == "":
        raise ValueError("token must be a non-empty string")

    normalized = normalize_search_history_query(query)
    if normalized is None:
        return False
    if len(search_index.query_note_ids(query)) == 0:
        return False

    encryption_service = _resolve_encryption_service(token)
    if encryption_service is None and is_encryption_required():
        raise RuntimeError("Search history interaction requires an active DEK")

    now = datetime.now(timezone.utc)
    encrypted_fields = _serialize_search_history_fields(
        encryption_service=encryption_service,
        normalized=normalized,
    )

    with begin_search_history_writer() as connection:
        rows = fetch_all_search_history_rows(connection)
        current_row: dict[str, object] | None = None
        rows_to_delete: list[str] = []

        for row in rows:
            row_hash = row["query_hash"]
            if not isinstance(row_hash, str) or row_hash == "":
                raise TypeError("search_interaction_history.query_hash must be a non-empty string")
            score = row["score"]
            if not isinstance(score, float):
                raise TypeError(f"search_interaction_history.score must be a float: {type(score)}")

            decayed_score = score * SEARCH_HISTORY_DECAY_FACTOR
            if row_hash == normalized.query_hash:
                current_row = row
                current_row["score"] = decayed_score
                continue
            if decayed_score < _SEARCH_HISTORY_PRUNE_SCORE_THRESHOLD:
                rows_to_delete.append(row_hash)
                continue
            update_search_history_score_fields(
                connection,
                query_hash=row_hash,
                score=decayed_score,
                updated_at=now,
            )

        if rows_to_delete:
            delete_search_history_rows(connection, rows_to_delete)

        if current_row is None:
            insert_search_history_row(
                connection,
                query_hash=normalized.query_hash,
                query_key=encrypted_fields["query_key"],
                query_key_encryption_nonce=encrypted_fields["query_key_encryption_nonce"],
                query_key_encryption_tag=encrypted_fields["query_key_encryption_tag"],
                root_tag=encrypted_fields["root_tag"],
                root_tag_encryption_nonce=encrypted_fields["root_tag_encryption_nonce"],
                root_tag_encryption_tag=encrypted_fields["root_tag_encryption_tag"],
                tags_json=encrypted_fields["tags_json"],
                tags_json_encryption_nonce=encrypted_fields["tags_json_encryption_nonce"],
                tags_json_encryption_tag=encrypted_fields["tags_json_encryption_tag"],
                score=1.0,
                created_at=now,
                last_interacted_at=now,
                updated_at=now,
            )
            return True

        current_score = current_row["score"]
        if not isinstance(current_score, float):
            raise TypeError(f"search_interaction_history.score must be a float: {type(current_score)}")
        update_search_history_row(
            connection,
            query_hash=normalized.query_hash,
            query_key=encrypted_fields["query_key"],
            query_key_encryption_nonce=encrypted_fields["query_key_encryption_nonce"],
            query_key_encryption_tag=encrypted_fields["query_key_encryption_tag"],
            root_tag=encrypted_fields["root_tag"],
            root_tag_encryption_nonce=encrypted_fields["root_tag_encryption_nonce"],
            root_tag_encryption_tag=encrypted_fields["root_tag_encryption_tag"],
            tags_json=encrypted_fields["tags_json"],
            tags_json_encryption_nonce=encrypted_fields["tags_json_encryption_nonce"],
            tags_json_encryption_tag=encrypted_fields["tags_json_encryption_tag"],
            score=current_score + 1.0,
            last_interacted_at=now,
            updated_at=now,
        )
    return True


def list_recent_search_tags(*, limit: int, token: str) -> list[str]:
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if not isinstance(token, str) or token == "":
        raise ValueError("token must be a non-empty string")

    exact_tag_counts = search_index.list_tag_frequencies()
    preferred_terms_by_casefold = _build_preferred_case_variant_map(
        exact_tag_counts=exact_tag_counts,
    )
    if not preferred_terms_by_casefold:
        return []

    service = _resolve_encryption_service(token)
    with connect_search_history_reader() as connection:
        rows = fetch_all_search_history_rows(connection)

    entries: list[SearchHistoryEntry] = []
    for row in rows:
        entry = _deserialize_search_history_entry(
            encryption_service=service,
            row=row,
        )
        filtered_tags = tuple(
            preferred_terms_by_casefold[tag.casefold()]
            for tag in entry.tags
            if tag.casefold() in preferred_terms_by_casefold
        )
        if not filtered_tags:
            continue
        entries.append(
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

    entries.sort(
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
    for entry in entries:
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


def prioritize_blank_search_suggestions(
    *,
    base_suggestions: list[str],
    recent_tags: list[str],
    priority_slots: int,
) -> list[str]:
    if not isinstance(base_suggestions, list):
        raise TypeError("base_suggestions must be a list")
    if not isinstance(recent_tags, list):
        raise TypeError("recent_tags must be a list")
    if not isinstance(priority_slots, int) or priority_slots < 0:
        raise ValueError("priority_slots must be a non-negative integer")

    prioritized: list[str] = []
    seen_casefold: set[str] = set()

    for tag in recent_tags:
        if not isinstance(tag, str) or tag == "":
            raise TypeError("recent_tags entries must be non-empty strings")
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


def encrypt_all_search_history_for_active_dek(*, encryption_service: object) -> int:
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError("Search history encryption migration requires an active DEK")

    rewritten_count = 0
    with begin_search_history_writer() as connection:
        rows = fetch_all_search_history_rows(connection)
        for row in rows:
            if _row_is_fully_encrypted(row):
                continue
            entry = _deserialize_search_history_entry(
                encryption_service=service,
                row=row,
            )
            encrypted_fields = _serialize_search_history_fields(
                encryption_service=service,
                normalized=NormalizedSearchHistoryQuery(
                    query_hash=entry.query_hash,
                    query_key=entry.query_key,
                    root_tag=entry.root_tag,
                    tags=entry.tags,
                ),
            )
            update_search_history_row(
                connection,
                query_hash=entry.query_hash,
                query_key=encrypted_fields["query_key"],
                query_key_encryption_nonce=encrypted_fields["query_key_encryption_nonce"],
                query_key_encryption_tag=encrypted_fields["query_key_encryption_tag"],
                root_tag=encrypted_fields["root_tag"],
                root_tag_encryption_nonce=encrypted_fields["root_tag_encryption_nonce"],
                root_tag_encryption_tag=encrypted_fields["root_tag_encryption_tag"],
                tags_json=encrypted_fields["tags_json"],
                tags_json_encryption_nonce=encrypted_fields["tags_json_encryption_nonce"],
                tags_json_encryption_tag=encrypted_fields["tags_json_encryption_tag"],
                score=entry.score,
                last_interacted_at=entry.last_interacted_at,
                updated_at=datetime.now(timezone.utc),
            )
            rewritten_count += 1
    return rewritten_count


def decrypt_all_search_history_for_plaintext(*, encryption_service: object) -> int:
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError("Search history decryption migration requires an active DEK")

    rewritten_count = 0
    with begin_search_history_writer() as connection:
        rows = fetch_all_search_history_rows(connection)
        for row in rows:
            if _row_is_fully_plaintext(row):
                continue
            entry = _deserialize_search_history_entry(
                encryption_service=service,
                row=row,
            )
            plaintext_fields = _serialize_search_history_fields(
                encryption_service=None,
                normalized=NormalizedSearchHistoryQuery(
                    query_hash=entry.query_hash,
                    query_key=entry.query_key,
                    root_tag=entry.root_tag,
                    tags=entry.tags,
                ),
            )
            update_search_history_row(
                connection,
                query_hash=entry.query_hash,
                query_key=plaintext_fields["query_key"],
                query_key_encryption_nonce=None,
                query_key_encryption_tag=None,
                root_tag=plaintext_fields["root_tag"],
                root_tag_encryption_nonce=None,
                root_tag_encryption_tag=None,
                tags_json=plaintext_fields["tags_json"],
                tags_json_encryption_nonce=None,
                tags_json_encryption_tag=None,
                score=entry.score,
                last_interacted_at=entry.last_interacted_at,
                updated_at=datetime.now(timezone.utc),
            )
            rewritten_count += 1
    return rewritten_count


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
