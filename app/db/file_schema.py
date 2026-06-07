"""SQLite schema helpers for encrypted file storage."""

from __future__ import annotations

from sqlite3 import Connection

FILES_TABLE = "files"
SOUNDS_TABLE = "sounds"

_CREATE_FILES_TABLE = f"""
CREATE TABLE IF NOT EXISTS {FILES_TABLE} (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    title_encryption_nonce BLOB,
    title_encryption_tag BLOB,
    metadata_json TEXT NOT NULL,
    metadata_encryption_nonce BLOB,
    metadata_encryption_tag BLOB,
    blob_data BLOB NOT NULL,
    blob_encryption_nonce BLOB,
    blob_encryption_tag BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


_CREATE_SOUNDS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SOUNDS_TABLE} (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    title_encryption_nonce BLOB,
    title_encryption_tag BLOB,
    metadata_json TEXT NOT NULL,
    metadata_encryption_nonce BLOB,
    metadata_encryption_tag BLOB,
    blob_data BLOB NOT NULL,
    blob_encryption_nonce BLOB,
    blob_encryption_tag BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def initialize_file_schema(connection: Connection) -> None:
    connection.execute(_CREATE_FILES_TABLE)
    connection.execute(_CREATE_SOUNDS_TABLE)
