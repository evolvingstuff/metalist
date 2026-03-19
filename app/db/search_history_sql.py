"""Composable sqlite helpers for the search interaction history table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable, Optional

from app.db.search_history_schema import SEARCH_HISTORY_TABLE


def _serialize_datetime(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError(f"value must be a datetime, got {type(value)}")
    return value.isoformat()


def _deserialize_row(row: sqlite3.Row) -> dict[str, object]:
    query_hash = row["query_hash"]

    def _parse_datetime(field: str) -> datetime:
        raw = row[field]
        if not isinstance(raw, str):
            raise TypeError(
                f"search_interaction_history.{field} must be a string | query_hash={query_hash} value={raw!r}"
            )
        return datetime.fromisoformat(raw)

    return {
        "query_hash": query_hash,
        "query_key": row["query_key"],
        "query_key_encryption_nonce": row["query_key_encryption_nonce"],
        "query_key_encryption_tag": row["query_key_encryption_tag"],
        "root_tag": row["root_tag"],
        "root_tag_encryption_nonce": row["root_tag_encryption_nonce"],
        "root_tag_encryption_tag": row["root_tag_encryption_tag"],
        "tags_json": row["tags_json"],
        "tags_json_encryption_nonce": row["tags_json_encryption_nonce"],
        "tags_json_encryption_tag": row["tags_json_encryption_tag"],
        "score": float(row["score"]),
        "created_at": _parse_datetime("created_at"),
        "last_interacted_at": _parse_datetime("last_interacted_at"),
        "updated_at": _parse_datetime("updated_at"),
    }


def fetch_search_history_row(
    connection: sqlite3.Connection,
    query_hash: str,
) -> Optional[dict[str, object]]:
    row = connection.execute(
        f"SELECT * FROM {SEARCH_HISTORY_TABLE} WHERE query_hash = ?",
        (query_hash,),
    ).fetchone()
    if row is None:
        return None
    return _deserialize_row(row)


def fetch_all_search_history_rows(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        f"SELECT * FROM {SEARCH_HISTORY_TABLE} ORDER BY score DESC, updated_at DESC, query_hash ASC"
    ).fetchall()
    return [_deserialize_row(row) for row in rows]


def insert_search_history_row(
    connection: sqlite3.Connection,
    *,
    query_hash: str,
    query_key: str,
    query_key_encryption_nonce: Optional[bytes],
    query_key_encryption_tag: Optional[bytes],
    root_tag: str,
    root_tag_encryption_nonce: Optional[bytes],
    root_tag_encryption_tag: Optional[bytes],
    tags_json: str,
    tags_json_encryption_nonce: Optional[bytes],
    tags_json_encryption_tag: Optional[bytes],
    score: float,
    created_at: datetime,
    last_interacted_at: datetime,
    updated_at: datetime,
) -> None:
    connection.execute(
        f"""
        INSERT INTO {SEARCH_HISTORY_TABLE} (
            query_hash,
            query_key,
            query_key_encryption_nonce,
            query_key_encryption_tag,
            root_tag,
            root_tag_encryption_nonce,
            root_tag_encryption_tag,
            tags_json,
            tags_json_encryption_nonce,
            tags_json_encryption_tag,
            score,
            created_at,
            last_interacted_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            query_hash,
            query_key,
            query_key_encryption_nonce,
            query_key_encryption_tag,
            root_tag,
            root_tag_encryption_nonce,
            root_tag_encryption_tag,
            tags_json,
            tags_json_encryption_nonce,
            tags_json_encryption_tag,
            score,
            _serialize_datetime(created_at),
            _serialize_datetime(last_interacted_at),
            _serialize_datetime(updated_at),
        ),
    )


def update_search_history_row(
    connection: sqlite3.Connection,
    *,
    query_hash: str,
    query_key: str,
    query_key_encryption_nonce: Optional[bytes],
    query_key_encryption_tag: Optional[bytes],
    root_tag: str,
    root_tag_encryption_nonce: Optional[bytes],
    root_tag_encryption_tag: Optional[bytes],
    tags_json: str,
    tags_json_encryption_nonce: Optional[bytes],
    tags_json_encryption_tag: Optional[bytes],
    score: float,
    last_interacted_at: datetime,
    updated_at: datetime,
) -> None:
    connection.execute(
        f"""
        UPDATE {SEARCH_HISTORY_TABLE}
        SET
            query_key = ?,
            query_key_encryption_nonce = ?,
            query_key_encryption_tag = ?,
            root_tag = ?,
            root_tag_encryption_nonce = ?,
            root_tag_encryption_tag = ?,
            tags_json = ?,
            tags_json_encryption_nonce = ?,
            tags_json_encryption_tag = ?,
            score = ?,
            last_interacted_at = ?,
            updated_at = ?
        WHERE query_hash = ?
        """,
        (
            query_key,
            query_key_encryption_nonce,
            query_key_encryption_tag,
            root_tag,
            root_tag_encryption_nonce,
            root_tag_encryption_tag,
            tags_json,
            tags_json_encryption_nonce,
            tags_json_encryption_tag,
            score,
            _serialize_datetime(last_interacted_at),
            _serialize_datetime(updated_at),
            query_hash,
        ),
    )


def update_search_history_score_fields(
    connection: sqlite3.Connection,
    *,
    query_hash: str,
    score: float,
    updated_at: datetime,
) -> None:
    connection.execute(
        f"""
        UPDATE {SEARCH_HISTORY_TABLE}
        SET
            score = ?,
            updated_at = ?
        WHERE query_hash = ?
        """,
        (
            score,
            _serialize_datetime(updated_at),
            query_hash,
        ),
    )


def delete_search_history_rows(connection: sqlite3.Connection, query_hashes: Iterable[str]) -> int:
    identifiers = list(query_hashes)
    if not identifiers:
        return 0
    placeholders = ",".join(["?"] * len(identifiers))
    cursor = connection.execute(
        f"DELETE FROM {SEARCH_HISTORY_TABLE} WHERE query_hash IN ({placeholders})",
        tuple(identifiers),
    )
    return int(cursor.rowcount)
