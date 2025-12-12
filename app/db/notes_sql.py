"""Composable sqlite helpers for the notes table."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Iterable, Optional

from .engine import GuardedConnection
from .schema import NOTES_TABLE


def _conn(connection: GuardedConnection | sqlite3.Connection) -> sqlite3.Connection:
    return connection.raw_connection if isinstance(connection, GuardedConnection) else connection


def _serialize_datetime(value: Optional[datetime]) -> str:
    return (value or datetime.now(timezone.utc)).isoformat()


def _deserialize_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "content": row["content"],
        "encryption_nonce": row["encryption_nonce"],
        "encryption_tag": row["encryption_tag"],
        "parent_id": row["parent_id"],
        "prev_id": row["prev_id"],
        "next_id": row["next_id"],
        "is_collapsed": bool(row["is_collapsed"]),
        "created_at": datetime.fromisoformat(row["created_at"]),
        "updated_at": datetime.fromisoformat(row["updated_at"]),
    }


def insert_note(
    connection: GuardedConnection | sqlite3.Connection,
    *,
    note_id: str,
    content: str,
    encryption_nonce: Optional[bytes],
    encryption_tag: Optional[bytes],
    parent_id: Optional[str],
    prev_id: Optional[str],
    next_id: Optional[str],
    is_collapsed: bool = False,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
) -> None:
    conn = _conn(connection)
    conn.execute(
        f"""
        INSERT INTO {NOTES_TABLE} (
            id,
            content,
            encryption_nonce,
            encryption_tag,
            parent_id,
            prev_id,
            next_id,
            is_collapsed,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            note_id,
            content,
            encryption_nonce,
            encryption_tag,
            parent_id,
            prev_id,
            next_id,
            int(is_collapsed),
            _serialize_datetime(created_at),
            _serialize_datetime(updated_at),
        ),
    )


def update_note_content(
    connection: GuardedConnection | sqlite3.Connection,
    note_id: str,
    *,
    content: str,
    encryption_nonce: Optional[bytes],
    encryption_tag: Optional[bytes],
    updated_at: Optional[datetime] = None,
) -> None:
    conn = _conn(connection)
    conn.execute(
        f"""
        UPDATE {NOTES_TABLE}
        SET content = ?,
            encryption_nonce = ?,
            encryption_tag = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            content,
            encryption_nonce,
            encryption_tag,
            _serialize_datetime(updated_at),
            note_id,
        ),
    )


_UNSET = object()


def update_links(
    connection: GuardedConnection | sqlite3.Connection,
    note_id: str,
    *,
    parent_id: Optional[str] = _UNSET,
    prev_id: Optional[str] = _UNSET,
    next_id: Optional[str] = _UNSET,
    is_collapsed: Optional[bool] = _UNSET,
    updated_at: Optional[datetime] = None,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list = [_serialize_datetime(updated_at)]

    if parent_id is not _UNSET:
        fields.append("parent_id = ?")
        values.append(parent_id)
    if prev_id is not _UNSET:
        fields.append("prev_id = ?")
        values.append(prev_id)
    if next_id is not _UNSET:
        fields.append("next_id = ?")
        values.append(next_id)
    if is_collapsed is not _UNSET:
        fields.append("is_collapsed = ?")
        values.append(int(is_collapsed))

    values.append(note_id)

    conn = _conn(connection)
    sql = f"UPDATE {NOTES_TABLE} SET " + ", ".join(fields) + " WHERE id = ?"
    conn.execute(sql, tuple(values))


def delete_notes(
    connection: GuardedConnection | sqlite3.Connection,
    note_ids: Iterable[str],
) -> None:
    identifiers = list(note_ids)
    if not identifiers:
        return
    placeholders = ",".join(["?"] * len(identifiers))
    sql = f"DELETE FROM {NOTES_TABLE} WHERE id IN ({placeholders})"
    print('DEBUG CHECKPOINT 1')
    t1 = time.perf_counter()
    conn = _conn(connection)
    conn.execute(sql, tuple(identifiers))
    t2 = time.perf_counter()
    print(f'DEBUG CHECKPOINT 2 took {(t2-t1)} seconds')


def fetch_note(
    connection: GuardedConnection | sqlite3.Connection,
    note_id: str,
) -> Optional[dict]:
    conn = _conn(connection)
    row = conn.execute(
        f"SELECT * FROM {NOTES_TABLE} WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row is None:
        return None
    return _deserialize_row(row)


def fetch_children_ordered(
    connection: GuardedConnection | sqlite3.Connection,
    parent_id: Optional[str],
) -> list[dict]:
    conn = _conn(connection)
    if parent_id is None:
        rows = conn.execute(
            f"SELECT * FROM {NOTES_TABLE} WHERE parent_id IS NULL",
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM {NOTES_TABLE} WHERE parent_id = ?",
            (parent_id,),
        ).fetchall()

    if not rows:
        return []

    notes = [_deserialize_row(row) for row in rows]
    by_id = {note["id"]: note for note in notes}
    head = next((note for note in notes if note["prev_id"] is None), None)
    if not head:
        return list(notes)

    ordered: list[dict] = []
    current = head
    seen: set[str] = set()
    while current["id"] not in seen:
        ordered.append(current)
        seen.add(current["id"])
        next_id = current.get("next_id")
        if next_id is None:
            break
        current = by_id.get(next_id)
        if current is None:
            break
    return ordered


def fetch_all_for_cache(connection: GuardedConnection | sqlite3.Connection) -> list[dict]:
    conn = _conn(connection)
    rows = conn.execute(f"SELECT * FROM {NOTES_TABLE}").fetchall()
    return [_deserialize_row(row) for row in rows]


def clear_encryption_metadata_for_empty_notes(
    connection: GuardedConnection | sqlite3.Connection,
    *,
    updated_at: Optional[datetime] = None,
) -> int:
    """Clear encryption metadata for notes whose content is an empty string.

    AES-GCM encryption of an empty plaintext produces an empty ciphertext, so
    we can safely clear nonce/tag without losing content. This is used as a
    targeted integrity repair when password protection has been removed.
    """

    conn = _conn(connection)
    cursor = conn.execute(
        f"""
        UPDATE {NOTES_TABLE}
        SET encryption_nonce = NULL,
            encryption_tag = NULL,
            updated_at = ?
        WHERE content = ''
          AND encryption_nonce IS NOT NULL
          AND encryption_tag IS NOT NULL
        """,
        (_serialize_datetime(updated_at),),
    )
    return int(cursor.rowcount or 0)
