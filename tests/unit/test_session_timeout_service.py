from __future__ import annotations

from pathlib import Path

import pytest

from app.config import DEFAULT_TOKEN_EXPIRY_MINUTES
from app.db.settings_sql import fetch_settings
from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
from app.services.session_timeout_service import (
    MAX_SESSION_TIMEOUT_MINUTES,
    MIN_SESSION_TIMEOUT_MINUTES,
    get_session_timeout_minutes,
    reset_session_timeout_cache,
    save_session_timeout_minutes,
)


@pytest.fixture
def memory_settings_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    set_encryption_required(False)
    reset_session_timeout_cache()
    try:
        yield
    finally:
        reset_session_timeout_cache()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_get_session_timeout_minutes_returns_default_when_settings_row_missing(
    memory_settings_db,
) -> None:
    del memory_settings_db

    assert get_session_timeout_minutes() == DEFAULT_TOKEN_EXPIRY_MINUTES


def test_save_session_timeout_minutes_round_trips_through_app_settings(
    memory_settings_db,
) -> None:
    del memory_settings_db

    saved = save_session_timeout_minutes(timeout_minutes=45)

    assert saved == 45
    assert get_session_timeout_minutes() == 45

    session = SafeSession()
    try:
        with SafeSession.allow_reads("tests:session_timeout:settings"):
            settings = fetch_settings(session.connection())
        assert settings is not None
        assert settings["session_timeout_minutes"] == 45
    finally:
        session.close()


def test_save_session_timeout_minutes_accepts_zero_to_disable_timeout(
    memory_settings_db,
) -> None:
    del memory_settings_db

    saved = save_session_timeout_minutes(timeout_minutes=0)

    assert saved == 0
    assert get_session_timeout_minutes() == 0


def test_save_session_timeout_minutes_rejects_out_of_range_values(
    memory_settings_db,
) -> None:
    del memory_settings_db

    with pytest.raises(RuntimeError, match="must be >="):
        save_session_timeout_minutes(timeout_minutes=MIN_SESSION_TIMEOUT_MINUTES - 1)

    with pytest.raises(RuntimeError, match="must be <="):
        save_session_timeout_minutes(timeout_minutes=MAX_SESSION_TIMEOUT_MINUTES + 1)
