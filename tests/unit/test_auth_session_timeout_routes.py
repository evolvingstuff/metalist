from __future__ import annotations

import app.api.routes.auth as auth_route


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
