from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

from app.services.snapshot import build_view_state


@dataclass
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


def _state_for(
    *,
    monkeypatch: pytest.MonkeyPatch,
    notes: Dict[str, _Note],
    children_by_parent: Dict[Optional[str], List[str]],
    editing_note_id: Optional[str] = None,
):
    store = _FakeNoteStore(notes=notes, children_by_parent=children_by_parent)

    import app.services.snapshot as snapshot

    monkeypatch.setattr(snapshot, "note_store", store)
    monkeypatch.setattr(snapshot, "get_all_locks", lambda: {})
    return build_view_state(
        editing_note_id=editing_note_id,
        search=None,
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )


def test_embed_reference_renders_as_block_and_includes_descendants(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        "a": _Note("a", None, None, "b", False, "<div>blah ![[b]] yada</div>", ""),
        "b": _Note("b", None, "a", None, True, "<div>embedded root</div>", ""),
        "c": _Note("c", "b", None, None, False, "<div>embedded child</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: ["a", "b"], "b": ["c"]},
    )

    rendered = state.payloads["a"]["content"]
    assert "note-embed-block" in rendered
    assert 'data-embed-ref-id="b"' in rendered
    assert "embedded root" in rendered
    assert "embedded child" in rendered
    assert rendered.index("blah") < rendered.index("note-embed-block")
    assert rendered.index("note-embed-block") < rendered.index("yada")


def test_embed_reference_missing_uuid_shows_missing_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        "a": _Note("a", None, None, None, False, "<div>![[does-not-exist]]</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: ["a"]},
    )

    rendered = state.payloads["a"]["content"]
    assert "note-embed-missing" in rendered
    assert "Missing reference: does-not-exist" in rendered


def test_embed_reference_cycle_shows_cycle_marker_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        "a": _Note("a", None, None, None, False, "<div>![[b]]</div>", ""),
        "b": _Note("b", None, None, None, False, "<div>![[a]]</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: ["a", "b"]},
    )

    rendered = state.payloads["a"]["content"]
    assert "note-embed-block" in rendered
    assert "note-embed-cycle" in rendered
    assert "Circular reference: a" in rendered


def test_plain_reference_renders_link_mode_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        "a": _Note("a", None, None, None, False, "<div>prefix [[b]] suffix</div>", ""),
        "b": _Note("b", None, None, None, False, "<div>linked first line</div><div>linked second line</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: ["a", "b"]},
    )

    rendered = state.payloads["a"]["content"]
    assert "note-reference-link-mode" in rendered
    assert "note-reference-link" in rendered
    assert "linked first line" in rendered
    assert "linked second line" not in rendered
    assert 'data-ref-mode="link"' in rendered
    assert 'data-ref-target-mode="embed"' in rendered


def test_multiple_references_expose_stable_occurrence_indices(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        "a": _Note("a", None, None, None, False, "<div>[[b]] ![[c]] [[b]]</div>", ""),
        "b": _Note("b", None, None, "c", False, "<div>B</div>", ""),
        "c": _Note("c", None, "b", None, False, "<div>C</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: ["a", "b", "c"]},
    )

    rendered = state.payloads["a"]["content"]
    assert rendered.count('data-ref-occurrence="0"') == 1
    assert rendered.count('data-ref-occurrence="1"') == 1
    assert rendered.count('data-ref-occurrence="2"') == 1


def test_edit_mode_keeps_literal_embed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        "a": _Note("a", None, None, "b", False, "<div>![[b]]</div>", ""),
        "b": _Note("b", None, "a", None, False, "<div>embedded</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: ["a", "b"]},
        editing_note_id="a",
    )

    rendered = state.payloads["a"]["content"]
    assert "![[b]]" in rendered
    assert "note-embed-block" not in rendered


def test_embed_host_hash_changes_when_referenced_note_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        "a": _Note("a", None, None, "b", False, "<div>![[b]]</div>", ""),
        "b": _Note("b", None, "a", None, False, "<div>before</div>", ""),
    }
    children_by_parent = {None: ["a", "b"]}
    state_one = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent=children_by_parent,
    )
    first_hash = state_one.payloads["a"]["hash"]

    notes["b"].content = "<div>after</div>"
    state_two = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent=children_by_parent,
    )
    second_hash = state_two.payloads["a"]["hash"]

    assert first_hash != second_hash
