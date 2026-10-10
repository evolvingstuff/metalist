"""Link titles from oEmbed, and titles that are only the site's name
(docs/ui/content-formatting.md)."""

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

import app.services.link_titles as link_titles
from app.db.link_titles_sql import fetch_all_link_title_rows, insert_link_title_row
from app.db.schema import initialize_schema
from app.services.link_titles import (
    _HostPacer,
    _LinkTitleFetchResult,
    _ResolvedHttpTarget,
    _fetch_result_from_extracted_title,
    _is_placeholder_title,
    _is_site_name_title,
    _pacing_host,
    fetch_link_title,
    link_title_store,
)

POST = "https://www.reddit.com/r/IAmA/comments/z1c9z/i_am_barack_obama_president_of_the_united_states/"
POST_TITLE = "I am Barack Obama, President of the United States -- AMA"
PAGE_HTML = b"<html><head><title>Reddit - Dive into anything</title></head></html>"


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch):
    """Serve requests from `routes` (URL prefix -> response); records what was requested."""
    monkeypatch.setattr(link_titles, "_host_pacer", _HostPacer())
    monkeypatch.setattr(link_titles, "_HOST_REQUEST_SPACING_SECONDS", 0.0)
    monkeypatch.setattr(
        link_titles, "_resolve_public_http_target",
        lambda url: _ResolvedHttpTarget(hostname=_pacing_host(url), port=443, public_addresses=("93.184.216.34",)),
    )
    routes: dict[str, httpx.Response] = {}
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        for prefix, response in routes.items():
            if url.startswith(prefix):
                return response
        return httpx.Response(404)

    monkeypatch.setattr(link_titles, "_PinnedHTTPTransport", lambda **_kwargs: httpx.MockTransport(respond))
    return routes, requested


def _json(payload: object) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(payload).encode())


def test_a_reddit_post_gets_its_real_title_from_oembed(network) -> None:
    routes, requested = network
    routes["https://www.reddit.com/oembed?url="] = _json({"title": POST_TITLE, "provider_name": "reddit"})

    assert fetch_link_title(POST) == _LinkTitleFetchResult(url=POST, title=POST_TITLE, status="ok", last_error_kind=None)
    # The post page itself is never requested.
    assert len(requested) == 1
    assert parse_qs(urlsplit(requested[0]).query)["url"] == [POST]


def test_a_reddit_share_link_gets_the_title_of_the_post_it_forwards_to(network) -> None:
    routes, requested = network
    share = "https://www.reddit.com/r/neurobiology/s/haxo2NUSIs"
    post = "https://www.reddit.com/r/neurobiology/comments/1sy75op/abdominal_movement_flushes_neural_waste/?share_id=x"
    routes[share] = httpx.Response(301, headers={"location": post})
    oembed = "https://www.reddit.com/oembed?url="
    routes[oembed + "https%3A%2F%2Fwww.reddit.com%2Fr%2Fneurobiology%2Fcomments"] = _json(
        {"title": "Abdominal Movement Flushes Neural Waste"})
    # oEmbed rejects the share link itself.
    routes[oembed] = httpx.Response(400, content=b"invalid URL value")

    assert fetch_link_title(share) == _LinkTitleFetchResult(
        url=share, title="Abdominal Movement Flushes Neural Waste", status="ok", last_error_kind=None)
    assert [parse_qs(urlsplit(url).query)["url"] for url in requested if url.startswith(oembed)] == [[share], [post]]


def test_short_youtube_links_ask_youtube_s_oembed(network) -> None:
    routes, requested = network
    routes["https://www.youtube.com/oembed?format=json&url="] = _json({"title": "A video"})
    assert fetch_link_title("https://youtu.be/dQw4w9WgXcQ").title == "A video"
    assert parse_qs(urlsplit(requested[0]).query)["url"] == ["https://youtu.be/dQw4w9WgXcQ"]


@pytest.mark.parametrize("oembed_response", [
    httpx.Response(404),
    httpx.Response(401),
    httpx.Response(200, content=b"not json"),
    _json({"provider_name": "reddit"}),
    _json({"title": ""}),
    _json({"title": "Reddit"}),
    _json(["a list"]),
])
def test_without_a_usable_oembed_answer_the_page_is_read(network, oembed_response) -> None:
    routes, requested = network
    routes["https://www.reddit.com/oembed?url="] = oembed_response
    routes[POST] = httpx.Response(200, headers={"content-type": "text/html"},
                                  content=b"<html><head><title>A post title</title></head></html>")

    assert fetch_link_title(POST).title == "A post title"
    assert requested[-1] == POST


def test_a_rate_limited_oembed_service_pauses_the_site(network) -> None:
    routes, requested = network
    routes["https://www.reddit.com/oembed?url="] = httpx.Response(429, headers={"Retry-After": "120"})

    first = fetch_link_title(POST)
    assert (first.status, first.last_error_kind) == ("failed", "http_429")
    assert fetch_link_title("https://old.reddit.com/r/IAmA/comments/z1c9z/").status == "deferred"
    assert len(requested) == 1


def test_sites_without_oembed_are_read_as_before(network) -> None:
    routes, requested = network
    routes["https://example.com/"] = httpx.Response(200, headers={"content-type": "text/html"},
                                                    content=b"<html><head><title>Example Domain</title></head></html>")
    assert fetch_link_title("https://example.com/").title == "Example Domain"
    assert requested == ["https://example.com/"]


def test_reddit_s_generic_page_title_is_no_title(network) -> None:
    routes, _requested = network
    routes[POST] = httpx.Response(200, headers={"content-type": "text/html"}, content=PAGE_HTML)
    result = fetch_link_title(POST)
    assert (result.status, result.title) == ("no_title", None)


@pytest.mark.parametrize(("title", "url"), [
    ("Reddit", "https://www.reddit.com/r/x/comments/abc/post/"),
    ("reddit.com", "https://old.reddit.com/r/x/"),
    ("YouTube", "https://www.youtube.com/watch?v=abc"),
    ("Spotify", "https://open.spotify.com/track/abc"),
    ("BBC", "https://www.bbc.co.uk/news/articles/abc"),
    ("X", "https://x.com/someone/status/1"),
    ("Git Hub", "https://github.com/"),
])
def test_a_title_that_is_only_the_site_s_name_is_no_title(title: str, url: str) -> None:
    assert _is_site_name_title(title=title, url=url)
    assert _fetch_result_from_extracted_title(url=url, title=title) == _LinkTitleFetchResult(
        url=url, title=None, status="no_title", last_error_kind="site_name_title")


@pytest.mark.parametrize(("title", "url"), [
    ("Reddit's new API pricing explained", "https://www.reddit.com/r/x/comments/abc/post/"),
    ("BBC News - Home", "https://www.bbc.co.uk/news"),
    ("John Doe's blog", "https://johndoe.com/"),
    ("Never Gonna Give You Up", "https://open.spotify.com/track/abc"),
])
def test_titles_that_say_more_than_the_site_s_name_are_kept(title: str, url: str) -> None:
    assert not _is_placeholder_title(title=title, url=url)


def test_a_site_name_title_saved_earlier_is_cleared_at_the_next_login() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_schema(connection)
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    insert_link_title_row(
        connection, url=POST, url_encryption_nonce=None, url_encryption_tag=None, title="Reddit",
        title_encryption_nonce=None, title_encryption_tag=None, status="ok", last_error_kind=None,
        last_checked_at=now, last_success_at=now, last_failure_at=None,
        next_check_after=now + timedelta(days=90), failure_count=0, created_at=now, updated_at=now,
    )
    try:
        link_title_store.bootstrap(connection=connection)
        displayed_title = link_title_store.get_ok_title(POST)
        rows = fetch_all_link_title_rows(connection)
    finally:
        link_title_store.reset()
        connection.close()

    assert displayed_title is None
    assert rows[0]["status"] == "no_title"
