from __future__ import annotations

from dataclasses import dataclass

import pytest

import app.api.routes.notes as notes_route
import app.usecases.move_to_top as move_to_top_module
from app.services.snapshot import SearchScope
from app.usecases.move_to_top import CmdMoveToTop


@dataclass
class _FakeRecord:
    id: str
    parent_id: str | None
    tags: str


class _FakeStore:
    def __init__(self, records: dict[str, _FakeRecord], children_by_parent: dict[str | None, list[str]]) -> None:
        self._records = records
        self._children_by_parent = children_by_parent

    def get(self, note_id: str) -> _FakeRecord:
        return self._records[note_id]

    def children(self, parent_id: str | None) -> list[str]:
        return list(self._children_by_parent.get(parent_id, []))


def test_move_to_top_moves_child_before_first_sibling(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _FakeStore(
        records={
            "a": _FakeRecord(id="a", parent_id="parent", tags=""),
            "b": _FakeRecord(id="b", parent_id="parent", tags=""),
            "c": _FakeRecord(id="c", parent_id="parent", tags=""),
        },
        children_by_parent={"parent": ["a", "b", "c"]},
    )
    monkeypatch.setattr(move_to_top_module, "store", fake_store)

    captured: dict[str, object] = {}

    monkeypatch.setattr(move_to_top_module, "_neighbors", lambda note_id: ("parent", "a", "c"))
    monkeypatch.setattr(
        move_to_top_module,
        "apply_move",
        lambda note_id, new_parent_id, prev_id, next_id: captured.update(
            note_id=note_id,
            new_parent_id=new_parent_id,
            prev_id=prev_id,
            next_id=next_id,
        ),
    )
    monkeypatch.setattr(
        move_to_top_module,
        "_assert_neighbors",
        lambda note_id, parent_id, prev_id, next_id: captured.update(
            asserted=(note_id, parent_id, prev_id, next_id),
        ),
    )
    monkeypatch.setattr(
        move_to_top_module,
        "record_move",
        lambda client_id, undo_context, note_id, **kwargs: captured.update(
            undo=(client_id, undo_context, note_id, kwargs),
        ),
    )
    monkeypatch.setattr(move_to_top_module, "generate_new_uuid", lambda: "uuid-move-top")

    result = CmdMoveToTop(
        note_id="b",
        search_query=None,
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert captured["note_id"] == "b"
    assert captured["new_parent_id"] == "parent"
    assert captured["prev_id"] is None
    assert captured["next_id"] == "a"
    assert captured["asserted"] == ("b", "parent", None, "a")
    assert captured["undo"][0:3] == ("client-1", "undo-1", "b")
    assert result == {"status": "moved", "updateUUID": "uuid-move-top"}


def test_move_to_top_uses_search_root_order_for_root_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _FakeStore(
        records={
            "hidden-root": _FakeRecord(id="hidden-root", parent_id=None, tags=""),
            "root-a": _FakeRecord(id="root-a", parent_id=None, tags=""),
            "root-b": _FakeRecord(id="root-b", parent_id=None, tags=""),
        },
        children_by_parent={None: ["hidden-root", "root-b", "root-a"]},
    )
    monkeypatch.setattr(move_to_top_module, "store", fake_store)

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        move_to_top_module,
        "resolve_search_scope",
        lambda *, search, editing_note_id: SearchScope(
            search_active=True,
            allowed_note_ids={"root-a", "root-b"},
            search_root_ids_ordered=["root-b", "root-a"],
            search_root_count_total=2,
        ),
    )
    monkeypatch.setattr(
        move_to_top_module,
        "_neighbors",
        lambda note_id: (
            (None, "root-b", None)
            if note_id == "root-a"
            else (None, "hidden-root", "root-a")
        ),
    )
    monkeypatch.setattr(
        move_to_top_module,
        "apply_move",
        lambda note_id, new_parent_id, prev_id, next_id: captured.update(
            note_id=note_id,
            new_parent_id=new_parent_id,
            prev_id=prev_id,
            next_id=next_id,
        ),
    )
    monkeypatch.setattr(move_to_top_module, "_assert_neighbors", lambda *args: None)
    monkeypatch.setattr(move_to_top_module, "record_move", lambda *args, **kwargs: None)
    monkeypatch.setattr(move_to_top_module, "generate_new_uuid", lambda: "uuid-search-root")

    result = CmdMoveToTop(
        note_id="root-a",
        search_query="journal",
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert captured == {
        "note_id": "root-a",
        "new_parent_id": None,
        "prev_id": "hidden-root",
        "next_id": "root-b",
    }
    assert result == {"status": "moved", "updateUUID": "uuid-search-root"}


def test_move_to_top_noops_when_note_is_already_first(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _FakeStore(
        records={"root-a": _FakeRecord(id="root-a", parent_id=None, tags="")},
        children_by_parent={None: ["root-a"]},
    )
    monkeypatch.setattr(move_to_top_module, "store", fake_store)

    result = CmdMoveToTop(
        note_id="root-a",
        search_query=None,
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert result == {"status": "noop"}


def test_move_to_top_route_normalizes_empty_search_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notes_route, "_require_viewport", lambda body: {"scrollY": 0})
    monkeypatch.setattr(notes_route, "_require_note_present", lambda note_id, *, context: None)

    captured: dict[str, object] = {}

    class _FakeCmdMoveToTop:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def execute(self) -> dict[str, str]:
            return {"status": "moved"}

    monkeypatch.setattr(notes_route, "CmdMoveToTop", _FakeCmdMoveToTop)

    result = notes_route.move_note_to_top_endpoint(
        "root-a",
        {
            "search_query": "",
            "clientId": "client-1",
            "undoContext": "undo-1",
            "viewport": {"scrollY": 0},
        },
    )

    assert captured["note_id"] == "root-a"
    assert captured["search_query"] is None
    assert captured["client_id"] == "client-1"
    assert captured["undo_context"] == "undo-1"
    assert captured["viewport"] == {"scrollY": 0}
    assert result == {"status": "moved"}
