"""SQLite schema helpers for search interaction history storage."""

from __future__ import annotations

from sqlite3 import Connection

SEARCH_HISTORY_TABLE = "search_interaction_history"

_CREATE_SEARCH_HISTORY_TABLE = f"""
CREATE TABLE IF NOT EXISTS {SEARCH_HISTORY_TABLE} (
    query_hash TEXT PRIMARY KEY,
    query_key TEXT NOT NULL,
    query_key_encryption_nonce BLOB,
    query_key_encryption_tag BLOB,
    root_tag TEXT NOT NULL,
    root_tag_encryption_nonce BLOB,
    root_tag_encryption_tag BLOB,
    tags_json TEXT NOT NULL,
    tags_json_encryption_nonce BLOB,
    tags_json_encryption_tag BLOB,
    score REAL NOT NULL,
    created_at TEXT NOT NULL,
    last_interacted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_CREATE_SEARCH_HISTORY_SCORE_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{SEARCH_HISTORY_TABLE}_score
ON {SEARCH_HISTORY_TABLE}(score DESC, updated_at DESC);
"""


def initialize_search_history_schema(connection: Connection) -> None:
    connection.execute(_CREATE_SEARCH_HISTORY_TABLE)
    connection.execute(_CREATE_SEARCH_HISTORY_SCORE_INDEX)
