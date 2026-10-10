"""Retry failed link titles (app/services/link_title_retry.py)."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

import app.services.link_title_retry as retry
import app.services.link_titles as link_titles
from app.db.link_titles_sql import insert_link_title_row
from app.db.schema import initialize_schema
from app.services.link_titles import _HostPacer, _LinkTitleFetchResult, link_title_store

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
STORED = {
    "https://youtube.com/watch?v=a": ("failed", "http_429", None),
    "https://youtube.com/watch?v=b": ("failed", "http_429", None),
    "https://example.com/gone": ("failed", "http_404", None),
    "https://example.com/spa": ("no_title", "no_title", None),
    "https://example.com/paper.pdf": ("unsupported", "non_html", None),
    "https://intranet.local/": ("blocked", "blocked_private_address", None),
    "https://example.com/fine": ("ok", None, "Fine page"),
}


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_schema(connection)
    for url, (status, kind, title) in STORED.items():
        insert_link_title_row(
            connection, url=url, url_encryption_nonce=None, url_encryption_tag=None, title=title,
            title_encryption_nonce=None, title_encryption_tag=None, status=status, last_error_kind=kind,
            last_checked_at=NOW, last_success_at=None, last_failure_at=NOW,
            next_check_after=NOW + timedelta(days=7), failure_count=1, created_at=NOW, updated_at=NOW,
        )

    @contextmanager
    def fake_begin_writer():
        yield connection

    monkeypatch.setattr(link_titles, "begin_writer", fake_begin_writer)
    monkeypatch.setattr(link_titles, "_host_pacer", _HostPacer())
    monkeypatch.setattr(retry, "_current_run", [])
    # Run lookup jobs at once, in order, instead of on the worker threads.
    monkeypatch.setattr(link_titles.link_title_fetcher, "submit_job", lambda job, *args: job(*args))
    link_title_store.bootstrap(connection=connection)
    yield connection
    link_title_store.reset()
    connection.close()


def _answer(monkeypatch: pytest.MonkeyPatch, answers: dict[str, _LinkTitleFetchResult]) -> list[str]:
    asked: list[str] = []

    def fake_fetch(url: str) -> _LinkTitleFetchResult:
        asked.append(url)
        return answers[url]

    monkeypatch.setattr(retry, "fetch_link_title", fake_fetch)
    return asked


def _ok(url: str, title: str) -> _LinkTitleFetchResult:
    return _LinkTitleFetchResult(url=url, title=title, status="ok", last_error_kind=None)


def _failed(url: str, kind: str) -> _LinkTitleFetchResult:
    return _LinkTitleFetchResult(url=url, title=None, status="failed", last_error_kind=kind)


def test_before_a_run_the_dialog_shows_how_many_links_it_would_ask(stored) -> None:
    snapshot = retry.link_title_retry_snapshot()
    assert snapshot["status"] == "idle"
    # Failed and title-less lookups; not unsupported, blocked or titled ones.
    assert snapshot["retryable"] == 4


def test_a_run_asks_every_failure_now_and_counts_the_outcomes(stored, monkeypatch) -> None:
    asked = _answer(monkeypatch, {
        "https://youtube.com/watch?v=a": _ok("https://youtube.com/watch?v=a", "Video A"),
        "https://youtube.com/watch?v=b": _ok("https://youtube.com/watch?v=b", "Video B"),
        "https://example.com/gone": _failed("https://example.com/gone", "http_404"),
        "https://example.com/spa": _ok("https://example.com/spa", "The app"),
    })

    snapshot = retry.start_link_title_retry()

    assert sorted(asked) == sorted(url for url, (status, _kind, _title) in STORED.items()
                                   if status in {"failed", "no_title"})
    assert snapshot == {"status": "finished", "total": 4, "asked": 4, "found": 3,
                        "stillFailing": {"http_404": 1}, "pausedSites": {}, "skipped": 0,
                        "dropped": 0, "retryable": 1}
    assert link_title_store.get_ok_title("https://youtube.com/watch?v=a") == "Video A"


def test_a_site_that_asks_to_wait_is_skipped_for_the_rest_of_the_run(stored, monkeypatch) -> None:
    asked = _answer(monkeypatch, {
        "https://youtube.com/watch?v=a": _failed("https://youtube.com/watch?v=a", "http_429"),
        "https://example.com/gone": _failed("https://example.com/gone", "http_404"),
        "https://example.com/spa": _ok("https://example.com/spa", "The app"),
    })
    real_fetch = retry.fetch_link_title

    def fetch_then_pause(url: str) -> _LinkTitleFetchResult:
        if url == "https://youtube.com/watch?v=b":
            return _LinkTitleFetchResult(url=url, title=None, status="deferred", last_error_kind="rate_limited")
        return real_fetch(url)

    monkeypatch.setattr(retry, "fetch_link_title", fetch_then_pause)

    snapshot = retry.start_link_title_retry()

    assert "https://youtube.com/watch?v=b" not in asked
    assert snapshot["status"] == "finished"
    assert snapshot["pausedSites"] == {"youtube.com": 1}
    assert snapshot["stillFailing"] == {"http_404": 1, "http_429": 1}
    # The paused link is free for later lookups, with its record unchanged.
    assert "https://youtube.com/watch?v=b" in link_title_store.list_manual_retry_urls()


def test_stopping_drops_the_lookups_not_yet_started(stored, monkeypatch) -> None:
    queued: list[tuple] = []
    monkeypatch.setattr(link_titles.link_title_fetcher, "submit_job", lambda job, *args: queued.append((job, args)))
    asked = _answer(monkeypatch, {
        "https://example.com/gone": _failed("https://example.com/gone", "http_404"),
    })

    assert retry.start_link_title_retry()["status"] == "running"
    first_job, first_args = queued[0]
    first_job(*first_args)
    assert retry.stop_link_title_retry()["status"] == "stopping"
    for job, args in queued[1:]:
        job(*args)

    snapshot = retry.link_title_retry_snapshot()
    assert asked == ["https://example.com/gone"]
    assert snapshot["status"] == "stopped"
    assert snapshot["asked"] == 1
    assert snapshot["dropped"] == 3


def test_logging_in_or_locking_drops_the_rest(stored, monkeypatch) -> None:
    queued: list[tuple] = []
    monkeypatch.setattr(link_titles.link_title_fetcher, "submit_job", lambda job, *args: queued.append((job, args)))
    asked = _answer(monkeypatch, {})
    retry.start_link_title_retry()

    monkeypatch.setattr(retry, "current_generation", lambda: -1)
    for job, args in queued:
        job(*args)

    assert asked == []
    assert retry.link_title_retry_snapshot()["status"] == "stopped"


def test_starting_while_a_run_is_going_shows_that_run(stored, monkeypatch) -> None:
    queued: list[tuple] = []
    monkeypatch.setattr(link_titles.link_title_fetcher, "submit_job", lambda job, *args: queued.append((job, args)))
    retry.start_link_title_retry()
    retry.start_link_title_retry()
    assert len(queued) == 4


def test_with_nothing_to_retry_no_run_starts(stored, monkeypatch) -> None:
    monkeypatch.setattr(link_title_store, "list_manual_retry_urls", lambda: ())
    assert retry.start_link_title_retry()["status"] == "idle"
