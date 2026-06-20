from __future__ import annotations

from types import SimpleNamespace

import app.api.routes.auth as auth_route


class _FakeUserVersionCursor:
    def fetchone(self):
        return (42,)


class _FakeConnection:
    def execute(self, statement: str):
        assert statement == "PRAGMA user_version"
        return _FakeUserVersionCursor()


class _FakeDb:
    def connection(self):
        return _FakeConnection()


def test_get_session_timeout_settings_returns_current_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setattr(auth_route, "get_session_timeout_minutes", lambda: 55)

    response = auth_route.get_session_timeout_settings(token="token")

    assert response.idle_timeout_minutes == 55


def test_put_session_timeout_settings_saves_timeout_and_refreshes_active_tokens(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def _save_session_timeout_minutes(*, timeout_minutes: int) -> int:
        captured["timeout_minutes"] = timeout_minutes
        return timeout_minutes

    def _refresh_active_tokens_for_current_timeout() -> None:
        captured["refreshed"] = True

    monkeypatch.setattr(auth_route, "save_session_timeout_minutes", _save_session_timeout_minutes)
    monkeypatch.setattr(
        auth_route.token_service,
        "refresh_active_tokens_for_current_timeout",
        _refresh_active_tokens_for_current_timeout,
    )

    payload = auth_route.SessionTimeoutUpdateRequest(idle_timeout_minutes=75)
    response = auth_route.put_session_timeout_settings(payload=payload, token="token")

    assert captured == {
        "timeout_minutes": 75,
        "refreshed": True,
    }
    assert response.idle_timeout_minutes == 75


def test_put_session_timeout_settings_allows_disabling_timeout(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def _save_session_timeout_minutes(*, timeout_minutes: int) -> int:
        captured["timeout_minutes"] = timeout_minutes
        return timeout_minutes

    monkeypatch.setattr(auth_route, "save_session_timeout_minutes", _save_session_timeout_minutes)
    monkeypatch.setattr(
        auth_route.token_service,
        "refresh_active_tokens_for_current_timeout",
        lambda: captured.__setitem__("refreshed", True),
    )

    payload = auth_route.SessionTimeoutUpdateRequest(idle_timeout_minutes=0)
    response = auth_route.put_session_timeout_settings(payload=payload, token="token")

    assert captured == {
        "timeout_minutes": 0,
        "refreshed": True,
    }
    assert response.idle_timeout_minutes == 0


def test_auth_status_reports_app_and_database_versions(monkeypatch) -> None:
    class FakeAuthService:
        def __init__(self, db):
            assert isinstance(db, _FakeDb)

        def get_settings(self):
            return SimpleNamespace(
                encryption_enabled=False,
                encryption_algorithm=None,
                vault_version=None,
                kdf_algorithm=None,
                kdf_memory_cost_kib=None,
                kdf_parallelism=None,
            )

        def has_password(self):
            return False

    monkeypatch.setattr(auth_route, "AuthService", FakeAuthService)
    monkeypatch.setattr(auth_route.auth_cache_state, "cache_refresh_needed", lambda: False)
    monkeypatch.setattr(auth_route, "load_client_preferences", lambda: {})

    payload = auth_route.auth_status(db=_FakeDb(), token="token")

    assert payload["version"] == auth_route.VERSION
    assert payload["database_user_version"] == 42
    assert payload["authenticated"] is True
    assert payload["namespace"] == auth_route.ACTIVE_NAMESPACE
