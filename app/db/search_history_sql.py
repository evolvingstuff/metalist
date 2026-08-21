"""Composable sqlite helpers for opaque search interaction history rows."""

from __future__ import annotations

from collections.abc import Iterable
import sqlite3

from app.db.schema import SEARCH_HISTORY_TABLE


def _deserialize_row(row: sqlite3.Row) -> dict[str, object]:
    storage_id = row["storage_id"]
    payload_json = row["payload_json"]
    if not isinstance(storage_id, str) or storage_id == "":
        raise TypeError("search_interaction_history.storage_id must be a non-empty string")
    if not isinstance(payload_json, str) or payload_json == "":
        raise TypeError("search_interaction_history.payload_json must be a non-empty string")
    return {
        "storage_id": storage_id,
        "payload_json": payload_json,
        "payload_encryption_nonce": row["payload_encryption_nonce"],
        "payload_encryption_tag": row["payload_encryption_tag"],
    }


def fetch_all_search_history_rows(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        f"SELECT * FROM {SEARCH_HISTORY_TABLE} ORDER BY storage_id ASC"
    ).fetchall()
    return [_deserialize_row(row) for row in rows]


def upsert_search_history_row(
    connection: sqlite3.Connection,
    *,
    storage_id: str,
    payload_json: str,
    payload_encryption_nonce: bytes | None,
    payload_encryption_tag: bytes | None,
) -> None:
    connection.execute(
        f"""
        INSERT INTO {SEARCH_HISTORY_TABLE} (
            storage_id,
            payload_json,
            payload_encryption_nonce,
            payload_encryption_tag
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(storage_id) DO UPDATE SET
            payload_json = excluded.payload_json,
            payload_encryption_nonce = excluded.payload_encryption_nonce,
            payload_encryption_tag = excluded.payload_encryption_tag
        """,
        (
            storage_id,
            payload_json,
            payload_encryption_nonce,
            payload_encryption_tag,
        ),
    )


def delete_search_history_rows(connection: sqlite3.Connection, storage_ids: Iterable[str]) -> int:
    identifiers = list(storage_ids)
    if not identifiers:
        return 0
    placeholders = ",".join(["?"] * len(identifiers))
    cursor = connection.execute(
        f"DELETE FROM {SEARCH_HISTORY_TABLE} WHERE storage_id IN ({placeholders})",
        tuple(identifiers),
    )
    return int(cursor.rowcount)


def delete_all_search_history_rows(connection: sqlite3.Connection) -> int:
    cursor = connection.execute(f"DELETE FROM {SEARCH_HISTORY_TABLE}")
    return int(cursor.rowcount)
