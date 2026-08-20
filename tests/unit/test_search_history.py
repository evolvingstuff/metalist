from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from app.db.session import connect_reader
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key, set_encryption_required, set_session_dek
from app.services.search_history import (
    DEFAULT_TAG_ACTIVITY_WINDOWS,
    is_first_search_tag_suggestion_context,
    list_recent_search_tags_for_first_query,
    prioritize_first_search_tag_suggestions,
    record_note_interaction,
    reset_search_history,
)
from app.services.search_index import SearchIndex, SearchRecord, extract_tags_for_search
import app.services.search_history as search_history_module


def _build_index(
    records: list[SearchRecord], *, raw_tag_terms_by_id: dict[str, frozenset[str]]
) -> SearchIndex:
    index = SearchIndex()
    index.rebuild(
        records,
        raw_tag_terms_by_id=raw_tag_terms_by_id,
        progress_update=lambda _processed: None,
        progress_interval=1000,
    )
    return index


def _fetch_rows():
    with connect_reader("tests:tag_activity") as connection:
        return connection.execute(
            "SELECT * FROM search_interaction_history ORDER BY storage_id ASC"
        ).fetchall()


def _configure_memory_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    search_history_module.search_history_store.clear_persisted_state_for_tests()


def test_note_interaction_credits_raw_inherited_tags_not_ontology_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_database(tmp_path, monkeypatch)
    try:
        index = _build_index(
            [
                SearchRecord(
                    note_id="shell-note",
                    content_text="Backup command",
                    tags="@shell",
                    tag_terms=frozenset({"shortcut", "@shell", "inferred"}),
                )
            ],
            raw_tag_terms_by_id={"shell-note": frozenset({"shortcut", "@shell"})},
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_note_interaction(
            note_id="shell-note",
            interaction_type="command",
            token="token",
            interacted_on=date(2026, 8, 20),
        ) is True
        assert list_recent_search_tags_for_first_query(
            query="shor",
            candidate_tags=["short-story", "shortcut", "inferred"],
            window_days=DEFAULT_TAG_ACTIVITY_WINDOWS,
            token="token",
            today=date(2026, 8, 20),
        ) == ["shortcut"]
    finally:
        search_history_module.search_history_store.clear_persisted_state_for_tests()


def test_daily_activity_reuses_one_bucket_and_one_database_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_database(tmp_path, monkeypatch)
    try:
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Journal",
                    tags="journal workday",
                    tag_terms=frozenset({"journal", "workday"}),
                )
            ],
            raw_tag_terms_by_id={"n1": frozenset({"journal", "workday"})},
        )
        monkeypatch.setattr(search_history_module, "search_index", index)
        interaction_day = date(2026, 8, 20)

        for interaction_type in ("edit", "expand", "fullscreen"):
            assert record_note_interaction(
                note_id="n1",
                interaction_type=interaction_type,
                token="token",
                interacted_on=interaction_day,
            ) is True

        rows = _fetch_rows()
        assert len(rows) == 1
        assert rows[0]["payload_encryption_nonce"] is None
        payload = json.loads(rows[0]["payload_json"])
        assert payload == {
            "version": 2,
            "counts_by_date": {
                "2026-08-20": {"journal": 3, "workday": 3},
            },
        }
    finally:
        search_history_module.search_history_store.clear_persisted_state_for_tests()


def test_sparse_retention_keeps_365_populated_days_regardless_of_gaps() -> None:
    newest_day = date(2026, 8, 20)
    counts_by_date = {
        (newest_day - timedelta(days=index * 20)).isoformat(): {"journal": 1}
        for index in range(366)
    }

    retained = search_history_module._prune_counts_by_date(
        counts_by_date=counts_by_date,
        today=newest_day,
    )

    assert len(retained) == 365
    assert newest_day.isoformat() in retained
    assert (newest_day - timedelta(days=365 * 20)).isoformat() not in retained


def test_tag_activity_is_opaque_at_rest_and_reencrypts_same_single_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_database(tmp_path, monkeypatch)
    set_session_dek(b"k" * 32)
    set_encryption_required(True)
    try:
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Shortcut",
                    tags="shortcut",
                    tag_terms=frozenset({"shortcut"}),
                )
            ],
            raw_tag_terms_by_id={"n1": frozenset({"shortcut"})},
        )
        monkeypatch.setattr(search_history_module, "search_index", index)

        assert record_note_interaction(
            note_id="n1",
            interaction_type="edit",
            token="token",
            interacted_on=date(2026, 8, 20),
        ) is True
        first_row = _fetch_rows()[0]
        assert "shortcut" not in first_row["payload_json"]
        assert isinstance(first_row["payload_encryption_nonce"], bytes)

        assert record_note_interaction(
            note_id="n1",
            interaction_type="command",
            token="token",
            interacted_on=date(2026, 8, 20),
        ) is True
        second_rows = _fetch_rows()
        assert len(second_rows) == 1
        assert second_rows[0]["storage_id"] == first_row["storage_id"]
        assert second_rows[0]["payload_json"] != first_row["payload_json"]
        assert second_rows[0]["payload_encryption_nonce"] != first_row["payload_encryption_nonce"]
    finally:
        set_encryption_required(False)
        clear_encryption_key()
        search_history_module.search_history_store.clear_persisted_state_for_tests()


def test_reset_tag_activity_deletes_only_the_aggregate_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_database(tmp_path, monkeypatch)
    try:
        index = _build_index(
            [
                SearchRecord(
                    note_id="n1",
                    content_text="Journal",
                    tags="journal",
                    tag_terms=frozenset({"journal"}),
                )
            ],
            raw_tag_terms_by_id={"n1": frozenset({"journal"})},
        )
        monkeypatch.setattr(search_history_module, "search_index", index)
        record_note_interaction(
            note_id="n1",
            interaction_type="edit",
            token="token",
            interacted_on=date(2026, 8, 20),
        )

        assert reset_search_history(token="token") == 1
        assert _fetch_rows() == []
        assert reset_search_history(token="token") == 0
    finally:
        search_history_module.search_history_store.clear_persisted_state_for_tests()


def test_search_suggestion_context_and_merge_preserve_base_order() -> None:
    assert is_first_search_tag_suggestion_context("") is True
    assert is_first_search_tag_suggestion_context("shor") is True
    assert is_first_search_tag_suggestion_context("journal next") is False
    assert prioritize_first_search_tag_suggestions(
        query="shor",
        base_suggestions=["short-story", "shortcut", "short-selling"],
        recent_tags=["shortcut"],
        priority_slots=3,
    ) == ["shortcut", "short-story", "short-selling"]
