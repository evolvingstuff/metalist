from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db.settings_sql import fetch_settings
from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
from app.services.client_state_service import load_client_preferences
from app.services.client_state_service import load_client_state
from app.services.client_state_service import load_command_palette_usage
from app.services.client_state_service import save_client_preferences
from app.services.client_state_service import save_command_palette_usage


@pytest.fixture
def memory_settings_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    set_encryption_required(False)
    try:
        yield
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_load_client_state_returns_empty_objects_when_settings_row_is_missing(
    memory_settings_db,
) -> None:
    del memory_settings_db

    assert load_client_preferences() == {}
    assert load_command_palette_usage() == {}
    assert load_client_state() == {
        "preferences": {},
        "command_palette_usage": {},
    }


def test_save_client_preferences_round_trips_through_app_settings(
    memory_settings_db,
) -> None:
    del memory_settings_db

    expected_preferences = {
        "pref.show_note_tags": "true",
        "pref.show_rhs_panel": "false",
        "pref.reminder_surface_expanded": "false",
        "pref.theme": "dark",
    }

    saved = save_client_preferences(preferences=expected_preferences)

    assert saved == expected_preferences
    assert load_client_preferences() == expected_preferences

    session = SafeSession()
    try:
        with SafeSession.allow_reads("tests:client_state:preferences"):
            settings = fetch_settings(session.connection())
        assert settings is not None
        assert json.loads(settings["client_preferences_json"]) == expected_preferences
    finally:
        session.close()


def test_save_command_palette_usage_round_trips_through_app_settings(
    memory_settings_db,
) -> None:
    del memory_settings_db

    expected_usage = {
        "command.logout": {
            "count": 2,
            "lastUsedAt": 1234567890,
            "lastQueryTokens": ["logout"],
        },
    }

    saved = save_command_palette_usage(usage_state=expected_usage)

    assert saved == expected_usage
    assert load_command_palette_usage() == expected_usage
    assert load_client_state() == {
        "preferences": {},
        "command_palette_usage": expected_usage,
    }

    session = SafeSession()
    try:
        with SafeSession.allow_reads("tests:client_state:usage"):
            settings = fetch_settings(session.connection())
        assert settings is not None
        assert json.loads(settings["command_palette_usage_json"]) == expected_usage
    finally:
        session.close()


def test_save_client_preferences_rejects_unknown_preference_key(
    memory_settings_db,
) -> None:
    del memory_settings_db

    with pytest.raises(RuntimeError, match="Unknown client preference key"):
        save_client_preferences(preferences={"pref.not-real": "dark"})


def test_save_command_palette_usage_rejects_invalid_usage_record(
    memory_settings_db,
) -> None:
    del memory_settings_db

    with pytest.raises(RuntimeError, match="Usage count for command.logout must be a positive integer"):
        save_command_palette_usage(
            usage_state={
                "command.logout": {
                    "count": 0,
                    "lastUsedAt": 1234567890,
                    "lastQueryTokens": ["logout"],
                },
            },
        )
