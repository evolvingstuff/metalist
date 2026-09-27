from __future__ import annotations

import random

import pytest

import app.services.embedded_references as embedded_references
import app.services.sync as sync
import app.services.undo_state as undo_state
from app.services.embedded_references import collapsed_preview_source_has_hidden_content
from app.services.embedded_references import extract_collapsed_preview_source_html
from app.services.snapshot import _SnapshotTraversalCache


_VIEWPORT = {"scrollY": 0, "scrollAnchor": None}


def test_collapsed_preview_head_matches_full_fragment_scan() -> None:
    rng = random.Random(23)
    pieces = [
        "<div>", "</div>", "<p>", "</p>", "<br>", "<br/>", "\n", "text", " ", "<img src=x>",
        "<b>", "</b>", "[[00000000-0000-0000-0000-000000000000]]", "&nbsp;", "<span></span>",
    ]
    for _ in range(3000):
        content = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 14)))
        fragments = list(embedded_references._iter_collapsed_preview_meaningful_fragments(content))

        assert extract_collapsed_preview_source_html(content) == "".join(fragments[:1])
        assert collapsed_preview_source_has_hidden_content(content) == (len(fragments) > 1)


def test_collapsed_preview_head_stops_after_second_fragment(monkeypatch: pytest.MonkeyPatch) -> None:
    yielded: list[str] = []
    original = embedded_references._iter_collapsed_preview_meaningful_fragments

    def counting(content_html: str):
        for fragment in original(content_html):
            yielded.append(fragment)
            yield fragment

    monkeypatch.setattr(embedded_references, "_iter_collapsed_preview_meaningful_fragments", counting)
    embedded_references._collapsed_preview_head.cache_clear()
    content = "".join(f"<div>line {index}</div>" for index in range(50))

    assert embedded_references._collapsed_preview_head(content) == ("<div>line 0</div>", True)
    assert yielded == ["<div>line 0</div>", "<div>line 1</div>"]
    embedded_references._collapsed_preview_head.cache_clear()


def test_view_metadata_carries_only_client_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Record:
        created_at = None
        updated_at = None

    cache = _SnapshotTraversalCache()
    monkeypatch.setattr(cache, "get_note", lambda _note_id: _Record())

    assert cache.build_metadata("note") == {"createdAt": "", "updatedAt": ""}


def test_undo_budget_walk_skipped_for_existing_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    undo_state.reset_all_undo_state()
    undo_state.record_update("client", "context", "note", before="a", after="b",
                             before_tags="", after_tags="", viewport=_VIEWPORT)
    walks: list[object] = []
    original = undo_state.retained_bytes
    monkeypatch.setattr(undo_state, "retained_bytes", lambda value: walks.append(value) or original(value))

    undo_state.maybe_reset_on_context("client", "context")
    assert walks == []

    undo_state.record_update("client", "context", "note", before="b", after="c",
                             before_tags="", after_tags="", viewport=_VIEWPORT)
    assert len(walks) == 1
    undo_state.reset_all_undo_state()


def test_undo_budget_still_enforced_when_undo_moves_an_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    undo_state.reset_all_undo_state()
    undo_state.record_update("client", "context", "note", before="a", after="b",
                             before_tags="", after_tags="", viewport=_VIEWPORT)
    monkeypatch.setattr(undo_state, "apply_update_content", lambda *_args: None)
    monkeypatch.setattr(undo_state, "generate_new_uuid", lambda: None)
    monkeypatch.setattr(undo_state, "_compute_focus_note_id", lambda _op, *, direction: None)
    monkeypatch.setattr(undo_state, "UNDO_BYTES", 1)

    undo_state.undo("client", "token")

    assert undo_state._clients["client"].history == []
    assert undo_state._clients["client"].redo == []
    assert undo_state.undo_history_limited("client")
    undo_state.reset_all_undo_state()


def test_sync_capture_shares_immutable_clipboards_until_restore() -> None:
    sync.set_clipboard("fixture", [{"content": {"text": "original"}}])
    live = sync._clipboards["fixture"]

    snapshot = sync.capture_sync_state()

    assert snapshot[2]["fixture"] is live
    sync.restore_sync_state(snapshot)
    assert sync._clipboards["fixture"] is not live
    assert sync._clipboards["fixture"] == live
    sync.reset_state()
