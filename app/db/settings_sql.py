"""SQLite helpers for the app_settings table."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .engine import GuardedConnection
from .schema import APP_SETTINGS_TABLE


def _conn(connection: GuardedConnection | sqlite3.Connection) -> sqlite3.Connection:
    raw_connection = getattr(connection, "raw_connection", None)
    if isinstance(raw_connection, sqlite3.Connection):
        return raw_connection
    assert isinstance(connection, sqlite3.Connection)
    return connection


def _serialize_datetime(value: Optional[datetime]) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    return value.isoformat()


def fetch_settings(connection: GuardedConnection | sqlite3.Connection) -> Optional[dict]:
    conn = _conn(connection)
    row = conn.execute(
        f"SELECT * FROM {APP_SETTINGS_TABLE} WHERE id = 1",
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "auth_verifier": row["auth_verifier"],
        "auth_salt": row["auth_salt"],
        "auth_iterations": row["auth_iterations"],
        "kek_salt": row["kek_salt"],
        "kek_iterations": row["kek_iterations"],
        "vault_version": row["vault_version"],
        "kdf_algorithm": row["kdf_algorithm"],
        "kdf_memory_cost_kib": row["kdf_memory_cost_kib"],
        "kdf_parallelism": row["kdf_parallelism"],
        "encryption_enabled": bool(row["encryption_enabled"]),
        "encryption_algorithm": row["encryption_algorithm"],
        "encrypted_dek": row["encrypted_dek"],
        "dek_nonce": row["dek_nonce"],
        "dek_tag": row["dek_tag"],
        "backup_settings_json": row["backup_settings_json"],
        "backup_settings_encryption_nonce": row["backup_settings_encryption_nonce"],
        "backup_settings_encryption_tag": row["backup_settings_encryption_tag"],
        "client_preferences_json": row["client_preferences_json"],
        "command_palette_usage_json": row["command_palette_usage_json"],
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
    vault_version: int,
    kdf_algorithm: str,
    kdf_memory_cost_kib: int,
    kdf_parallelism: int,
    encrypted_dek: bytes,
    dek_nonce: bytes,
    dek_tag: bytes,
    encryption_algorithm: str,
) -> None:
    conn = _conn(connection)
    conn.execute(
        f"""
        UPDATE {APP_SETTINGS_TABLE}
        SET auth_verifier = ?,
            auth_salt = ?,
            auth_iterations = ?,
            kek_salt = ?,
            kek_iterations = ?,
            vault_version = ?,
            kdf_algorithm = ?,
            kdf_memory_cost_kib = ?,
            kdf_parallelism = ?,
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
            vault_version,
            kdf_algorithm,
            kdf_memory_cost_kib,
            kdf_parallelism,
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
        SET auth_verifier = NULL,
            auth_salt = NULL,
            auth_iterations = NULL,
            kek_salt = NULL,
            kek_iterations = NULL,
            vault_version = NULL,
            kdf_algorithm = NULL,
            kdf_memory_cost_kib = NULL,
            kdf_parallelism = NULL,
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


def update_client_preferences_json(
    connection: GuardedConnection | sqlite3.Connection,
    *,
    client_preferences_json: str,
) -> None:
    if not isinstance(client_preferences_json, str):
        raise TypeError("client_preferences_json must be a string")

    conn = _conn(connection)
    conn.execute(
        f"""
        UPDATE {APP_SETTINGS_TABLE}
        SET client_preferences_json = ?,
            updated_at = ?
        WHERE id = 1
        """,
        (
            client_preferences_json,
            _serialize_datetime(datetime.now(timezone.utc)),
        ),
    )


def update_command_palette_usage_json(
    connection: GuardedConnection | sqlite3.Connection,
    *,
    command_palette_usage_json: str,
) -> None:
    if not isinstance(command_palette_usage_json, str):
        raise TypeError("command_palette_usage_json must be a string")

    conn = _conn(connection)
    conn.execute(
        f"""
        UPDATE {APP_SETTINGS_TABLE}
        SET command_palette_usage_json = ?,
            updated_at = ?
        WHERE id = 1
        """,
        (
            command_palette_usage_json,
            _serialize_datetime(datetime.now(timezone.utc)),
        ),
    )
