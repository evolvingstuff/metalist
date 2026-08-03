"""Ordered, transactional database migrations for namespace databases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import sqlite3

from app.db.version import CURRENT_DATABASE_VERSION
from app.services.encryption import EncryptionService


@dataclass(frozen=True, slots=True)
class MigrationResult:
    initial_version: int
    final_version: int
    applied_versions: tuple[int, ...]
    rewritten_payload_count: int


_CLIENT_STATE_PAYLOADS = (
    (
        "client_preferences_json",
        "client_preferences_encryption_nonce",
        "client_preferences_encryption_tag",
    ),
    (
        "command_palette_usage_json",
        "command_palette_usage_encryption_nonce",
        "command_palette_usage_encryption_tag",
    ),
    (
        "tag_prefix_settings_json",
        "tag_prefix_settings_encryption_nonce",
        "tag_prefix_settings_encryption_tag",
    ),
)


def read_database_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        raise RuntimeError("Database user_version PRAGMA returned no row")
    version = row[0]
    if not isinstance(version, int) or version < 0:
        raise RuntimeError(f"Invalid database user_version: {version!r}")
    return version


def _table_columns(connection: sqlite3.Connection, *, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _assert_client_state_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, table="app_settings")
    required = {column for payload in _CLIENT_STATE_PAYLOADS for column in payload}
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(f"Database migration requires missing columns: {missing}")


def _rewrite_payload_for_encrypted_namespace(
    *,
    connection: sqlite3.Connection,
    encryption_service: EncryptionService,
    value_column: str,
    nonce_column: str,
    tag_column: str,
) -> int:
    row = connection.execute(
        f"SELECT {value_column}, {nonce_column}, {tag_column} FROM app_settings WHERE id = 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("Database migration requires app_settings row id=1")
    value, nonce, tag = row
    if (nonce is None) != (tag is None):
        raise RuntimeError(f"{value_column} has incomplete encryption metadata")
    if value is None or value == "":
        if nonce is not None:
            raise RuntimeError(f"{value_column} has encryption metadata without a payload")
        return 0
    if not isinstance(value, str):
        raise RuntimeError(f"{value_column} must be stored as text")
    if nonce is not None:
        encryption_service.decrypt_from_storage(value, nonce, tag)
        return 0
    ciphertext, next_nonce, next_tag = encryption_service.encrypt_for_storage(value)
    connection.execute(
        f"""
        UPDATE app_settings
        SET {value_column} = ?, {nonce_column} = ?, {tag_column} = ?
        WHERE id = 1
        """,
        (ciphertext, next_nonce, next_tag),
    )
    return 1


def _migration_0_to_1(
    *,
    connection: sqlite3.Connection,
    encryption_enabled: bool,
    encryption_service: EncryptionService | None,
) -> int:
    _assert_client_state_schema(connection)
    if not encryption_enabled:
        return 0
    if encryption_service is None or encryption_service.dek is None:
        raise RuntimeError("Database migration 0→1 requires the namespace DEK")
    rewritten_count = 0
    for value_column, nonce_column, tag_column in _CLIENT_STATE_PAYLOADS:
        rewritten_count += _rewrite_payload_for_encrypted_namespace(
            connection=connection,
            encryption_service=encryption_service,
            value_column=value_column,
            nonce_column=nonce_column,
            tag_column=tag_column,
        )
    return rewritten_count


_MIGRATIONS: dict[
    int,
    Callable[..., int],
] = {
    0: _migration_0_to_1,
}


def run_database_migrations(
    *,
    connection: sqlite3.Connection,
    encryption_enabled: bool,
    encryption_service: EncryptionService | None,
) -> MigrationResult:
    initial_version = read_database_version(connection)
    if initial_version > CURRENT_DATABASE_VERSION:
        raise RuntimeError(
            f"Database version {initial_version} is newer than supported version "
            f"{CURRENT_DATABASE_VERSION}"
        )
    version = initial_version
    applied_versions: list[int] = []
    rewritten_payload_count = 0
    while version < CURRENT_DATABASE_VERSION:
        if version not in _MIGRATIONS:
            raise RuntimeError(f"No database migration registered from version {version}")
        rewritten_payload_count += _MIGRATIONS[version](
            connection=connection,
            encryption_enabled=encryption_enabled,
            encryption_service=encryption_service,
        )
        version += 1
        connection.execute(f"PRAGMA user_version = {version}")
        applied_versions.append(version)
    return MigrationResult(
        initial_version=initial_version,
        final_version=version,
        applied_versions=tuple(applied_versions),
        rewritten_payload_count=rewritten_payload_count,
    )
