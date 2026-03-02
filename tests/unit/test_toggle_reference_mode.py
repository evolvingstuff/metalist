from __future__ import annotations

from dataclasses import dataclass

import app.usecases.toggle_reference_mode as toggle_module
from app.services.embedded_references import replace_reference_token_mode_in_html


def test_replace_reference_token_mode_updates_only_target_occurrence() -> None:
    content = "<div>[[aaa]] ![[bbb]] [[aaa]]</div>"
    updated, changed = replace_reference_token_mode_in_html(
        content_html=content,
        reference_note_id="aaa",
        occurrence_index=2,
        target_mode="embed",
    )

    assert changed
    assert updated == "<div>[[aaa]] ![[bbb]] ![[aaa]]</div>"


def test_replace_reference_token_mode_noop_when_reference_mismatches() -> None:
    content = "<div>[[aaa]]</div>"
    updated, changed = replace_reference_token_mode_in_html(
        content_html=content,
        reference_note_id="bbb",
        occurrence_index=0,
        target_mode="embed",
    )

    assert not changed
    assert updated == content


@dataclass
class _Record:
    id: str
    content: str
    tags: str


class _FakeStore:
    def __init__(self, record: _Record) -> None:
        self._record = record

    def get(self, note_id: str) -> _Record:
        if note_id != self._record.id:
            raise KeyError(note_id)
        return self._record


def test_cmd_toggle_reference_mode_updates_content_and_records_undo(monkeypatch) -> None:
    record = _Record(
        id="host",
        content="<div>![[target]] [[other]]</div>",
        tags="alpha beta",
    )
    fake_store = _FakeStore(record=record)
    monkeypatch.setattr(toggle_module, "store", fake_store)

    captured = {
        "update": None,
        "undo": None,
    }

    def _fake_apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
        captured["update"] = (note_id, content, tags, token)

    def _fake_record_update(*args, **kwargs) -> None:
        captured["undo"] = (args, kwargs)

    monkeypatch.setattr(toggle_module, "apply_update_content", _fake_apply_update_content)
    monkeypatch.setattr(toggle_module, "generate_new_uuid", lambda: "uuid-updated")
    monkeypatch.setattr("app.services.undo_state.record_update", _fake_record_update)

    command = toggle_module.CmdToggleReferenceMode(
        note_id="host",
        reference_note_id="target",
        occurrence_index=0,
        mode="link",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )
    result = command.execute()

    assert captured["update"] == (
        "host",
        "<div>[[target]] [[other]]</div>",
        "alpha beta",
        "token",
    )
    assert captured["undo"] is not None
    assert result == {"status": "updated", "updateUUID": "uuid-updated"}
