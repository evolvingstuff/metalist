"""SQLite schema helpers for MetaList."""

from __future__ import annotations

from sqlite3 import Connection

NOTES_TABLE = "notes"
APP_SETTINGS_TABLE = "app_settings"

_CREATE_NOTES_TABLE = f"""
CREATE TABLE IF NOT EXISTS {NOTES_TABLE} (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    is_collapsed INTEGER NOT NULL DEFAULT 0,
    encryption_nonce BLOB,
    encryption_tag BLOB,
    parent_id TEXT,
    prev_id TEXT,
    next_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_CREATE_NOTES_PARENT_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{NOTES_TABLE}_parent ON {NOTES_TABLE}(parent_id);
"""

_CREATE_NOTES_PREV_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{NOTES_TABLE}_prev ON {NOTES_TABLE}(prev_id);
"""

_CREATE_NOTES_NEXT_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{NOTES_TABLE}_next ON {NOTES_TABLE}(next_id);
"""

_CREATE_APP_SETTINGS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {APP_SETTINGS_TABLE} (
    id INTEGER PRIMARY KEY,
    password_hash TEXT,
    password_salt BLOB,
    password_iterations INTEGER,
    auth_verifier TEXT,
    auth_salt BLOB,
    auth_iterations INTEGER,
    kek_salt BLOB,
    kek_iterations INTEGER,
    encryption_enabled INTEGER NOT NULL DEFAULT 0,
    encryption_algorithm TEXT,
    encrypted_dek BLOB,
    dek_nonce BLOB,
    dek_tag BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _ensure_columns(connection: Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        if row and len(row) > 1
    }

    for name, col_type in columns.items():
        if name in existing:
            continue
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def initialize_schema(connection: Connection) -> None:
    """Create tables and indexes if they do not already exist."""

    connection.execute(_CREATE_NOTES_TABLE)
    connection.execute(_CREATE_APP_SETTINGS_TABLE)
    _ensure_columns(
        connection,
        APP_SETTINGS_TABLE,
        {
            "auth_verifier": "TEXT",
            "auth_salt": "BLOB",
            "auth_iterations": "INTEGER",
            "kek_salt": "BLOB",
            "kek_iterations": "INTEGER",
        },
    )
    connection.execute(_CREATE_NOTES_PARENT_INDEX)
    connection.execute(_CREATE_NOTES_PREV_INDEX)
    connection.execute(_CREATE_NOTES_NEXT_INDEX)
