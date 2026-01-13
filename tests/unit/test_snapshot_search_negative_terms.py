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


def test_negative_text_term_redacts_notes_containing_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tree:
    # r1
    #   c1(AAB)
    #   c2
    notes = {
        "r1": _Note("r1", None, None, None, False, "<div>r1</div>", ""),
        "c1": _Note("c1", "r1", None, "c2", False, "<div>AAB</div>", ""),
        "c2": _Note("c2", "r1", "c1", None, False, "<div>c2</div>", ""),
    }
    store = _FakeNoteStore(notes=notes, children_by_parent={None: ["r1"], "r1": ["c1", "c2"]})

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
        search='-"AAB"',
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )

    assert not state.payloads["c2"]["flags"]["searchRedacted"]
    assert state.payloads["c1"]["flags"]["searchRedacted"]


def test_negative_text_term_redacts_forbidden_descendants(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tree:
    # r1(AA)
    #   c1(AAB)
    notes = {
        "r1": _Note("r1", None, None, None, False, "<div>AA</div>", ""),
        "c1": _Note("c1", "r1", None, None, False, "<div>AAB</div>", ""),
    }
    store = _FakeNoteStore(notes=notes, children_by_parent={None: ["r1"], "r1": ["c1"]})

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
        search='"AA" -"AAB"',
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )

    assert not state.payloads["r1"]["flags"]["searchRedacted"]
    assert state.payloads["c1"]["flags"]["searchRedacted"]
