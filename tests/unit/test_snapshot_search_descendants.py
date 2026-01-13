from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

from app.services.search_index import SearchIndex, SearchRecord, extract_tags_for_search
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


def _visible_ids(state) -> set[str]:
    return {entry["id"] for entry in state.structure}


def test_search_includes_descendants_of_matching_root(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tree:
    # r1(asdf)
    #   c1
    #     g1
    #   c2
    # r2
    notes = {
        "r1": _Note("r1", None, None, "r2", False, "<div>r1</div>", "asdf"),
        "c1": _Note("c1", "r1", None, "c2", False, "<div>c1</div>", ""),
        "g1": _Note("g1", "c1", None, None, False, "<div>g1</div>", ""),
        "c2": _Note("c2", "r1", "c1", None, False, "<div>c2</div>", ""),
        "r2": _Note("r2", None, "r1", None, False, "<div>r2</div>", ""),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["r1", "r2"], "r1": ["c1", "c2"], "c1": ["g1"]},
    )

    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id=n.id,
                content_html=n.content,
                tags=n.tags,
                tag_terms=extract_tags_for_search(n.tags),
            )
            for n in notes.values()
        ]
    )

    import app.services.snapshot as snapshot

    monkeypatch.setattr(snapshot, "note_store", store)
    monkeypatch.setattr(snapshot, "search_index", index)
    monkeypatch.setattr(snapshot, "get_all_locks", lambda: {})

    state = build_view_state(
        editing_note_id=None,
        search="asdf",
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )

    assert _visible_ids(state) == {"r1", "c1", "g1", "c2"}


def test_search_includes_descendants_of_matching_non_root(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tree:
    # r1
    #   c1(asdf)
    #     g1
    #   c2
    notes = {
        "r1": _Note("r1", None, None, None, False, "<div>r1</div>", ""),
        "c1": _Note("c1", "r1", None, "c2", False, "<div>c1</div>", "asdf"),
        "g1": _Note("g1", "c1", None, None, False, "<div>g1</div>", ""),
        "c2": _Note("c2", "r1", "c1", None, False, "<div>c2</div>", ""),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["r1"], "r1": ["c1", "c2"], "c1": ["g1"]},
    )

    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id=n.id,
                content_html=n.content,
                tags=n.tags,
                tag_terms=extract_tags_for_search(n.tags),
            )
            for n in notes.values()
        ]
    )

    import app.services.snapshot as snapshot

    monkeypatch.setattr(snapshot, "note_store", store)
    monkeypatch.setattr(snapshot, "search_index", index)
    monkeypatch.setattr(snapshot, "get_all_locks", lambda: {})

    state = build_view_state(
        editing_note_id=None,
        search="asdf",
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )

    assert _visible_ids(state) == {"r1", "c1", "g1", "c2"}
    assert not state.payloads["r1"]["flags"]["searchRedacted"]
    assert not state.payloads["c1"]["flags"]["searchRedacted"]
    assert not state.payloads["g1"]["flags"]["searchRedacted"]
    assert state.payloads["c2"]["flags"]["searchRedacted"]
