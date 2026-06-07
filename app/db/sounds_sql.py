"""Composable sqlite helpers for the encrypted sounds table."""

from __future__ import annotations

from datetime import datetime
import sqlite3

from app.db.file_schema import SOUNDS_TABLE


def _serialize_datetime(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError(f"value must be a datetime, got {type(value)}")
    return value.isoformat()


def _deserialize_row(row: sqlite3.Row) -> dict[str, object]:
    sound_id = row["id"]

    def _parse_datetime(field: str) -> datetime:
        raw = row[field]
        if not isinstance(raw, str):
            raise TypeError(f"sounds.{field} must be a string | sound_id={sound_id} value={raw!r}")
        return datetime.fromisoformat(raw)

    return {
        "id": sound_id,
        "title": row["title"],
        "title_encryption_nonce": row["title_encryption_nonce"],
        "title_encryption_tag": row["title_encryption_tag"],
        "metadata_json": row["metadata_json"],
        "metadata_encryption_nonce": row["metadata_encryption_nonce"],
        "metadata_encryption_tag": row["metadata_encryption_tag"],
        "blob_data": row["blob_data"],
        "blob_encryption_nonce": row["blob_encryption_nonce"],
        "blob_encryption_tag": row["blob_encryption_tag"],
        "created_at": _parse_datetime("created_at"),
        "updated_at": _parse_datetime("updated_at"),
    }


def insert_sound(
    connection: sqlite3.Connection,
    *,
    sound_id: str,
    title: str,
    title_encryption_nonce: bytes | None,
    title_encryption_tag: bytes | None,
    metadata_json: str,
    metadata_encryption_nonce: bytes | None,
    metadata_encryption_tag: bytes | None,
    blob_data: bytes,
    blob_encryption_nonce: bytes | None,
    blob_encryption_tag: bytes | None,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    connection.execute(
        f"""
        INSERT INTO {SOUNDS_TABLE} (
            id,
            title,
            title_encryption_nonce,
            title_encryption_tag,
            metadata_json,
            metadata_encryption_nonce,
            metadata_encryption_tag,
            blob_data,
            blob_encryption_nonce,
            blob_encryption_tag,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sound_id,
            title,
            title_encryption_nonce,
            title_encryption_tag,
            metadata_json,
            metadata_encryption_nonce,
            metadata_encryption_tag,
            blob_data,
            blob_encryption_nonce,
            blob_encryption_tag,
            _serialize_datetime(created_at),
            _serialize_datetime(updated_at),
        ),
    )


def fetch_sound(connection: sqlite3.Connection, sound_id: str) -> dict[str, object] | None:
    row = connection.execute(
        f"SELECT * FROM {SOUNDS_TABLE} WHERE id = ?",
        (sound_id,),
    ).fetchone()
    if row is None:
        return None
    return _deserialize_row(row)


def fetch_all_sounds(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(f"SELECT * FROM {SOUNDS_TABLE} ORDER BY created_at ASC").fetchall()
    records: list[dict[str, object]] = []
    for row in rows:
        records.append(_deserialize_row(row))
    return records


def update_sound_storage_fields(
    connection: sqlite3.Connection,
    *,
    sound_id: str,
    title: str,
    title_encryption_nonce: bytes | None,
    title_encryption_tag: bytes | None,
    metadata_json: str,
    metadata_encryption_nonce: bytes | None,
    metadata_encryption_tag: bytes | None,
    blob_data: bytes,
    blob_encryption_nonce: bytes | None,
    blob_encryption_tag: bytes | None,
    updated_at: datetime,
) -> None:
    connection.execute(
        f"""
        UPDATE {SOUNDS_TABLE}
        SET
            title = ?,
            title_encryption_nonce = ?,
            title_encryption_tag = ?,
            metadata_json = ?,
            metadata_encryption_nonce = ?,
            metadata_encryption_tag = ?,
            blob_data = ?,
            blob_encryption_nonce = ?,
            blob_encryption_tag = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            title,
            title_encryption_nonce,
            title_encryption_tag,
            metadata_json,
            metadata_encryption_nonce,
            metadata_encryption_tag,
            blob_data,
            blob_encryption_nonce,
            blob_encryption_tag,
            _serialize_datetime(updated_at),
            sound_id,
        ),
    )


def delete_sound(connection: sqlite3.Connection, sound_id: str) -> int:
    cursor = connection.execute(
        f"DELETE FROM {SOUNDS_TABLE} WHERE id = ?",
        (sound_id,),
    )
    return int(cursor.rowcount)
