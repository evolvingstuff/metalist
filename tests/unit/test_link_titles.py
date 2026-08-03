from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import socket
import sqlite3

import httpcore
import httpx
import pytest

from app.db.link_titles_sql import fetch_all_link_title_rows
from app.db.link_titles_sql import insert_link_title_row
from app.db.schema import initialize_schema
from app.services.link_titles import LinkTitleRecord
from app.services.link_titles import _LinkTitleFetchResult
from app.services.link_titles import _MAX_RESPONSE_BYTES
from app.services.link_titles import _LinkTitleTargetRejected
from app.services.link_titles import _PinnedNetworkBackend
from app.services.link_titles import _PinnedHTTPTransport
from app.services.link_titles import _ResolvedHttpTarget
from app.services.link_titles import _effective_next_check_after
from app.services.link_titles import _extract_title_from_html
from app.services.link_titles import _fetch_result_from_extracted_title
from app.services.link_titles import _looks_like_interstitial_title
from app.services.link_titles import _next_check_after_for_status
from app.services.link_titles import _resolve_public_http_target
from app.services.link_titles import fetch_link_title
from app.services.link_titles import link_title_store


def test_extract_title_from_html_accepts_common_meta_title_variants() -> None:
    html = b"""
    <html>
      <head>
        <meta name="Title" content="Name Meta Title">
        <meta itemprop="name" content="Itemprop Name Title">
        <title>Fallback Title</title>
      </head>
    </html>
    """

    assert _extract_title_from_html(content=html, encoding="utf-8") == "Name Meta Title"


def test_link_title_fetch_reads_enough_html_for_large_metadata_pages() -> None:
    assert _MAX_RESPONSE_BYTES >= 1024 * 1024


def test_extract_title_from_html_prefers_case_insensitive_open_graph_title() -> None:
    html = b"""
    <html>
      <head>
        <meta property="OG:TITLE" content="Open Graph Title">
        <meta name="title" content="Name Meta Title">
      </head>
    </html>
    """

    assert _extract_title_from_html(content=html, encoding="utf-8") == "Open Graph Title"


def test_interstitial_title_classifier_rejects_verification_pages() -> None:
    assert _looks_like_interstitial_title("Reddit - Please wait for verification")
    assert _looks_like_interstitial_title("Just a moment...")
    assert _looks_like_interstitial_title("Checking if the site connection is secure")
    assert _looks_like_interstitial_title("Access Denied")


def test_interstitial_title_classifier_allows_content_titles() -> None:
    assert not _looks_like_interstitial_title("How Login Systems Work - Example Blog")
    assert not _looks_like_interstitial_title("Security Checklists for Small Teams")
    assert not _looks_like_interstitial_title("Verification Methods in Distributed Systems")


def test_extracted_interstitial_title_becomes_no_title_result() -> None:
    result = _fetch_result_from_extracted_title(
        url="https://example.com/thread",
        title="Reddit - Please wait for verification",
    )

    assert result == _LinkTitleFetchResult(
        url="https://example.com/thread",
        title=None,
        status="no_title",
        last_error_kind="interstitial_title",
    )


def test_bootstrap_rewrites_existing_interstitial_title_cache() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_schema(connection)
    now = datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc)
    insert_link_title_row(
        connection,
        url="https://reddit.com/r/example/comments/abc",
        url_encryption_nonce=None,
        url_encryption_tag=None,
        title="Reddit - Please wait for verification",
        title_encryption_nonce=None,
        title_encryption_tag=None,
        status="ok",
        last_error_kind=None,
        last_checked_at=now,
        last_success_at=now,
        last_failure_at=None,
        next_check_after=now + timedelta(days=90),
        failure_count=0,
        created_at=now,
        updated_at=now,
    )

    try:
        link_title_store.bootstrap(connection=connection)
        revision_after_bootstrap = link_title_store.get_revision()
        displayed_title = link_title_store.get_ok_title("https://reddit.com/r/example/comments/abc")
        rows = fetch_all_link_title_rows(connection)
    finally:
        link_title_store.reset()
        connection.close()

    assert revision_after_bootstrap == 1
    assert displayed_title is None
    assert len(rows) == 1
    assert rows[0]["title"] is None
    assert rows[0]["status"] == "no_title"
    assert rows[0]["last_error_kind"] == "interstitial_title"
    assert rows[0]["last_success_at"] == now
    assert rows[0]["failure_count"] == 1


def test_link_title_revision_increments_after_fetch_result(monkeypatch) -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_schema(connection)

    @contextmanager
    def fake_begin_writer():
        yield connection

    monkeypatch.setattr("app.services.link_titles.begin_writer", fake_begin_writer)

    try:
        link_title_store.bootstrap(connection=connection)
        assert link_title_store.get_revision() == 0
        link_title_store.apply_fetch_result(
            _LinkTitleFetchResult(
                url="https://example.com/article",
                title="Example Article",
                status="ok",
                last_error_kind=None,
            )
        )
        assert link_title_store.get_revision() == 1
    finally:
        link_title_store.reset()
        connection.close()


def test_failed_link_title_retries_quickly_on_first_failure() -> None:
    now = datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc)

    assert (
        _next_check_after_for_status(
            status="failed",
            now=now,
            failure_count=1,
            last_error_kind="timeout",
        )
        == now + timedelta(minutes=1)
    )


def test_no_title_link_title_retries_quickly_on_first_failure() -> None:
    now = datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc)

    assert (
        _next_check_after_for_status(
            status="no_title",
            now=now,
            failure_count=1,
            last_error_kind="no_title",
        )
        == now + timedelta(minutes=1)
    )


def test_ok_link_title_keeps_long_refresh_interval() -> None:
    now = datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc)

    assert (
        _next_check_after_for_status(
            status="ok",
            now=now,
            failure_count=0,
            last_error_kind=None,
        )
        == now + timedelta(days=90)
    )


def test_existing_long_failed_retry_uses_shorter_current_policy() -> None:
    checked_at = datetime(2026, 5, 17, 20, 0, tzinfo=timezone.utc)
    record = LinkTitleRecord(
        id=1,
        url="https://example.com",
        title=None,
        status="failed",
        last_error_kind="timeout",
        last_checked_at=checked_at,
        last_success_at=None,
        last_failure_at=checked_at,
        next_check_after=checked_at + timedelta(days=7),
        failure_count=1,
        created_at=checked_at,
        updated_at=checked_at,
    )

    assert _effective_next_check_after(record=record) == checked_at + timedelta(minutes=1)


def test_fetch_link_title_does_not_fall_through_dns_preflight_errors(monkeypatch) -> None:
    def fake_resolve_public_http_target(url: str) -> _ResolvedHttpTarget:
        raise _LinkTitleTargetRejected("dns_error")

    def fail_fetch_one_url(url: str, target: _ResolvedHttpTarget) -> _LinkTitleFetchResult:
        raise AssertionError("HTTP fetch must not run after DNS validation fails")

    monkeypatch.setattr(
        "app.services.link_titles._resolve_public_http_target",
        fake_resolve_public_http_target,
    )
    monkeypatch.setattr("app.services.link_titles._fetch_one_url", fail_fetch_one_url)

    result = fetch_link_title("https://www.youtube.com/watch?v=abc123")

    assert result == _LinkTitleFetchResult(
        url="https://www.youtube.com/watch?v=abc123",
        title=None,
        status="failed",
        last_error_kind="dns_error",
    )


def test_fetch_link_title_resolves_and_pins_every_redirect(monkeypatch) -> None:
    first_url = "https://example.com/start"
    redirected_url = "https://example.net/final"
    first_target = _ResolvedHttpTarget(
        hostname="example.com",
        port=443,
        public_addresses=("93.184.216.34",),
    )
    redirected_target = _ResolvedHttpTarget(
        hostname="example.net",
        port=443,
        public_addresses=("93.184.216.35",),
    )
    resolved_urls: list[str] = []
    fetch_calls: list[tuple[str, _ResolvedHttpTarget]] = []

    def fake_resolve(url: str) -> _ResolvedHttpTarget:
        resolved_urls.append(url)
        if url == first_url:
            return first_target
        if url == redirected_url:
            return redirected_target
        raise AssertionError(f"Unexpected URL resolution: {url}")

    def fake_fetch(url: str, target: _ResolvedHttpTarget) -> _LinkTitleFetchResult:
        fetch_calls.append((url, target))
        if url == first_url:
            return _LinkTitleFetchResult(
                url=url,
                title=redirected_url,
                status="redirect",
                last_error_kind=None,
            )
        return _LinkTitleFetchResult(
            url=url,
            title="Final title",
            status="ok",
            last_error_kind=None,
        )

    monkeypatch.setattr("app.services.link_titles._resolve_public_http_target", fake_resolve)
    monkeypatch.setattr("app.services.link_titles._fetch_one_url", fake_fetch)

    result = fetch_link_title(first_url)

    assert resolved_urls == [first_url, redirected_url]
    assert fetch_calls == [
        (first_url, first_target),
        (redirected_url, redirected_target),
    ]
    assert result == _LinkTitleFetchResult(
        url=first_url,
        title="Final title",
        status="ok",
        last_error_kind=None,
    )


def test_pinned_network_backend_connects_to_validated_ip_not_hostname() -> None:
    calls: list[tuple[str, int]] = []
    expected_stream = object()

    class FakeNetworkBackend:
        def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: float | None,
            local_address: str | None,
            socket_options,
        ):
            calls.append((host, port))
            return expected_stream

        def connect_unix_socket(self, path, timeout, socket_options):
            raise AssertionError("Unix sockets are not used for link title requests")

        def sleep(self, seconds: float) -> None:
            raise AssertionError("Retries are disabled for link title requests")

    target = _ResolvedHttpTarget(
        hostname="attacker.example",
        port=443,
        public_addresses=("93.184.216.34",),
    )
    backend = _PinnedNetworkBackend(
        target=target,
        network_backend=FakeNetworkBackend(),
    )

    stream = backend.connect_tcp(
        host="attacker.example",
        port=443,
        timeout=None,
        local_address=None,
        socket_options=None,
    )

    assert stream is expected_stream
    assert calls == [("93.184.216.34", 443)]


def test_pinned_network_backend_rejects_unexpected_connection_target() -> None:
    class UnusedNetworkBackend:
        def connect_tcp(self, **kwargs):
            raise AssertionError("Unexpected target must be rejected before connecting")

    target = _ResolvedHttpTarget(
        hostname="example.com",
        port=443,
        public_addresses=("93.184.216.34",),
    )
    backend = _PinnedNetworkBackend(
        target=target,
        network_backend=UnusedNetworkBackend(),
    )

    with pytest.raises(
        RuntimeError,
        match="Pinned link-title transport received an unexpected host or port",
    ):
        backend.connect_tcp(
            host="127.0.0.1",
            port=443,
            timeout=None,
            local_address=None,
            socket_options=None,
        )


def test_pinned_http_transport_preserves_original_http_hostname() -> None:
    target = _ResolvedHttpTarget(
        hostname="example.com",
        port=80,
        public_addresses=("93.184.216.34",),
    )
    network_backend = httpcore.MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: text/html; charset=utf-8\r\n",
            b"Content-Length: 47\r\n",
            b"\r\n",
            b"<html><head><title>Pinned</title></head></html>",
        ]
    )
    transport = _PinnedHTTPTransport(
        target=target,
        network_backend=network_backend,
    )

    with httpx.Client(transport=transport) as client:
        response = client.get("http://example.com/article")

    assert response.status_code == 200
    assert response.text == "<html><head><title>Pinned</title></head></html>"


def test_resolve_public_http_target_returns_only_validated_addresses(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type, proto: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2606:2800:220:1:248:1893:25c8:1946", port, 0, 0)),
        ],
    )

    target = _resolve_public_http_target("https://example.com/article")

    assert target == _ResolvedHttpTarget(
        hostname="example.com",
        port=443,
        public_addresses=("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"),
    )


@pytest.mark.parametrize("private_address", ["127.0.0.1", "10.0.0.31", "169.254.169.254", "::1"])
def test_resolve_public_http_target_rejects_any_private_dns_answer(
    private_address: str,
    monkeypatch,
) -> None:
    address_family = socket.AF_INET
    socket_address = (private_address, 443)
    if ":" in private_address:
        address_family = socket.AF_INET6
        socket_address = (private_address, 443, 0, 0)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *, type, proto: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port)),
            (address_family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address),
        ],
    )

    with pytest.raises(_LinkTitleTargetRejected) as exc_info:
        _resolve_public_http_target("https://example.com/article")

    assert exc_info.value.reason == "blocked_private_address"
