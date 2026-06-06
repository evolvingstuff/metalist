from __future__ import annotations

from dataclasses import dataclass

import app.usecases.indent as indent_module
from app.usecases.indent import CmdIndent


@dataclass
class _Record:
    id: str
    parent_id: str | None
    tags: str
    is_collapsed: bool


class _FakeStore:
    def __init__(self) -> None:
        self.records = {
            "x": _Record(id="x", parent_id=None, tags="", is_collapsed=True),
            "y": _Record(id="y", parent_id=None, tags="", is_collapsed=False),
        }
        self.children_by_parent = {None: ["x", "y"], "x": []}

    def get(self, note_id: str) -> _Record:
        return self.records[note_id]

    def contains(self, note_id: str) -> bool:
        return note_id in self.records

    def children(self, parent_id: str | None) -> list[str]:
        return list(self.children_by_parent[parent_id])


def test_indent_expands_collapsed_new_parent(monkeypatch) -> None:
    fake_store = _FakeStore()
    expand_calls = []
    move_calls = []

    monkeypatch.setattr(indent_module, "store", fake_store)
    monkeypatch.setattr(
        indent_module,
        "apply_set_collapse",
        lambda note_id, collapsed: expand_calls.append((note_id, collapsed)),
    )
    monkeypatch.setattr(
        indent_module,
        "apply_move",
        lambda note_id, parent_id, prev_id, next_id: move_calls.append(
            (note_id, parent_id, prev_id, next_id)
        ),
    )
    monkeypatch.setattr(indent_module, "_neighbors", lambda note_id: (None, "x", None))
    monkeypatch.setattr(indent_module, "_assert_neighbors", lambda *args: None)
    monkeypatch.setattr(indent_module, "record_move", lambda *args, **kwargs: None)
    monkeypatch.setattr(indent_module, "generate_new_uuid", lambda: "uuid-1")

    result = CmdIndent(
        note_id="y",
        visible_prev_id="x",
        client_id="client-1",
        undo_context="tab:t|search:|epoch:0",
        viewport={},
    ).execute()

    assert result == {"status": "moved", "updateUUID": "uuid-1"}
    assert move_calls == [("y", "x", None, None)]
    assert expand_calls == [("x", False)]
