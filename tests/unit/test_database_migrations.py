from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db.migrations import CURRENT_DATABASE_VERSION
from app.db.migrations import read_database_version
from app.db.migrations import run_database_migrations
from app.db.schema import initialize_schema
from app.services.encryption import EncryptionService


_NOW = "2026-08-01T00:00:00+00:00"


def _connection(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    initialize_schema(connection)
    return connection


def _insert_settings(
    connection: sqlite3.Connection,
    *,
    encryption_enabled: bool,
    preferences_json: str,
    usage_json: str,
    tag_prefix_json: str,
) -> None:
    connection.execute(
        """
        INSERT INTO app_settings (
            id,
            encryption_enabled,
            client_preferences_json,
            command_palette_usage_json,
            tag_prefix_settings_json,
            created_at,
            updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(encryption_enabled),
            preferences_json,
            usage_json,
            tag_prefix_json,
            _NOW,
            _NOW,
        ),
    )


def _encryption_service() -> EncryptionService:
    service = EncryptionService()
    service.dek = b"d" * 32
    return service


def test_plaintext_namespace_advances_through_migrations_without_rewriting(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "plain.db")
    _insert_settings(
        connection,
        encryption_enabled=False,
        preferences_json='{"pref.theme":"dark"}',
        usage_json="{}",
        tag_prefix_json="{}",
    )

    result = run_database_migrations(
        connection=connection,
        encryption_enabled=False,
        encryption_service=None,
    )

    assert result.initial_version == 0
    assert result.final_version == CURRENT_DATABASE_VERSION
    assert result.applied_versions == (1,)
    assert result.rewritten_payload_count == 0
    assert read_database_version(connection) == CURRENT_DATABASE_VERSION
    row = connection.execute(
        "SELECT client_preferences_json FROM app_settings WHERE id = 1"
    ).fetchone()
    assert row[0] == '{"pref.theme":"dark"}'
    connection.close()


def test_encrypted_namespace_migration_rewrites_every_nonempty_client_payload(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path / "encrypted.db")
    _insert_settings(
        connection,
        encryption_enabled=True,
        preferences_json='{"pref.theme":"dark"}',
        usage_json='{"lastQueryTokens":["secret"]}',
        tag_prefix_json='{"prefix":"private"}',
    )
    service = _encryption_service()

    result = run_database_migrations(
        connection=connection,
        encryption_enabled=True,
        encryption_service=service,
    )

    assert result.rewritten_payload_count == 3
    row = connection.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
    for value_column, nonce_column, tag_column, expected_plaintext in (
        (
            "client_preferences_json",
            "client_preferences_encryption_nonce",
            "client_preferences_encryption_tag",
            '{"pref.theme":"dark"}',
        ),
        (
            "command_palette_usage_json",
            "command_palette_usage_encryption_nonce",
            "command_palette_usage_encryption_tag",
            '{"lastQueryTokens":["secret"]}',
        ),
        (
            "tag_prefix_settings_json",
            "tag_prefix_settings_encryption_nonce",
            "tag_prefix_settings_encryption_tag",
            '{"prefix":"private"}',
        ),
    ):
        assert row[value_column] != expected_plaintext
        assert service.decrypt_from_storage(
            row[value_column],
            row[nonce_column],
            row[tag_column],
        ) == expected_plaintext
    connection.close()


def test_migrations_are_idempotent_after_version_advances(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "idempotent.db")
    _insert_settings(
        connection,
        encryption_enabled=True,
        preferences_json='{"pref.theme":"dark"}',
        usage_json="{}",
        tag_prefix_json="{}",
    )
    service = _encryption_service()
    run_database_migrations(
        connection=connection,
        encryption_enabled=True,
        encryption_service=service,
    )

    second_result = run_database_migrations(
        connection=connection,
        encryption_enabled=True,
        encryption_service=service,
    )

    assert second_result.applied_versions == ()
    assert second_result.rewritten_payload_count == 0
    connection.close()


def test_migration_rejects_incomplete_existing_encryption_metadata(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "invalid.db")
    _insert_settings(
        connection,
        encryption_enabled=True,
        preferences_json='{"pref.theme":"dark"}',
        usage_json="{}",
        tag_prefix_json="{}",
    )
    connection.execute(
        "UPDATE app_settings SET client_preferences_encryption_nonce = ? WHERE id = 1",
        (b"n" * 12,),
    )

    with pytest.raises(RuntimeError, match="incomplete encryption metadata"):
        run_database_migrations(
            connection=connection,
            encryption_enabled=True,
            encryption_service=_encryption_service(),
        )

    assert read_database_version(connection) == 0
    connection.close()


def test_migration_rejects_database_from_newer_application(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "future.db")
    connection.execute(f"PRAGMA user_version = {CURRENT_DATABASE_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than supported"):
        run_database_migrations(
            connection=connection,
            encryption_enabled=False,
            encryption_service=None,
        )
    connection.close()
