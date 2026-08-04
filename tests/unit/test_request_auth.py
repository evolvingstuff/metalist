from __future__ import annotations

from fastapi import HTTPException
from fastapi import Response
import pytest
from starlette.requests import Request

from app.api.request_auth import AUTH_COOKIE_NAME
from app.api.request_auth import auth_cookie_name_for_namespace
from app.api.request_auth import clear_auth_cookie
from app.api.request_auth import get_request_auth_token
from app.api.request_auth import read_request_auth_token
from app.api.request_auth import require_request_auth_token
from app.api.request_auth import set_auth_cookie


def test_auth_cookie_names_are_scoped_to_namespace() -> None:
    assert auth_cookie_name_for_namespace("default") == "metalist_auth_default"
    assert auth_cookie_name_for_namespace("cla") == "metalist_auth_cla"
    assert auth_cookie_name_for_namespace("default") != auth_cookie_name_for_namespace("cla")


def _build_request(
    *,
    scheme: str,
    authorization: str | None,
    cookie_token: str | None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = [
        (b"host", b"testserver"),
    ]
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("utf-8")))
    if cookie_token is not None:
        headers.append((b"cookie", f"{AUTH_COOKIE_NAME}={cookie_token}".encode("utf-8")))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443 if scheme == "https" else 80),
    }
    return Request(scope)


def test_get_request_auth_token_returns_bearer_header_token() -> None:
    request = _build_request(
        scheme="http",
        authorization="Bearer header-token",
        cookie_token=None,
    )

    assert get_request_auth_token(request) == "header-token"


def test_get_request_auth_token_prefers_header_token_over_cookie() -> None:
    request = _build_request(
        scheme="http",
        authorization="Bearer header-token",
        cookie_token="cookie-token",
    )

    assert get_request_auth_token(request) == "header-token"


def test_get_request_auth_token_returns_cookie_token_when_header_missing() -> None:
    request = _build_request(
        scheme="http",
        authorization=None,
        cookie_token="cookie-token",
    )

    assert get_request_auth_token(request) == "cookie-token"


def test_read_request_auth_token_reports_invalid_authorization_header_without_raising() -> None:
    request = _build_request(
        scheme="http",
        authorization="Basic abc123",
        cookie_token=None,
    )

    assert read_request_auth_token(request) == (None, "Invalid Authorization header")


def test_get_request_auth_token_rejects_invalid_authorization_header() -> None:
    request = _build_request(
        scheme="http",
        authorization="Basic abc123",
        cookie_token=None,
    )

    with pytest.raises(HTTPException, match="Invalid Authorization header"):
        get_request_auth_token(request)


def test_require_request_auth_token_raises_when_request_has_no_token() -> None:
    request = _build_request(
        scheme="http",
        authorization=None,
        cookie_token=None,
    )

    with pytest.raises(HTTPException, match="Authentication required"):
        require_request_auth_token(request)


def test_set_auth_cookie_adds_http_only_cookie_for_https_requests() -> None:
    request = _build_request(
        scheme="https",
        authorization=None,
        cookie_token=None,
    )
    response = Response()

    set_auth_cookie(request=request, response=response, token="token-123")

    cookie_header = response.headers["set-cookie"]
    assert f"{AUTH_COOKIE_NAME}=token-123" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Secure" in cookie_header


def test_set_auth_cookie_omits_secure_attribute_for_http_requests() -> None:
    request = _build_request(
        scheme="http",
        authorization=None,
        cookie_token=None,
    )
    response = Response()

    set_auth_cookie(request=request, response=response, token="token-123")

    cookie_header = response.headers["set-cookie"]
    assert "Secure" not in cookie_header


def test_clear_auth_cookie_sets_cookie_expiration() -> None:
    response = Response()

    clear_auth_cookie(response=response)

    cookie_header = response.headers["set-cookie"]
    assert f"{AUTH_COOKIE_NAME}=" in cookie_header
    assert "Max-Age=0" in cookie_header
    assert "expires=" in cookie_header.lower()
