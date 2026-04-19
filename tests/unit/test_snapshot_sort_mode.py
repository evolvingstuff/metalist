from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from app.services.snapshot import build_view_state


@dataclass(frozen=True)
class _Note:
    id: str
    parent_id: Optional[str]
    prev_id: Optional[str]
    next_id: Optional[str]
    is_collapsed: bool
    content: str
    tags: str
    created_at: datetime
    updated_at: datetime


class _FakeNoteStore:
    def __init__(self, *, notes: Dict[str, _Note], children_by_parent: Dict[Optional[str], List[str]]):
        self._notes = notes
        self._children_by_parent = children_by_parent

    def has_note(self, note_id: str) -> bool:
        return note_id in self._notes

    def get_note(self, note_id: str) -> _Note:
        return self._notes[note_id]

    def get_children(self, parent_id: Optional[str]) -> List[str]:
        return list(self._children_by_parent.get(parent_id, []))


def _patch_fake_store(monkeypatch: pytest.MonkeyPatch, store: _FakeNoteStore) -> None:
    import app.services.snapshot as snapshot
    import app.services.root_sorting as root_sorting

    monkeypatch.setattr(snapshot, "note_store", store)
    monkeypatch.setattr(snapshot, "get_all_locks", lambda: {})
    monkeypatch.setattr(root_sorting, "note_store", store)


def test_build_view_state_uses_newest_created_timestamp_in_root_subtree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        "root-old": _Note(
            id="root-old",
            parent_id=None,
            prev_id=None,
            next_id="root-new",
            is_collapsed=False,
            content="<div>old</div>",
            tags="",
            created_at=datetime(2025, 4, 7, 20, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 4, 8, 20, 0, tzinfo=timezone.utc),
        ),
        "root-new": _Note(
            id="root-new",
            parent_id=None,
            prev_id="root-old",
            next_id=None,
            is_collapsed=False,
            content="<div>new</div>",
            tags="",
            created_at=datetime(2026, 4, 17, 20, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc),
        ),
        "child-new": _Note(
            id="child-new",
            parent_id="root-old",
            prev_id=None,
            next_id=None,
            is_collapsed=False,
            content="<div>child</div>",
            tags="",
            created_at=datetime(2026, 4, 18, 20, 5, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 18, 20, 5, tzinfo=timezone.utc),
        ),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["root-old", "root-new"], "root-old": ["child-new"]},
    )
    _patch_fake_store(monkeypatch, store)

    state = build_view_state(
        editing_note_id=None,
        search=None,
        sort_mode="created",
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )

    assert state.children_by_parent[None] == ["root-old", "root-new"]
    assert state.children_by_parent["root-old"] == ["child-new"]
    assert state.metadata["sortMode"] == "created"
    assert state.metadata["rootSortBuckets"] == {
        "root-old": {"key": "2026-04-18", "label": "2026/04/18 - Saturday"},
        "root-new": {"key": "2026-04-17", "label": "2026/04/17 - Friday"},
    }


def test_build_view_state_uses_newest_updated_timestamp_in_root_subtree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        "root-stale": _Note(
            id="root-stale",
            parent_id=None,
            prev_id=None,
            next_id="root-fresh",
            is_collapsed=False,
            content="<div>stale</div>",
            tags="",
            created_at=datetime(2025, 4, 7, 20, 0, tzinfo=timezone.utc),
            updated_at=datetime(2025, 4, 8, 20, 0, tzinfo=timezone.utc),
        ),
        "root-fresh": _Note(
            id="root-fresh",
            parent_id=None,
            prev_id="root-stale",
            next_id=None,
            is_collapsed=False,
            content="<div>fresh</div>",
            tags="",
            created_at=datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc),
        ),
        "child-freshest": _Note(
            id="child-freshest",
            parent_id="root-stale",
            prev_id=None,
            next_id=None,
            is_collapsed=False,
            content="<div>child</div>",
            tags="",
            created_at=datetime(2026, 4, 11, 20, 5, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 19, 20, 5, tzinfo=timezone.utc),
        ),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["root-stale", "root-fresh"], "root-stale": ["child-freshest"]},
    )
    _patch_fake_store(monkeypatch, store)

    state = build_view_state(
        editing_note_id=None,
        search=None,
        sort_mode="updated",
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )

    assert state.children_by_parent[None] == ["root-stale", "root-fresh"]
    assert state.metadata["sortMode"] == "updated"
    assert state.metadata["rootSortBuckets"] == {
        "root-stale": {"key": "2026-04-19", "label": "2026/04/19 - Sunday"},
        "root-fresh": {"key": "2026-04-18", "label": "2026/04/18 - Saturday"},
    }
