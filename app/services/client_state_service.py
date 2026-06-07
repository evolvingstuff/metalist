from __future__ import annotations

import json
import re

from app.db.session import begin_writer
from app.db.settings_sql import (
    fetch_settings,
    insert_default_settings,
    update_client_preferences_json,
    update_command_palette_usage_json,
)
from app.models.database import SafeSession


_ALLOWED_CLIENT_PREFERENCES = {
    "pref.show_backlinks": {"true", "false"},
    "pref.show_note_tags": {"true", "false"},
    "pref.show_tab_ui": {"true", "false"},
    "pref.show_rhs_panel": {"true", "false"},
    "pref.show_perf_overlay": {"true", "false"},
    "pref.reminder_surface_expanded": {"true", "false"},
    "pref.reminder_default_popup_sound_enabled": {"true", "false"},
    "pref.reminder_default_popup_sound_id": "sound_id",
    "pref.reminder_default_ack_sound_enabled": {"true", "false"},
    "pref.reminder_default_ack_sound_id": "sound_id",
    "pref.theme": {"system", "light", "dark"},
}

_OBSOLETE_CLIENT_PREFERENCES = frozenset(
    {
        "pref.reminder_popup_sound_enabled",
        "pref.reminder_ack_sound_enabled",
        "pref.reminder_popup_sound_id",
        "pref.reminder_ack_sound_id",
    }
)

_BUILTIN_DEFAULT_SOUND_ID = "builtin.default_chime"
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _parse_json_object(*, raw_json: object, label: str) -> dict[str, object]:
    if not isinstance(label, str) or label == "":
        raise ValueError("label must be a non-empty string")
    if raw_json is None:
        return {}
    if not isinstance(raw_json, str):
        raise RuntimeError(f"{label} must be stored as a string")
    if raw_json == "":
        return {}

    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} must decode to an object")
    normalized: dict[str, object] = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            raise RuntimeError(f"{label} keys must be strings")
        normalized[key] = value
    return normalized


def _serialize_json_object(*, payload: dict[str, object], label: str) -> str:
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be a dict")
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _validate_client_preferences(preferences: dict[str, object]) -> dict[str, str]:
    if not isinstance(preferences, dict):
        raise TypeError("preferences must be a dict")

    normalized: dict[str, str] = {}
    for key, value in preferences.items():
        if not isinstance(key, str) or key == "":
            raise RuntimeError("client preference keys must be non-empty strings")
        if key in _OBSOLETE_CLIENT_PREFERENCES:
            continue
        if key not in _ALLOWED_CLIENT_PREFERENCES:
            raise RuntimeError(f"Unknown client preference key: {key}")
        if not isinstance(value, str):
            raise RuntimeError(f"Client preference {key} must be a string")
        allowed_values = _ALLOWED_CLIENT_PREFERENCES[key]
        if allowed_values == "sound_id":
            _validate_sound_preference_value(key=key, value=value)
        elif value not in allowed_values:
            raise RuntimeError(f"Invalid client preference value for {key}: {value}")
        normalized[key] = value
    return normalized


def _validate_sound_preference_value(*, key: str, value: str) -> None:
    if value == _BUILTIN_DEFAULT_SOUND_ID:
        return
    if _UUID_PATTERN.fullmatch(value) is None:
        raise RuntimeError(f"Invalid client preference value for {key}: {value}")


def _validate_usage_state(usage_state: dict[str, object]) -> dict[str, dict[str, object]]:
    if not isinstance(usage_state, dict):
        raise TypeError("usage_state must be a dict")

    normalized: dict[str, dict[str, object]] = {}
    for endpoint_id, raw_record in usage_state.items():
        if not isinstance(endpoint_id, str) or endpoint_id == "":
            raise RuntimeError("usage endpoint ids must be non-empty strings")
        if not isinstance(raw_record, dict):
            raise RuntimeError(f"Usage record for {endpoint_id} must be an object")
        if "count" not in raw_record:
            raise RuntimeError(f"Usage record for {endpoint_id} missing count")
        if "lastUsedAt" not in raw_record:
            raise RuntimeError(f"Usage record for {endpoint_id} missing lastUsedAt")
        if "lastQueryTokens" not in raw_record:
            raise RuntimeError(f"Usage record for {endpoint_id} missing lastQueryTokens")

        count = raw_record["count"]
        last_used_at = raw_record["lastUsedAt"]
        last_query_tokens = raw_record["lastQueryTokens"]

        if not isinstance(count, int) or count < 1:
            raise RuntimeError(f"Usage count for {endpoint_id} must be a positive integer")
        if not isinstance(last_used_at, int) or last_used_at < 0:
            raise RuntimeError(f"Usage lastUsedAt for {endpoint_id} must be a non-negative integer")
        if not isinstance(last_query_tokens, list):
            raise RuntimeError(f"Usage lastQueryTokens for {endpoint_id} must be a list")

        normalized_tokens: list[str] = []
        for token in last_query_tokens:
            if not isinstance(token, str):
                raise RuntimeError(f"Usage lastQueryTokens for {endpoint_id} must be strings")
            normalized_tokens.append(token)

        normalized[endpoint_id] = {
            "count": count,
            "lastUsedAt": last_used_at,
            "lastQueryTokens": normalized_tokens,
        }
    return normalized


def load_client_preferences() -> dict[str, str]:
    session = SafeSession()
    try:
        with SafeSession.allow_reads("client_state:load_preferences"):
            settings = fetch_settings(session.connection())
        if settings is None:
            return {}
        parsed = _parse_json_object(
            raw_json=settings["client_preferences_json"],
            label="client_preferences_json",
        )
        return _validate_client_preferences(parsed)
    finally:
        session.close()


def save_client_preferences(*, preferences: dict[str, object]) -> dict[str, str]:
    normalized = _validate_client_preferences(preferences)
    serialized = _serialize_json_object(payload=normalized, label="preferences")
    with begin_writer() as connection:
        insert_default_settings(connection)
        update_client_preferences_json(connection, client_preferences_json=serialized)
    return normalized


def load_command_palette_usage() -> dict[str, dict[str, object]]:
    session = SafeSession()
    try:
        with SafeSession.allow_reads("client_state:load_usage"):
            settings = fetch_settings(session.connection())
        if settings is None:
            return {}
        parsed = _parse_json_object(
            raw_json=settings["command_palette_usage_json"],
            label="command_palette_usage_json",
        )
        return _validate_usage_state(parsed)
    finally:
        session.close()


def save_command_palette_usage(*, usage_state: dict[str, object]) -> dict[str, dict[str, object]]:
    normalized = _validate_usage_state(usage_state)
    serialized = _serialize_json_object(payload=normalized, label="usage_state")
    with begin_writer() as connection:
        insert_default_settings(connection)
        update_command_palette_usage_json(connection, command_palette_usage_json=serialized)
    return normalized


def load_client_state() -> dict[str, object]:
    return {
        "preferences": load_client_preferences(),
        "command_palette_usage": load_command_palette_usage(),
    }
