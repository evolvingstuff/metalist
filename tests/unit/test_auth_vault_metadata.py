from __future__ import annotations

from pathlib import Path

import pytest

from app.config import (
    KDF_ALGORITHM,
    KDF_MEMORY_COST_KIB,
    KDF_PARALLELISM,
    KDF_TIME_COST,
    VAULT_VERSION,
)
from app.db.file_session import connect_file_reader
from app.db.files_sql import fetch_file
from app.db.session import begin_writer
from app.db.settings_sql import fetch_settings
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key, set_encryption_required, set_session_dek
from app.services.auth_service import AuthService
from app.services.file_registry import file_registry
from app.services.file_storage import create_file, get_file_reference_record


def test_set_password_persists_vault_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        session = SafeSession()
        try:
            auth = AuthService(session)
            success, message = auth.set_password("abcd", KDF_TIME_COST)
            assert success, message

            with SafeSession.allow_reads("tests:auth_vault_metadata:fetch_settings"):
                settings = fetch_settings(session.connection())
            assert settings is not None
            assert settings["encryption_enabled"] is True
            assert settings["vault_version"] == VAULT_VERSION
            assert settings["kdf_algorithm"] == KDF_ALGORITHM
            assert settings["auth_iterations"] == KDF_TIME_COST
            assert settings["kek_iterations"] == KDF_TIME_COST
            assert settings["kdf_memory_cost_kib"] == KDF_MEMORY_COST_KIB
            assert settings["kdf_parallelism"] == KDF_PARALLELISM

            assert auth.verify_password("abcd") is True
            dek = auth.unwrap_dek_for_password("abcd")
            assert len(dek) == 32
        finally:
            session.close()
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_verify_password_fails_for_unsupported_kdf_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        session = SafeSession()
        try:
            auth = AuthService(session)
            success, message = auth.set_password("abcd", KDF_TIME_COST)
            assert success, message

            with begin_writer() as connection:
                connection.execute(
                    """
                    UPDATE app_settings
                    SET kdf_algorithm = ?
                    WHERE id = 1
                    """,
                    ("UNSUPPORTED-KDF",),
                )

            with pytest.raises(RuntimeError, match="Unsupported kdf_algorithm"):
                auth.verify_password("abcd")
        finally:
            session.close()
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_verify_password_fails_when_kdf_memory_metadata_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        session = SafeSession()
        try:
            auth = AuthService(session)
            success, message = auth.set_password("abcd", KDF_TIME_COST)
            assert success, message

            with begin_writer() as connection:
                connection.execute(
                    """
                    UPDATE app_settings
                    SET kdf_memory_cost_kib = NULL
                    WHERE id = 1
                    """,
                    (),
                )

            with pytest.raises(RuntimeError, match="kdf_memory_cost_kib is NULL"):
                auth.verify_password("abcd")
        finally:
            session.close()
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_password_transitions_rewrite_file_storage_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    file_registry.reset()
    try:
        session = SafeSession()
        try:
            auth = AuthService(session)
            record = create_file(
                original_filename="transition.pdf",
                mime_type="application/pdf",
                content_bytes=b"transition-bytes",
                token="token",
            )

            with connect_file_reader() as connection:
                row = fetch_file(connection, record.id)
            assert row is not None
            assert row["title"] == "transition.pdf"
            assert row["title_encryption_nonce"] is None
            assert row["metadata_encryption_nonce"] is None
            assert row["blob_encryption_nonce"] is None

            success, message = auth.set_password("abcd", KDF_TIME_COST)
            assert success, message

            with connect_file_reader() as connection:
                encrypted_row = fetch_file(connection, record.id)
            assert encrypted_row is not None
            assert encrypted_row["title"] != "transition.pdf"
            assert isinstance(encrypted_row["title_encryption_nonce"], bytes)
            assert isinstance(encrypted_row["metadata_encryption_nonce"], bytes)
            assert isinstance(encrypted_row["blob_encryption_nonce"], bytes)

            dek = auth.unwrap_dek_for_password("abcd")
            set_session_dek(dek)
            encrypted_record = get_file_reference_record(record.id, token=None)
            assert encrypted_record.title == "transition.pdf"

            success, message = auth.remove_password("abcd")
            assert success, message

            clear_encryption_key()

            with connect_file_reader() as connection:
                decrypted_row = fetch_file(connection, record.id)
            assert decrypted_row is not None
            assert decrypted_row["title"] == "transition.pdf"
            assert decrypted_row["title_encryption_nonce"] is None
            assert decrypted_row["metadata_encryption_nonce"] is None
            assert decrypted_row["blob_encryption_nonce"] is None
            assert decrypted_row["blob_data"] == b"transition-bytes"

            restored_record = get_file_reference_record(record.id, token=None)
            assert restored_record.title == "transition.pdf"
            assert restored_record.mime_type == "application/pdf"
            assert restored_record.thumbnail_kind == "pdf"
        finally:
            session.close()
    finally:
        file_registry.reset()
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()
