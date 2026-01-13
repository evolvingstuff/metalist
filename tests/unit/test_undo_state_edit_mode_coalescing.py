from __future__ import annotations

from typing import Dict

from app.services.undo_state import _ctx, maybe_reset_on_context, record_edit_mode


def _viewport() -> Dict[str, object]:
    return {
        "scrollY": 0,
        "scrollAnchor": None,
    }


def test_record_edit_mode_coalesces_enter_exit_without_edits() -> None:
    client_id = "test-client"
    undo_context = "tab:main|search:"

    maybe_reset_on_context(client_id, undo_context)

    record_edit_mode(
        client_id,
        undo_context,
        before_editing_note_id=None,
        after_editing_note_id="n1",
        viewport=_viewport(),
    )
    record_edit_mode(
        client_id,
        undo_context,
        before_editing_note_id="n1",
        after_editing_note_id=None,
        viewport=_viewport(),
    )

    ctx = _ctx(client_id)
    assert len(ctx.history) == 1
    op = ctx.history[0]
    assert op["type"] == "edit_mode"
    assert op["before_editing_note_id"] == "n1"
    assert op["after_editing_note_id"] is None

