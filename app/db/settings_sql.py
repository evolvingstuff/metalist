"""SQLite helpers for the app_settings table."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .engine import GuardedConnection
from .schema import APP_SETTINGS_TABLE


def _conn(connection: GuardedConnection | sqlite3.Connection) -> sqlite3.Connection:
    if isinstance(connection, GuardedConnection):
        return connection.raw_connection
    else:
        return connection


def _serialize_datetime(value: Optional[datetime]) -> str:
    return (value or datetime.now(timezone.utc)).isoformat()


def fetch_settings(connection: GuardedConnection | sqlite3.Connection) -> Optional[dict]:
    conn = _conn(connection)
    row = conn.execute(
        f"SELECT * FROM {APP_SETTINGS_TABLE} WHERE id = 1",
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "password_hash": row["password_hash"],
        "password_salt": row["password_salt"],
        "password_iterations": row["password_iterations"],
        "auth_verifier": row["auth_verifier"],
        "auth_salt": row["auth_salt"],
        "auth_iterations": row["auth_iterations"],
        "kek_salt": row["kek_salt"],
        "kek_iterations": row["kek_iterations"],
        "encryption_enabled": bool(row["encryption_enabled"]),
        "encryption_algorithm": row["encryption_algorithm"],
        "encrypted_dek": row["encrypted_dek"],
        "dek_nonce": row["dek_nonce"],
        "dek_tag": row["dek_tag"],
        "created_at": datetime.fromisoformat(row["created_at"]),
        "updated_at": datetime.fromisoformat(row["updated_at"]),
    }


def insert_default_settings(connection: GuardedConnection | sqlite3.Connection) -> None:
    conn = _conn(connection)
    now = datetime.now(timezone.utc)
    conn.execute(
        f"""
        INSERT OR IGNORE INTO {APP_SETTINGS_TABLE} (
            id,
            encryption_enabled,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?)
        """,
        (
            1,
            0,
            _serialize_datetime(now),
            _serialize_datetime(now),
        ),
    )


def update_password_settings(
    connection: GuardedConnection | sqlite3.Connection,
    *,
    auth_verifier: str,
    auth_salt: bytes,
    auth_iterations: int,
    kek_salt: bytes,
    kek_iterations: int,
    encrypted_dek: bytes,
    dek_nonce: bytes,
    dek_tag: bytes,
    encryption_algorithm: str,
) -> None:
    conn = _conn(connection)
    conn.execute(
        f"""
        UPDATE {APP_SETTINGS_TABLE}
        SET password_hash = NULL,
            password_salt = NULL,
            password_iterations = NULL,
            auth_verifier = ?,
            auth_salt = ?,
            auth_iterations = ?,
            kek_salt = ?,
            kek_iterations = ?,
            encrypted_dek = ?,
            dek_nonce = ?,
            dek_tag = ?,
            encryption_enabled = 1,
            encryption_algorithm = ?,
            updated_at = ?
        WHERE id = 1
        """,
        (
            auth_verifier,
            auth_salt,
            auth_iterations,
            kek_salt,
            kek_iterations,
            encrypted_dek,
            dek_nonce,
            dek_tag,
            encryption_algorithm,
            _serialize_datetime(datetime.now(timezone.utc)),
        ),
    )


def clear_password_settings(connection: GuardedConnection | sqlite3.Connection) -> None:
    conn = _conn(connection)
    conn.execute(
        f"""
        UPDATE {APP_SETTINGS_TABLE}
        SET password_hash = NULL,
            password_salt = NULL,
            password_iterations = NULL,
            auth_verifier = NULL,
            auth_salt = NULL,
            auth_iterations = NULL,
            kek_salt = NULL,
            kek_iterations = NULL,
            encrypted_dek = NULL,
            dek_nonce = NULL,
            dek_tag = NULL,
            encryption_enabled = 0,
            encryption_algorithm = NULL,
            updated_at = ?
        WHERE id = 1
        """,
        (
            _serialize_datetime(datetime.now(timezone.utc)),
        ),
    )
