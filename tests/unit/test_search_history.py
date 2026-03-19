from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.db.search_history_session import (
    begin_search_history_writer,
    connect_search_history_reader,
    resolve_search_history_database_path,
)
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key, set_encryption_required, set_session_dek
from app.services.search_history import (
    list_recent_search_tags,
    normalize_search_history_query,
    prioritize_blank_search_suggestions,
    record_search_interaction,
)
from app.services.search_index import SearchIndex, SearchRecord, extract_tags_for_search
import app.services.search_history as search_history_module


def _build_index(records: list[SearchRecord]) -> SearchIndex:
    index = SearchIndex()
    index.rebuild(
        records,
        progress_update=lambda _processed: None,
        progress_interval=1000,
    )
    return index


def test_resolve_search_history_database_path_uses_sibling_search_history_name() -> None:
    path = resolve_search_history_database_path(Path("/tmp/namespaces/default/default.metalist.db"))
    assert path == Path("/tmp/namespaces/default/default.metalist.search-history.db")


def test_normalize_search_history_query_preserves_order_and_skips_negative_and_text_terms() -> None:
    normalized = normalize_search_history_query('journal +exercise -"weekly" \'review\' todo')
    assert normalized is not None
    assert normalized.query_key == "journal exercise todo"
    assert normalized.root_tag == "journal"
    assert normalized.tags == ("journal", "exercise", "todo")

    assert normalize_search_history_query('"quoted only" -"ignored"') is None
    assert normalize_search_history_query("4f9e98ee-0cae-4e63-a7b1-bd322ec0cb87") is None
    mixed = normalize_search_history_query("[[4f9e98ee-0cae-4e63-a7b1-bd322ec0cb87]] journal")
    assert mixed is not None
    assert mixed.query_key == "journal"


def test_record_search_interaction_uses_event_decay_and_returns_recent_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        with begin_search_history_writer() as connection:
            connection.execute("DELETE FROM search_interaction_history")
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Journal entry",
                    tags="journal",
                    tag_terms=extract_tags_for_search("journal"),
                ),
                SearchRecord(
                    note_id="n2",
                    content_text="Exercise log",
                    tags="exercise",
                    tag_terms=extract_tags_for_search("exercise"),
                ),
            ]
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_search_interaction(query="journal", interaction_type="edit", token="token") is True
        assert record_search_interaction(query="exercise", interaction_type="command", token="token") is True

        recent_tags = list_recent_search_tags(limit=3, token="token")
        assert recent_tags == ["exercise", "journal"]

        with connect_search_history_reader() as connection:
            rows = connection.execute(
                "SELECT query_key, score FROM search_interaction_history ORDER BY query_key ASC"
            ).fetchall()
        assert len(rows) == 2
        by_query = {str(row["query_key"]): float(row["score"]) for row in rows}
        assert by_query["journal"] == pytest.approx(0.98)
        assert by_query["exercise"] == pytest.approx(1.0)
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_record_search_interaction_flattens_ranked_multi_term_histories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        with begin_search_history_writer() as connection:
            connection.execute("DELETE FROM search_interaction_history")
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Journal todo",
                    tags="journal todo",
                    tag_terms=extract_tags_for_search("journal todo"),
                ),
                SearchRecord(
                    note_id="n2",
                    content_text="Journal exercise",
                    tags="journal exercise",
                    tag_terms=extract_tags_for_search("journal exercise"),
                ),
            ]
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_search_interaction(query="journal exercise", interaction_type="edit", token="token") is True
        assert record_search_interaction(query="journal todo", interaction_type="edit", token="token") is True

        recent_tags = list_recent_search_tags(limit=3, token="token")
        assert recent_tags == ["journal", "todo", "exercise"]
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_prioritize_blank_search_suggestions_reserves_top_slots() -> None:
    merged = prioritize_blank_search_suggestions(
        base_suggestions=["alpha", "beta", "gamma"],
        recent_tags=["journal", "beta", "todo", "later"],
        priority_slots=3,
    )
    assert merged == ["journal", "beta", "todo", "alpha", "gamma"]


def test_search_history_encrypts_at_rest_and_round_trips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(True)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    set_session_dek(os.urandom(32))
    try:
        with begin_search_history_writer() as connection:
            connection.execute("DELETE FROM search_interaction_history")
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Journal exercise",
                    tags="journal exercise",
                    tag_terms=extract_tags_for_search("journal exercise"),
                ),
            ]
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_search_interaction(query="journal exercise", interaction_type="edit", token="token") is True

        with connect_search_history_reader() as connection:
            row = connection.execute(
                """
                SELECT
                    query_key,
                    query_key_encryption_nonce,
                    root_tag,
                    root_tag_encryption_nonce,
                    tags_json,
                    tags_json_encryption_nonce
                FROM search_interaction_history
                LIMIT 1
                """
            ).fetchone()
        assert row is not None
        assert row["query_key"] != "journal exercise"
        assert isinstance(row["query_key_encryption_nonce"], bytes)
        assert row["root_tag"] != "journal"
        assert isinstance(row["root_tag_encryption_nonce"], bytes)
        assert row["tags_json"] != '["journal","exercise"]'
        assert isinstance(row["tags_json_encryption_nonce"], bytes)

        assert list_recent_search_tags(limit=3, token="token") == ["journal", "exercise"]
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()
