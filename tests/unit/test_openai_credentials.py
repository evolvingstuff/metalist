from __future__ import annotations

from pathlib import Path

import pytest

from app.db.session import begin_writer
from app.db.settings_sql import fetch_settings
from app.db.settings_sql import insert_default_settings
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key
from app.security.encryption import set_encryption_required
from app.services.encryption import EncryptionService
from app.services.openai_credentials import OpenAICredentialStore
import app.services.openai_credentials as credentials_module


_API_KEY = "sk-test-0123456789abcdefghijklmnop"


@pytest.fixture
def credential_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    set_encryption_required(False)
    with begin_writer() as connection:
        insert_default_settings(connection)
    try:
        yield
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def _settings() -> dict[str, object]:
    session = SafeSession()
    try:
        with SafeSession.allow_reads("tests:openai_credentials:settings"):
            settings = fetch_settings(session.connection())
        assert settings is not None
        return settings
    finally:
        session.close()


def test_plaintext_namespace_keeps_openai_key_in_session_memory_only(
    credential_database,
) -> None:
    del credential_database
    store = OpenAICredentialStore()

    status = store.configure(
        token="plaintext-token",
        session_key="session-a",
        api_key=_API_KEY,
    )

    assert status.configured is True
    assert status.persistent is False
    assert store.resolve(token="plaintext-token", session_key="session-a") == _API_KEY
    settings = _settings()
    assert settings["openai_api_key_ciphertext"] is None
    assert settings["openai_api_key_encryption_nonce"] is None
    assert settings["openai_api_key_encryption_tag"] is None

    store.clear_session(session_key="session-a")
    assert store.status(
        token="plaintext-token",
        session_key="session-a",
    ).configured is False
    with pytest.raises(RuntimeError, match="OpenAI API key is not configured"):
        store.resolve(token="plaintext-token", session_key="session-a")


def test_encrypted_namespace_persists_only_ciphertext(
    credential_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del credential_database
    set_encryption_required(True)
    encryption_service = EncryptionService()
    encryption_service.dek = b"d" * 32
    monkeypatch.setattr(
        credentials_module,
        "get_encryption_service_with_token",
        lambda token: encryption_service,
    )
    store = OpenAICredentialStore()

    status = store.configure(
        token="encrypted-token",
        session_key="session-a",
        api_key=_API_KEY,
    )

    assert status.configured is True
    assert status.persistent is True
    settings = _settings()
    ciphertext = settings["openai_api_key_ciphertext"]
    nonce = settings["openai_api_key_encryption_nonce"]
    tag = settings["openai_api_key_encryption_tag"]
    assert isinstance(ciphertext, str)
    assert _API_KEY not in ciphertext
    assert isinstance(nonce, bytes)
    assert isinstance(tag, bytes)

    restarted_store = OpenAICredentialStore()
    assert restarted_store.resolve(
        token="encrypted-token",
        session_key="session-after-restart",
    ) == _API_KEY
    assert restarted_store.status(
        token="encrypted-token",
        session_key="session-after-restart",
    ).persistent is True

    cleared = restarted_store.clear(session_key="session-after-restart")
    assert cleared.configured is False
    cleared_settings = _settings()
    assert cleared_settings["openai_api_key_ciphertext"] is None
    assert cleared_settings["openai_api_key_encryption_nonce"] is None
    assert cleared_settings["openai_api_key_encryption_tag"] is None
