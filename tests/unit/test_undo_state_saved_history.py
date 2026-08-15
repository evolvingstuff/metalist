from __future__ import annotations

from app.services import undo_state


def test_selection_transitions_are_not_undo_history_operations() -> None:
    assert not hasattr(undo_state, "record_edit_mode")
