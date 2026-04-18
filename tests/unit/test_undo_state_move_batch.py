from __future__ import annotations

from types import SimpleNamespace

from app.services import undo_state


def test_undo_and_redo_move_batch_use_one_history_op(monkeypatch) -> None:
    undo_state._clients.clear()
    client_id = "client-1"
    token = "token-1"

    apply_calls: list[tuple[str, str | None, str | None, str | None]] = []
    tag_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        undo_state,
        "apply_move",
        lambda note_id, parent_id, prev_id, next_id: apply_calls.append(
            (note_id, parent_id, prev_id, next_id)
        ),
    )
    monkeypatch.setattr(undo_state, "_assert_neighbors", lambda *args: None)
    monkeypatch.setattr(
        undo_state,
        "_apply_move_tags",
        lambda op, *, tags_key, token: tag_calls.append((op["note_id"], tags_key, token)),
    )
    monkeypatch.setattr(undo_state, "generate_new_uuid", lambda: None)
    monkeypatch.setattr(
        undo_state,
        "store",
        SimpleNamespace(get=lambda note_id: SimpleNamespace(id=note_id, parent_id=None)),
    )

    move_batch_op = {
        "type": "move_batch",
        "moves": [
            {
                "note_id": "root-c",
                "before_parent": None,
                "before_prev": "root-b",
                "before_next": "root-d",
                "before_tags": "",
                "after_parent": None,
                "after_prev": "root-a",
                "after_next": "root-b",
                "after_tags": "",
            },
            {
                "note_id": "root-e",
                "before_parent": None,
                "before_prev": "root-d",
                "before_next": "root-f",
                "before_tags": "",
                "after_parent": None,
                "after_prev": "root-c",
                "after_next": "root-d",
                "after_tags": "",
            },
        ],
        "viewport": {"scrollY": 0, "scrollAnchor": None},
        "viewAnchorRootId": "root-a",
    }

    ctx = undo_state._ctx(client_id)
    ctx.history.append(move_batch_op)

    undo_payload = undo_state.undo(client_id, token)

    assert undo_payload is not None
    assert undo_payload["opType"] == "move_batch"
    assert undo_payload["focusNoteId"] == "root-c"
    assert apply_calls == [
        ("root-e", None, "root-d", "root-f"),
        ("root-c", None, "root-b", "root-d"),
    ]
    assert tag_calls == [
        ("root-e", "before_tags", token),
        ("root-c", "before_tags", token),
    ]
    assert len(ctx.history) == 0
    assert len(ctx.redo) == 1

    apply_calls.clear()
    tag_calls.clear()

    redo_payload = undo_state.redo(client_id, token)

    assert redo_payload is not None
    assert redo_payload["opType"] == "move_batch"
    assert redo_payload["focusNoteId"] == "root-c"
    assert apply_calls == [
        ("root-c", None, "root-a", "root-b"),
        ("root-e", None, "root-c", "root-d"),
    ]
    assert tag_calls == [
        ("root-c", "after_tags", token),
        ("root-e", "after_tags", token),
    ]
    assert len(ctx.history) == 1
    assert len(ctx.redo) == 0
