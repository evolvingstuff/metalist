from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import undo_state


def test_redo_create_note_does_not_require_tag_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    undo_state._clients.clear()
    client_id = "client-1"
    token = "token"

    restored: list[object] = []

    def fake_restore(records: list[object], _token: str) -> None:
        assert _token == token
        assert len(records) == 1
        record = records[0]
        assert getattr(record, "id") == "note-1"
        assert isinstance(getattr(record, "content"), str)
        assert isinstance(getattr(record, "tags"), str)
        restored.append(record)

    monkeypatch.setattr(undo_state, "apply_restore_records", fake_restore)
    monkeypatch.setattr(
        undo_state,
        "store",
        SimpleNamespace(get=lambda note_id: SimpleNamespace(id=note_id, parent_id=None)),
    )

    ctx = undo_state._ctx(client_id)
    ctx.redo.append(
        {
            "type": "create_note",
            "record": {
                "id": "note-1",
                "parent_id": None,
                "prev_id": None,
                "next_id": None,
                "is_collapsed": False,
                "content": "",
                "tags": "",
                "created_at": None,
                "updated_at": None,
            },
            "viewport": {"scrollY": 0, "scrollAnchor": None},
            "viewAnchorRootId": "note-1",
        }
    )

    payload = undo_state.redo(client_id, token)
    assert payload is not None
    assert payload["opType"] == "create_note"
    assert restored
    assert isinstance(restored[0], SimpleNamespace)

