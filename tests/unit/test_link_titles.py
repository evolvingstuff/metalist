from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3

from app.db.link_titles_sql import fetch_all_link_title_rows
from app.db.link_titles_sql import insert_link_title_row
from app.db.schema import initialize_schema
from app.services.link_titles import LinkTitleRecord
from app.services.link_titles import _LinkTitleFetchResult
from app.services.link_titles import _MAX_RESPONSE_BYTES
from app.services.link_titles import _effective_next_check_after
from app.services.link_titles import _extract_title_from_html
from app.services.link_titles import _fetch_result_from_extracted_title
from app.services.link_titles import _looks_like_interstitial_title
from app.services.link_titles import _next_check_after_for_status
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


def test_fetch_link_title_falls_through_dns_preflight_errors(monkeypatch) -> None:
    calls: list[str] = []

    def fake_validate_public_http_url(url: str) -> str:
        calls.append(url)
        return "dns_error"

    def fake_fetch_one_url(url: str) -> _LinkTitleFetchResult:
        return _LinkTitleFetchResult(
            url=url,
            title="Fetched Title",
            status="ok",
            last_error_kind=None,
        )

    monkeypatch.setattr(
        "app.services.link_titles._validate_public_http_url",
        fake_validate_public_http_url,
    )
    monkeypatch.setattr("app.services.link_titles._fetch_one_url", fake_fetch_one_url)

    result = fetch_link_title("https://www.youtube.com/watch?v=abc123")

    assert calls == ["https://www.youtube.com/watch?v=abc123"]
    assert result == _LinkTitleFetchResult(
        url="https://www.youtube.com/watch?v=abc123",
        title="Fetched Title",
        status="ok",
        last_error_kind=None,
    )
