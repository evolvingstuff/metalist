"""A password namespace's page opens straight on the login screen when a login is
certain, so there is no white page before the browser checks its session."""

from pathlib import Path

from starlette.requests import Request

from app.api.request_auth import AUTH_COOKIE_NAME
from app.presentation.login_page import login_is_certainly_needed
from app.presentation.templates import get_templates

TEMPLATES = get_templates(template_directory=Path(__file__).resolve().parents[2] / "app" / "templates")


def _request(*, query: str, cookie: str) -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": query.encode(), "headers": headers})


def test_without_a_session_cookie_the_login_screen_shows_at_once() -> None:
    assert login_is_certainly_needed(_request(query="", cookie="")) is True


def test_go_to_login_from_the_locked_page_shows_the_login_screen_at_once() -> None:
    request = _request(query="force_reauth=1", cookie=f"{AUTH_COOKIE_NAME}=still-the-other-tab")
    assert login_is_certainly_needed(request) is True


def test_a_browser_with_a_session_waits_for_its_check_instead() -> None:
    # It may be logged in already (a reload), so the app is not hidden behind a dark screen.
    request = _request(query="", cookie=f"{AUTH_COOKIE_NAME}=a-session")
    assert login_is_certainly_needed(request) is False


def test_the_page_renders_each_way() -> None:
    template = TEMPLATES.get_template("index.html")
    shared = {"version": "0", "asset_version": "0", "page_title": "MetaList", "needs_auth": True}

    request = _request(query="", cookie="")
    request.state.csp_nonce = "n" * 32
    at_once = template.render(request=request, shows_login_at_once=True, **shared)
    later = template.render(request=request, shows_login_at_once=False, **shared)
    assert 'id="login-page" class="login-page" style="display: flex;"' in at_once
    assert '<div id="main-app" style="display: none;">' in at_once
    assert 'id="login-page" class="login-page" style="display: none;"' in later
    assert '<div id="main-app" style="display: block;">' in later
