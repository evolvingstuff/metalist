from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.db.session import connect_reader
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key, set_encryption_required, set_session_dek
from app.services.search_history import (
    MAX_SEARCH_HISTORY_ROWS,
    is_first_search_tag_suggestion_context,
    list_recent_search_tags,
    normalize_search_history_query,
    prioritize_blank_search_suggestions,
    prioritize_first_search_tag_suggestions,
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


def _reset_search_history_state() -> None:
    search_history_module.search_history_store.clear_persisted_state_for_tests()


def _fetch_search_history_rows(statement: str):
    with connect_reader("tests:search_history") as connection:
        return connection.execute(statement).fetchall()


def test_normalize_search_history_query_sorts_dedupes_and_skips_negative_and_text_terms() -> None:
    normalized = normalize_search_history_query('journal +exercise -"weekly" \'review\' todo')
    assert normalized is not None
    assert normalized.query_key == "exercise journal todo"
    assert normalized.root_tag == "exercise"
    assert normalized.tags == ("exercise", "journal", "todo")

    duplicate = normalize_search_history_query("journal exercise journal")
    assert duplicate is not None
    assert duplicate.query_key == "exercise journal"
    assert duplicate.tags == ("exercise", "journal")

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
        _reset_search_history_state()
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

        assert record_search_interaction(query="journal", interaction_type="search", token="token") is True
        assert record_search_interaction(query="exercise", interaction_type="command", token="token") is True

        recent_tags = list_recent_search_tags(limit=3, token="token")
        assert recent_tags == ["exercise", "journal"]

        rows = _fetch_search_history_rows(
            "SELECT query_key, score FROM search_interaction_history ORDER BY query_key ASC"
        )
        assert len(rows) == 2
        by_query = {str(row["query_key"]): float(row["score"]) for row in rows}
        assert by_query["journal"] == pytest.approx(0.98)
        assert by_query["exercise"] == pytest.approx(1.0)
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_list_recent_search_tags_aggregates_recent_frequency_across_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        _reset_search_history_state()
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Alpha beta",
                    tags="alpha beta",
                    tag_terms=extract_tags_for_search("alpha beta"),
                ),
                SearchRecord(
                    note_id="n2",
                    content_text="Alpha gamma",
                    tags="alpha gamma",
                    tag_terms=extract_tags_for_search("alpha gamma"),
                ),
                SearchRecord(
                    note_id="n3",
                    content_text="Delta epsilon zeta",
                    tags="delta epsilon zeta",
                    tag_terms=extract_tags_for_search("delta epsilon zeta"),
                ),
            ]
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_search_interaction(query="alpha beta", interaction_type="edit", token="token") is True
        assert record_search_interaction(query="alpha gamma", interaction_type="edit", token="token") is True
        assert record_search_interaction(query="delta epsilon zeta", interaction_type="edit", token="token") is True

        recent_tags = list_recent_search_tags(limit=3, token="token")
        assert recent_tags == ["alpha", "delta", "epsilon"]
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_repeated_direct_search_promotes_tag_for_blank_and_first_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        _reset_search_history_state()
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Scratchpad",
                    tags="scratchpad",
                    tag_terms=extract_tags_for_search("scratchpad"),
                ),
                SearchRecord(
                    note_id="n2",
                    content_text="Shopping",
                    tags="shopping",
                    tag_terms=extract_tags_for_search("shopping"),
                ),
                SearchRecord(
                    note_id="n3",
                    content_text="Sleep",
                    tags="sleep",
                    tag_terms=extract_tags_for_search("sleep"),
                ),
            ]
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_search_interaction(query="shopping", interaction_type="search", token="token") is True
        assert record_search_interaction(query="sleep", interaction_type="search", token="token") is True
        for _ in range(5):
            assert record_search_interaction(query="scratchpad", interaction_type="search", token="token") is True

        recent_tags = list_recent_search_tags(limit=50, token="token")
        assert recent_tags[0] == "scratchpad"
        assert prioritize_blank_search_suggestions(
            base_suggestions=["shopping", "sleep", "scratchpad"],
            recent_tags=recent_tags,
            priority_slots=3,
        )[0] == "scratchpad"
        assert prioritize_first_search_tag_suggestions(
            query="s",
            base_suggestions=["shopping", "sleep", "scratchpad"],
            recent_tags=recent_tags,
            priority_slots=3,
        )[0] == "scratchpad"
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


def test_prioritize_blank_search_suggestions_collapses_case_equivalent_terms() -> None:
    merged = prioritize_blank_search_suggestions(
        base_suggestions=["databricks", "alpha"],
        recent_tags=["Databricks", "todo"],
        priority_slots=3,
    )
    assert merged == ["Databricks", "todo", "alpha"]


def test_first_search_tag_context_only_matches_blank_or_single_tag_prefix() -> None:
    assert is_first_search_tag_suggestion_context("")
    assert is_first_search_tag_suggestion_context("jo")
    assert is_first_search_tag_suggestion_context("+jo")
    assert is_first_search_tag_suggestion_context("-jo")
    assert not is_first_search_tag_suggestion_context("+")
    assert not is_first_search_tag_suggestion_context("journal ")
    assert not is_first_search_tag_suggestion_context("journal exercise")
    assert not is_first_search_tag_suggestion_context('"journal"')


def test_prioritize_first_search_tag_suggestions_filters_recent_tags_by_prefix() -> None:
    merged = prioritize_first_search_tag_suggestions(
        query="ju",
        base_suggestions=["jupyter", "junior", "juice"],
        recent_tags=["todo", "junior", "jupyter", "journal"],
        priority_slots=3,
    )
    assert merged == ["junior", "jupyter", "juice"]


def test_prioritize_first_search_tag_suggestions_uses_connector_segment_prefix() -> None:
    merged = prioritize_first_search_tag_suggestions(
        query="wor",
        base_suggestions=["workspaces", "workflow", "databricks-workspaces"],
        recent_tags=["databricks-workspaces", "later"],
        priority_slots=3,
    )
    assert merged == ["databricks-workspaces", "workspaces", "workflow"]


def test_prioritize_first_search_tag_suggestions_keeps_multi_term_ranking() -> None:
    merged = prioritize_first_search_tag_suggestions(
        query="journal ex",
        base_suggestions=["exercise", "exams"],
        recent_tags=["exams"],
        priority_slots=3,
    )
    assert merged == ["exercise", "exams"]


def test_prioritize_first_search_tag_suggestions_excludes_exact_current_prefix() -> None:
    merged = prioritize_first_search_tag_suggestions(
        query="journal",
        base_suggestions=["journalism", "job"],
        recent_tags=["journal", "journalism"],
        priority_slots=3,
    )
    assert merged == ["journalism", "job"]


def test_list_recent_search_tags_canonicalizes_case_equivalent_terms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        _reset_search_history_state()
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="One",
                    tags="databricks",
                    tag_terms=extract_tags_for_search("databricks"),
                ),
                SearchRecord(
                    note_id="n2",
                    content_text="Two",
                    tags="databricks",
                    tag_terms=extract_tags_for_search("databricks"),
                ),
                SearchRecord(
                    note_id="n3",
                    content_text="Three",
                    tags="Databricks",
                    tag_terms=extract_tags_for_search("Databricks"),
                ),
            ]
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_search_interaction(query="Databricks", interaction_type="edit", token="token") is True
        assert record_search_interaction(query="databricks", interaction_type="edit", token="token") is True

        recent_tags = list_recent_search_tags(limit=3, token="token")
        assert recent_tags == ["databricks"]
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_search_history_collapses_same_terms_in_different_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        _reset_search_history_state()
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
        assert record_search_interaction(query="exercise journal", interaction_type="edit", token="token") is True

        rows = _fetch_search_history_rows(
            "SELECT query_key, score FROM search_interaction_history ORDER BY query_key ASC"
        )
        assert len(rows) == 1
        assert rows[0]["query_key"] == "exercise journal"
        assert float(rows[0]["score"]) == pytest.approx(1.98)
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_search_history_enforces_explicit_row_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    try:
        _reset_search_history_state()
        monkeypatch.setattr(search_history_module, "SEARCH_HISTORY_DECAY_FACTOR", 1.0)
        monkeypatch.setattr(search_history_module, "_SEARCH_HISTORY_PRUNE_SCORE_THRESHOLD", -1.0)
        records = [
            SearchRecord(
                note_id=f"n{i}",
                content_text=f"Tag {i}",
                tags=f"tag-{i:03d}",
                tag_terms=extract_tags_for_search(f"tag-{i:03d}"),
            )
            for i in range(MAX_SEARCH_HISTORY_ROWS + 5)
        ]
        monkeypatch.setattr(search_history_module, "search_index", _build_index(records))

        for i in range(MAX_SEARCH_HISTORY_ROWS + 5):
            query = f"tag-{i:03d}"
            assert record_search_interaction(query=query, interaction_type="search", token="token") is True

        rows = _fetch_search_history_rows(
            "SELECT query_key FROM search_interaction_history ORDER BY query_key ASC"
        )
        query_keys = [str(row["query_key"]) for row in rows]
        assert len(query_keys) == MAX_SEARCH_HISTORY_ROWS
        assert "tag-000" not in query_keys
        assert "tag-004" not in query_keys
        assert "tag-005" in query_keys
        assert f"tag-{MAX_SEARCH_HISTORY_ROWS + 4:03d}" in query_keys
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_search_history_encrypts_at_rest_and_round_trips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(True)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    set_session_dek(os.urandom(32))
    try:
        _reset_search_history_state()
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

        rows = _fetch_search_history_rows(
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
        )
        assert rows
        row = rows[0]
        assert row is not None
        assert row["query_key"] != "exercise journal"
        assert isinstance(row["query_key_encryption_nonce"], bytes)
        assert row["root_tag"] != "exercise"
        assert isinstance(row["root_tag_encryption_nonce"], bytes)
        assert row["tags_json"] != '["exercise","journal"]'
        assert isinstance(row["tags_json_encryption_nonce"], bytes)

        assert list_recent_search_tags(limit=3, token="token") == ["exercise", "journal"]
    finally:
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()
