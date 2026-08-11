from __future__ import annotations

from dataclasses import dataclass

import pytest

import app.usecases.set_collapse_in_context as collapse_context_module
from app.usecases.set_collapse_in_context import CmdSetCollapseInContext


@dataclass
class _FakeRecord:
    id: str
    parent_id: str | None
    is_collapsed: bool


class _FakeNoteStore:
    def __init__(self, records: list[_FakeRecord]) -> None:
        self.records = {record.id: record for record in records}
        self.children_by_parent: dict[str | None, list[str]] = {}
        for record in records:
            self.children_by_parent.setdefault(record.parent_id, []).append(record.id)

    def get_children(self, parent_id: str | None) -> list[str]:
        return list(self.children_by_parent.get(parent_id, []))

    def has_note(self, note_id: str) -> bool:
        return note_id in self.records

    def get_note(self, note_id: str) -> _FakeRecord:
        return self.records[note_id]


class _FakeStore:
    def __init__(self, note_store: _FakeNoteStore) -> None:
        self.note_store = note_store

    def get(self, note_id: str) -> _FakeRecord:
        return self.note_store.records[note_id]


@pytest.mark.parametrize(
    ("target_collapsed", "initial_root_collapsed", "initial_child_states"),
    [
        (True, False, {"child-a": False, "grandchild-a": True, "child-b": True}),
        (False, True, {"child-a": True, "grandchild-a": False, "child-b": False}),
    ],
)
def test_set_collapse_in_context_updates_roots_only(
    monkeypatch: pytest.MonkeyPatch,
    target_collapsed: bool,
    initial_root_collapsed: bool,
    initial_child_states: dict[str, bool],
) -> None:
    records = [
        _FakeRecord("root-a", None, initial_root_collapsed),
        _FakeRecord("child-a", "root-a", initial_child_states["child-a"]),
        _FakeRecord("grandchild-a", "child-a", initial_child_states["grandchild-a"]),
        _FakeRecord("root-b", None, initial_root_collapsed),
        _FakeRecord("child-b", "root-b", initial_child_states["child-b"]),
    ]
    fake_note_store = _FakeNoteStore(records)
    fake_store = _FakeStore(fake_note_store)
    bulk_calls: list[tuple[list[str], bool]] = []

    def fake_apply_set_collapse_bulk(note_ids: list[str], collapsed: bool) -> None:
        bulk_calls.append((list(note_ids), collapsed))
        for note_id in note_ids:
            fake_note_store.records[note_id].is_collapsed = collapsed

    monkeypatch.setattr(collapse_context_module, "note_store", fake_note_store)
    monkeypatch.setattr(collapse_context_module, "store", fake_store)
    monkeypatch.setattr(
        collapse_context_module,
        "apply_set_collapse_bulk",
        fake_apply_set_collapse_bulk,
    )
    monkeypatch.setattr(collapse_context_module, "reset_undo_stack", lambda *args: None)
    monkeypatch.setattr(collapse_context_module, "generate_new_uuid", lambda: "collapse-uuid")

    result = CmdSetCollapseInContext(
        search_query=None,
        collapsed=target_collapsed,
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert bulk_calls == [(["root-a", "root-b"], target_collapsed)]
    assert fake_note_store.records["root-a"].is_collapsed is target_collapsed
    assert fake_note_store.records["root-b"].is_collapsed is target_collapsed
    for child_id, initial_state in initial_child_states.items():
        assert fake_note_store.records[child_id].is_collapsed is initial_state
    assert result == {
        "status": "updated",
        "updatedCount": 2,
        "totalCount": 2,
        "updateUUID": "collapse-uuid",
    }
