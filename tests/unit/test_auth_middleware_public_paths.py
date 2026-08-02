from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request
from starlette.responses import Response

import app.api.middleware.auth as auth_middleware
from app.api.middleware.auth import AuthMiddleware


@pytest.mark.parametrize(
    "path",
    (
        "/namespace-renamed?job=11111111-1111-1111-1111-111111111111",
        "/namespace-renamed/open?job=11111111-1111-1111-1111-111111111111",
        "/api2/auth/namespaces/rename-jobs/11111111-1111-1111-1111-111111111111",
    ),
)
def test_namespace_rename_restart_routes_do_not_require_tab_auth(path: str) -> None:
    request_path = path.partition("?")[0]

    assert any(request_path.startswith(public_path) for public_path in AuthMiddleware.PUBLIC_PATHS)


@pytest.mark.parametrize("path", ("/api2/mcp", "/mcp-client", "/mcp-client-v2"))
def test_removed_agent_routes_are_not_public(path: str) -> None:
    assert not any(path.startswith(public_path) for public_path in AuthMiddleware.PUBLIC_PATHS)


def test_request_after_session_expiry_purges_decrypted_runtime_state(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(auth_middleware.token_service, "has_active_tokens", lambda: False)
    monkeypatch.setattr(
        auth_middleware,
        "purge_decrypted_runtime_state",
        lambda: calls.append("purge") or True,
    )
    middleware = AuthMiddleware(lambda scope, receive, send: None)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/api2/auth/status",
            "raw_path": b"/api2/auth/status",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8000),
        }
    )

    async def _call_next(_request: Request) -> Response:
        return Response(status_code=200)

    response = asyncio.run(middleware.dispatch(request, _call_next))

    assert response.status_code == 200
    assert calls == ["purge"]
