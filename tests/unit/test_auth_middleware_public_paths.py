from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request
from starlette.responses import Response

import app.api.middleware.auth as auth_middleware
from app.api.middleware.auth import AuthMiddleware
from app.api.routes.auth import router as auth_router
from app.config import API_PREFIX


def test_auth_router_public_route_inventory_is_explicit_and_complete() -> None:
    expected_public_paths = {
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/auth/login-namespaces",
        f"{API_PREFIX}/auth/login-namespaces/open",
        f"{API_PREFIX}/auth/namespaces/delete-jobs/{{job_id}}",
        f"{API_PREFIX}/auth/namespaces/rename-jobs/{{job_id}}",
        f"{API_PREFIX}/auth/session",
        f"{API_PREFIX}/auth/status",
    }
    declared_paths = {
        f"{API_PREFIX}{route.path}"
        for route in auth_router.routes
    }
    actual_public_paths = {
        path
        for path in declared_paths
        if AuthMiddleware.is_public_path(path=path)
    }

    assert actual_public_paths == expected_public_paths


@pytest.mark.parametrize(
    "path",
    (
        "/",
        "/api2/auth/login",
        "/api2/auth/login-namespaces",
        "/api2/auth/login-namespaces/open",
        "/api2/auth/session",
        "/api2/auth/status",
        "/locked",
        "/namespace-renamed?job=11111111-1111-1111-1111-111111111111",
        "/namespace-renamed/open?job=11111111-1111-1111-1111-111111111111",
        "/api2/auth/namespaces/rename-jobs/11111111-1111-1111-1111-111111111111",
        "/namespace-deleted?job=11111111-1111-1111-1111-111111111111",
        "/namespace-deleted/open?job=11111111-1111-1111-1111-111111111111",
        "/api2/auth/namespaces/delete-jobs/11111111-1111-1111-1111-111111111111",
        "/static/js/main.js",
    ),
)
def test_explicit_pre_authentication_routes_are_public(path: str) -> None:
    request_path = path.partition("?")[0]

    assert AuthMiddleware.is_public_path(path=request_path) is True


@pytest.mark.parametrize(
    "path",
    (
        "/api2/auth/sessions",
        "/api2/auth/login-evil",
        "/api2/auth/status-details",
        "/api2/auth/session/claim",
        "/api2/mcp",
        "/dev/use-dev-db",
        "/dev/use-file-db",
        "/mcp-client",
        "/mcp-client-v2",
    ),
)
def test_routes_outside_the_exact_allowlist_are_not_public(path: str) -> None:
    assert AuthMiddleware.is_public_path(path=path) is False


def test_public_status_request_after_session_expiry_preserves_warm_runtime_state(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        auth_middleware.token_service,
        "has_active_tokens",
        lambda: (_ for _ in ()).throw(
            AssertionError("session expiry must not tear down the hydrated runtime")
        ),
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
