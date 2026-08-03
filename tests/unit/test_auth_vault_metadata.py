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
from app.db.session import connect_reader
from app.db.settings_sql import fetch_settings
from app.db.tab_state_sql import fetch_tab_state_row
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key, set_encryption_required, set_session_dek
from app.services.auth_service import AuthService
from app.services.file_registry import file_registry
from app.services.file_storage import create_file, get_file_reference_record
from app.services.search_history import list_recent_search_tags, record_search_interaction
from app.services.search_index import SearchIndex, SearchRecord, extract_tags_for_search
from app.services.tab_state import TabStateStore, tab_state_store
import app.services.search_history as search_history_module


def _reset_search_history_state() -> None:
    search_history_module.search_history_store.clear_persisted_state_for_tests()


def _fetch_search_history_row():
    with connect_reader("tests:auth_vault_metadata:search_history") as connection:
        return connection.execute(
            """
            SELECT
                query_key,
                query_key_encryption_nonce,
                tags_json_encryption_nonce
            FROM search_interaction_history
            LIMIT 1
            """
        ).fetchone()


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
            success, message = auth.set_password("aQ7!mZ2#vL9@xR4", KDF_TIME_COST)
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

            assert auth.verify_password("aQ7!mZ2#vL9@xR4") is True
            dek = auth.unwrap_dek_for_password("aQ7!mZ2#vL9@xR4")
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
            success, message = auth.set_password("aQ7!mZ2#vL9@xR4", KDF_TIME_COST)
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
                auth.verify_password("aQ7!mZ2#vL9@xR4")
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
            success, message = auth.set_password("aQ7!mZ2#vL9@xR4", KDF_TIME_COST)
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
                auth.verify_password("aQ7!mZ2#vL9@xR4")
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

            success, message = auth.set_password("aQ7!mZ2#vL9@xR4", KDF_TIME_COST)
            assert success, message

            with connect_file_reader() as connection:
                encrypted_row = fetch_file(connection, record.id)
            assert encrypted_row is not None
            assert encrypted_row["title"] != "transition.pdf"
            assert isinstance(encrypted_row["title_encryption_nonce"], bytes)
            assert isinstance(encrypted_row["metadata_encryption_nonce"], bytes)
            assert isinstance(encrypted_row["blob_encryption_nonce"], bytes)

            dek = auth.unwrap_dek_for_password("aQ7!mZ2#vL9@xR4")
            set_session_dek(dek)
            encrypted_record = get_file_reference_record(record.id, token=None)
            assert encrypted_record.title == "transition.pdf"

            success, message = auth.remove_password("aQ7!mZ2#vL9@xR4")
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


def test_password_transitions_rewrite_search_history_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        _reset_search_history_state()
        index = SearchIndex()
        index.rebuild(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Journal entry",
                    tags="journal",
                    tag_terms=extract_tags_for_search("journal"),
                ),
            ],
            raw_tag_terms_by_id={"n1": extract_tags_for_search("journal")},
            progress_update=lambda _processed: None,
            progress_interval=1000,
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        session = SafeSession()
        try:
            auth = AuthService(session)
            assert record_search_interaction(query="journal", interaction_type="edit", token="token") is True

            row = _fetch_search_history_row()
            assert row is not None
            assert row["query_key"] == "journal"
            assert row["query_key_encryption_nonce"] is None
            assert row["tags_json_encryption_nonce"] is None

            success, message = auth.set_password("aQ7!mZ2#vL9@xR4", KDF_TIME_COST)
            assert success, message

            encrypted_row = _fetch_search_history_row()
            assert encrypted_row is not None
            assert encrypted_row["query_key"] != "journal"
            assert isinstance(encrypted_row["query_key_encryption_nonce"], bytes)
            assert isinstance(encrypted_row["tags_json_encryption_nonce"], bytes)

            dek = auth.unwrap_dek_for_password("aQ7!mZ2#vL9@xR4")
            set_session_dek(dek)
            assert list_recent_search_tags(limit=3, token="token") == ["journal"]

            success, message = auth.remove_password("aQ7!mZ2#vL9@xR4")
            assert success, message

            clear_encryption_key()

            decrypted_row = _fetch_search_history_row()
            assert decrypted_row is not None
            assert decrypted_row["query_key"] == "journal"
            assert decrypted_row["query_key_encryption_nonce"] is None
            assert decrypted_row["tags_json_encryption_nonce"] is None
        finally:
            session.close()
    finally:
        file_registry.reset()
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_password_transitions_rewrite_tab_state_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        tab_state_store.clear_persisted_state_for_tests()
        store = tab_state_store
        initial = store.snapshot()
        tab_id = initial["activeTabId"]
        payload = initial["tabs"]
        payload[tab_id]["searchQuery"] = "focus-tag"
        payload[tab_id]["scrollY"] = 75
        payload[tab_id]["anchorRootId"] = "root-77"
        store.update(
            active_tab_id=tab_id,
            tabs=payload,
            tab_order=initial["tabOrder"],
        )

        session = SafeSession()
        try:
            with SafeSession.allow_reads("tests:auth_vault_metadata:fetch_tab_state_plaintext"):
                row = fetch_tab_state_row(session.connection())
            assert row is not None
            assert row["state_json"] != ""
            assert "focus-tag" in row["state_json"]
            assert row["state_encryption_nonce"] is None
            assert row["state_encryption_tag"] is None

            auth = AuthService(session)
            success, message = auth.set_password("aQ7!mZ2#vL9@xR4", KDF_TIME_COST)
            assert success, message

            with SafeSession.allow_reads("tests:auth_vault_metadata:fetch_tab_state_encrypted"):
                encrypted_row = fetch_tab_state_row(session.connection())
            assert encrypted_row is not None
            assert "focus-tag" not in encrypted_row["state_json"]
            assert isinstance(encrypted_row["state_encryption_nonce"], bytes)
            assert isinstance(encrypted_row["state_encryption_tag"], bytes)

            clear_encryption_key()
            encrypted_store = TabStateStore()
            with SafeSession.allow_reads("tests:auth_vault_metadata:bootstrap_tab_state_encrypted"):
                encrypted_store.bootstrap(connection=session.connection())
            prelogin_snapshot = encrypted_store.snapshot()
            assert prelogin_snapshot["tabs"][prelogin_snapshot["activeTabId"]]["searchQuery"] == ""

            dek = auth.unwrap_dek_for_password("aQ7!mZ2#vL9@xR4")
            set_session_dek(dek)
            encrypted_store.ensure_decrypted(token="")
            decrypted_snapshot = encrypted_store.snapshot()
            assert decrypted_snapshot["tabs"][tab_id]["searchQuery"] == "focus-tag"
            assert decrypted_snapshot["tabs"][tab_id]["anchorRootId"] == "root-77"

            success, message = auth.remove_password("aQ7!mZ2#vL9@xR4")
            assert success, message

            clear_encryption_key()

            with SafeSession.allow_reads("tests:auth_vault_metadata:fetch_tab_state_decrypted"):
                decrypted_row = fetch_tab_state_row(session.connection())
            assert decrypted_row is not None
            assert "focus-tag" in decrypted_row["state_json"]
            assert decrypted_row["state_encryption_nonce"] is None
            assert decrypted_row["state_encryption_tag"] is None
        finally:
            session.close()
    finally:
        clear_encryption_key()
        tab_state_store.reset()
        set_encryption_required(False)
        SafeSession.use_file_db()
