from datetime import datetime, timedelta, timezone

from app.services.link_titles import LinkTitleRecord
from app.services.link_titles import _LinkTitleFetchResult
from app.services.link_titles import _MAX_RESPONSE_BYTES
from app.services.link_titles import _effective_next_check_after
from app.services.link_titles import _extract_title_from_html
from app.services.link_titles import _next_check_after_for_status
from app.services.link_titles import fetch_link_title


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
