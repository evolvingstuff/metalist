from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import app.services.undo_state as undo_state_module
import app.usecases.update_content as update_content_module


def test_update_content_saves_and_records_previous_tags(monkeypatch) -> None:
    undo_calls: list[dict[str, object]] = []
    activity_calls: list[dict[str, object]] = []
    record = SimpleNamespace(content="before", tags="old-tag")

    monkeypatch.setattr(update_content_module.store, "get", lambda note_id: record)
    monkeypatch.setattr(update_content_module, "sanitize_note_html", lambda content: content)
    monkeypatch.setattr(update_content_module, "apply_update_content", lambda *args: None)
    monkeypatch.setattr(undo_state_module, "record_update", lambda *args, **kwargs: undo_calls.append(kwargs))
    monkeypatch.setattr(update_content_module, "generate_new_uuid", lambda: "update-1")
    monkeypatch.setattr(update_content_module, "current_local_date", lambda: date(2026, 8, 21))
    monkeypatch.setattr(
        update_content_module,
        "record_explicit_tag_additions",
        lambda **kwargs: activity_calls.append(kwargs) or True,
    )

    result = update_content_module.CmdUpdateContent(
        note_id="note-1",
        content="after",
        tags="new-tag",
        token="token",
        client_id="client-1",
        undo_context="tab-1",
        viewport={},
    ).execute()

    assert result == {"status": "success", "updateUUID": "update-1"}
    assert len(undo_calls) == 1
    assert undo_calls[0]["before_tags"] == "old-tag"
    assert undo_calls[0]["after_tags"] == "new-tag"
    assert activity_calls == [
        {
            "before_tags": "old-tag",
            "after_tags": "new-tag",
            "token": "token",
            "interacted_on": date(2026, 8, 21),
        }
    ]
