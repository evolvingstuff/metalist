"""A text search also matches the cached titles of URLs written in a note
(docs/ui/search-semantics.md, "URL titles")."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.db.link_titles_sql import insert_link_title_row
from app.db.schema import initialize_schema
from app.services.link_titles import _LinkTitleFetchResult, link_title_store
from app.services.note_store import _search_text
from app.services.search_index import SearchIndex
from app.services.search_text import build_searchable_text_casefold
from app.utils.text_utils import strip_html

ARTICLE = "https://example.com/article"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _store_title(connection: sqlite3.Connection, url: str, title: str) -> None:
    insert_link_title_row(
        connection, url=url, url_encryption_nonce=None, url_encryption_tag=None,
        title=title, title_encryption_nonce=None, title_encryption_tag=None,
        status="ok", last_error_kind=None, last_checked_at=NOW, last_success_at=NOW,
        last_failure_at=None, next_check_after=NOW + timedelta(days=90), failure_count=0,
        created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_schema(connection)

    @contextmanager
    def fake_begin_writer():
        yield connection

    monkeypatch.setattr("app.services.link_titles.begin_writer", fake_begin_writer)
    yield connection
    link_title_store.reset()
    connection.close()


@pytest.fixture
def index(monkeypatch: pytest.MonkeyPatch) -> SearchIndex:
    """A fresh index that, like the app's, follows title changes."""
    index = SearchIndex()
    monkeypatch.setattr(link_title_store, "_titles_changed_listeners", [index.refresh_link_titles])
    return index


def _write(index: SearchIndex, note_id: str, text: str) -> None:
    index.upsert(note_id=note_id, content_text=text, tags="", raw_tag_terms=frozenset(), tag_terms=frozenset())


def _fetched(url: str, title: str) -> _LinkTitleFetchResult:
    return _LinkTitleFetchResult(url=url, title=title, status="ok", last_error_kind=None)


def test_a_search_matches_the_title_of_a_url_in_the_note(connection, index) -> None:
    _store_title(connection, ARTICLE, "Mamba: Linear-Time Sequence Modeling")
    link_title_store.bootstrap(connection=connection)
    _write(index, "standalone", ARTICLE)
    _write(index, "in-prose", f"see {ARTICLE}. for details")
    _write(index, "other", "nothing linked here")

    assert index.query_note_ids('"sequence modeling"') == {"standalone", "in-prose"}
    # The URL itself stays searchable.
    assert index.query_note_ids('"example.com"') == {"standalone", "in-prose"}


def test_a_title_fetched_later_makes_the_note_match(connection, index) -> None:
    link_title_store.bootstrap(connection=connection)
    _write(index, "note", ARTICLE)
    assert index.query_note_ids('"mamba"') == set()

    link_title_store.apply_fetch_result(_fetched(ARTICLE, "Mamba paper"))

    assert index.query_note_ids('"mamba"') == {"note"}


def test_titles_loaded_after_the_index_was_built_are_searchable(connection, index) -> None:
    # Hydration can build the index before the stored titles are loaded or decrypted.
    _write(index, "note", ARTICLE)
    _store_title(connection, ARTICLE, "Mamba paper")
    assert index.query_note_ids('"mamba"') == set()

    link_title_store.bootstrap(connection=connection)

    assert index.query_note_ids('"mamba"') == {"note"}


def test_titles_stop_matching_once_cleared_on_lock(connection, index) -> None:
    _store_title(connection, ARTICLE, "Mamba paper")
    link_title_store.bootstrap(connection=connection)
    _write(index, "note", ARTICLE)
    assert index.query_note_ids('"mamba"') == {"note"}

    link_title_store.reset()

    assert index.query_note_ids('"mamba"') == set()
    assert index.query_note_ids('"example.com"') == {"note"}


def test_a_note_edited_or_deleted_away_from_the_url_no_longer_matches_its_title(connection, index) -> None:
    _store_title(connection, ARTICLE, "Mamba paper")
    link_title_store.bootstrap(connection=connection)
    _write(index, "edited", ARTICLE)
    _write(index, "deleted", ARTICLE)

    _write(index, "edited", "the link is gone")
    index.remove_many({"deleted"})
    assert index.query_note_ids('"mamba"') == set()

    # A later title change for that URL leaves both notes alone.
    link_title_store.apply_fetch_result(_fetched(ARTICLE, "Mamba, revised"))
    assert index.query_note_ids('"mamba"') == set()

    # Restoring the deleted note (undo) brings its URL and title back.
    _write(index, "deleted", ARTICLE)
    assert index.query_note_ids('"revised"') == {"deleted"}


def test_search_context_checks_see_the_same_titles(connection) -> None:
    # New notes in a search context are checked against the search with this text.
    _store_title(connection, ARTICLE, "Mamba paper")
    link_title_store.bootstrap(connection=connection)
    assert "mamba paper" in build_searchable_text_casefold(f"<div>{ARTICLE}</div>", "")


def test_a_link_label_hides_its_url_but_search_still_matches_the_url_and_its_title(connection, index) -> None:
    _store_title(connection, ARTICLE, "Mamba paper")
    link_title_store.bootstrap(connection=connection)
    html = f'<div>Watch <a href="{ARTICLE}">the video</a> later</div>'
    _write(index, "labelled", _search_text(html, strip_html(html)))

    assert index.query_note_ids('"example.com/article"') == {"labelled"}
    assert index.query_note_ids('"mamba"') == {"labelled"}
    assert index.query_note_ids('"the video"') == {"labelled"}
    assert "example.com/article" in build_searchable_text_casefold(html, "")
