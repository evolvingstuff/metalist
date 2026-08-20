from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import app.usecases.add_selected_text_tag as add_tag_module


def _record(*, tags: str) -> SimpleNamespace:
    return SimpleNamespace(
        content="<div>Neural Networks are useful</div>",
        tags=tags,
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_command_uses_existing_namespace_variant_and_records_tag_only_update(monkeypatch) -> None:
    record = _record(tags="machine-learning")
    applied: list[tuple[str, str, str, str]] = []
    undo_calls: list[dict[str, object]] = []

    monkeypatch.setattr(add_tag_module.store, "get", lambda note_id: record)
    monkeypatch.setattr(
        add_tag_module.search_index,
        "list_explicit_tag_frequencies",
        lambda: {"Neural.Networks": 2, "neural_networks": 7},
    )
    monkeypatch.setattr(
        add_tag_module,
        "apply_update_content",
        lambda note_id, content, tags, token: applied.append((note_id, content, tags, token)),
    )
    monkeypatch.setattr(add_tag_module, "record_update", lambda *args, **kwargs: undo_calls.append(kwargs))
    monkeypatch.setattr(add_tag_module, "generate_new_uuid", lambda: "update-1")

    response = add_tag_module.CmdAddSelectedTextTag(
        note_id="note-a",
        selected_text="Neural Networks",
        token="token",
        client_id="client",
        undo_context="undo",
        viewport={"scrollY": 0},
    ).execute()

    assert response == {
        "status": "added",
        "tag": "neural_networks",
        "tags": "machine-learning neural_networks",
        "updateUUID": "update-1",
    }
    assert applied == [
        (
            "note-a",
            "<div>Neural Networks are useful</div>",
            "machine-learning neural_networks",
            "token",
        )
    ]
    assert undo_calls == [
        {
            "before": "<div>Neural Networks are useful</div>",
            "after": "<div>Neural Networks are useful</div>",
            "before_tags": "machine-learning",
            "after_tags": "machine-learning neural_networks",
            "viewport": {"scrollY": 0},
        }
    ]


def test_command_does_not_duplicate_equivalent_tag_already_on_note(monkeypatch) -> None:
    record = _record(tags="Neural.Networks machine-learning")

    monkeypatch.setattr(add_tag_module.store, "get", lambda note_id: record)
    monkeypatch.setattr(
        add_tag_module.search_index,
        "list_explicit_tag_frequencies",
        lambda: {"neural_networks": 20, "Neural.Networks": 1},
    )
    monkeypatch.setattr(
        add_tag_module,
        "apply_update_content",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("existing tag must not be saved")),
    )
    monkeypatch.setattr(add_tag_module, "get_current_sync_uuid", lambda: "update-2")

    response = add_tag_module.CmdAddSelectedTextTag(
        note_id="note-a",
        selected_text="neural networks",
        token="token",
        client_id="client",
        undo_context="undo",
        viewport={"scrollY": 0},
    ).execute()

    assert response == {
        "status": "exists",
        "tag": "Neural.Networks",
        "tags": "Neural.Networks machine-learning",
        "updateUUID": "update-2",
    }
