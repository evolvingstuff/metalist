from __future__ import annotations

from dataclasses import dataclass

from app.services.undo_state import _compute_focus_note_id


@dataclass(frozen=True, slots=True)
class _Record:
    id: str
    parent_id: str | None
    prev_id: str | None
    next_id: str | None


def test_compute_focus_note_id_undo_paste_prefers_prev_id() -> None:
    record = _Record(id="pasted", parent_id="parent", prev_id="target", next_id="next")
    op = {"type": "paste_subtree", "records": [record]}

    focus = _compute_focus_note_id(op, direction="undo")

    assert focus == "target"


def test_compute_focus_note_id_undo_paste_falls_back_to_parent_when_no_prev() -> None:
    record = _Record(id="pasted", parent_id="target", prev_id=None, next_id="next")
    op = {"type": "paste_subtree", "records": [record]}

    focus = _compute_focus_note_id(op, direction="undo")

    assert focus == "target"


def test_compute_focus_note_id_undo_paste_falls_back_to_next_when_no_prev_or_parent() -> None:
    record = _Record(id="pasted", parent_id=None, prev_id=None, next_id="next")
    op = {"type": "paste_subtree", "records": [record]}

    focus = _compute_focus_note_id(op, direction="undo")

    assert focus == "next"


def test_compute_focus_note_id_redo_paste_returns_root_id() -> None:
    record = _Record(id="pasted", parent_id="parent", prev_id="target", next_id="next")
    op = {"type": "paste_subtree", "records": [record]}

    focus = _compute_focus_note_id(op, direction="redo")

    assert focus == "pasted"

