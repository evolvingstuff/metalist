from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

import app.api.routes.auth as auth_route


def test_login_does_not_decrypt_file_metadata_before_hydration(monkeypatch) -> None:
    class _AuthService:
        def has_password(self) -> bool:
            return True

        def verify_password(self, password: str) -> bool:
            return password == "abcd"

        def unwrap_dek_for_password(self, password: str) -> bytes:
            assert password == "abcd"
            return b"d" * 32

        def run_authenticated_database_migrations(self, *, dek: bytes) -> None:
            assert dek == b"d" * 32

    monkeypatch.setattr(auth_route, "AuthService", lambda db: _AuthService())
    monkeypatch.setattr(auth_route.login_rate_limiter, "check_allowed", lambda key: (True, 0))
    monkeypatch.setattr(auth_route.login_rate_limiter, "record_success", lambda key: None)
    monkeypatch.setattr(auth_route, "set_session_dek", lambda dek: None)
    monkeypatch.setattr(auth_route, "ensure_rules_decrypted_and_compiled", lambda *, token: None)
    monkeypatch.setattr(auth_route.tab_state_store, "ensure_decrypted", lambda *, token: None)
    monkeypatch.setattr(auth_route.link_title_store, "ensure_decrypted", lambda *, token: None)
    monkeypatch.setattr(auth_route.reminder_store, "ensure_decrypted", lambda *, token: None)
    monkeypatch.setattr(auth_route.search_history_store, "ensure_decrypted", lambda *, token: None)
    monkeypatch.setattr(
        auth_route,
        "bootstrap_file_registry",
        lambda: (_ for _ in ()).throw(AssertionError("file metadata belongs to hydration")),
    )
    monkeypatch.setattr(auth_route.token_service, "create_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(auth_route, "set_auth_cookie", lambda **kwargs: None)
    monkeypatch.setattr(auth_route, "clear_all_locks", lambda: None)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api2/auth/login",
            "raw_path": b"/api2/auth/login",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8000),
        }
    )

    login_impl = auth_route.login.__wrapped__
    result = login_impl(
        request=request,
        response=Response(),
        payload=auth_route.LoginRequest(password="abcd"),
        tab_id="tab-id",
        db=object(),
    )

    assert result.message == "Login successful"
