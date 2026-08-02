from __future__ import annotations

from dataclasses import dataclass

import app.usecases.unformat_content as unformat_module


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


def test_cmd_unformat_content_updates_content_and_records_undo(monkeypatch) -> None:
    record = _Record(
        id="note-1",
        content="<h1><strong>Heading</strong></h1><div>Body</div>",
        tags="@todo @bold",
    )
    monkeypatch.setattr(unformat_module, "store", _FakeStore(record))

    captured = {
        "update": None,
        "undo": None,
    }

    def _fake_apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
        captured["update"] = (note_id, content, tags, token)

    def _fake_record_update(*args, **kwargs) -> None:
        captured["undo"] = (args, kwargs)

    monkeypatch.setattr(unformat_module, "apply_update_content", _fake_apply_update_content)
    monkeypatch.setattr(unformat_module, "generate_new_uuid", lambda: "uuid-unformatted")
    monkeypatch.setattr("app.services.undo_state.record_update", _fake_record_update)

    command = unformat_module.CmdUnformatContent(
        note_id="note-1",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )
    result = command.execute()

    assert captured["update"] == ("note-1", "Heading<br>Body", "@todo", "token")
    assert captured["undo"] is not None
    assert captured["undo"][1]["before_tags"] == "@todo @bold"
    assert captured["undo"][1]["after_tags"] == "@todo"
    assert result == {"status": "updated", "updateUUID": "uuid-unformatted"}


def test_cmd_unformat_content_removes_scoped_style_tags_and_content_delimiters(
    monkeypatch,
) -> None:
    record = _Record(
        id="note-1",
        content="this {{word}} is <strong>red</strong>",
        tags="foo {{@red}} bar",
    )
    monkeypatch.setattr(unformat_module, "store", _FakeStore(record))

    captured = {"update": None}

    def _fake_apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
        captured["update"] = (note_id, content, tags, token)

    monkeypatch.setattr(unformat_module, "apply_update_content", _fake_apply_update_content)
    monkeypatch.setattr(unformat_module, "generate_new_uuid", lambda: "uuid-unformatted")
    monkeypatch.setattr("app.services.undo_state.record_update", lambda *args, **kwargs: None)

    command = unformat_module.CmdUnformatContent(
        note_id="note-1",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )

    result = command.execute()

    assert captured["update"] == ("note-1", "this word is red", "foo bar", "token")
    assert result == {"status": "updated", "updateUUID": "uuid-unformatted"}


def test_cmd_unformat_content_preserves_scope_used_by_non_formatting_tag(monkeypatch) -> None:
    record = _Record(
        id="note-1",
        content="{{word}}",
        tags="{{@red}} {{project}}",
    )
    monkeypatch.setattr(unformat_module, "store", _FakeStore(record))

    captured = {"update": None}

    def _fake_apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
        captured["update"] = (note_id, content, tags, token)

    monkeypatch.setattr(unformat_module, "apply_update_content", _fake_apply_update_content)
    monkeypatch.setattr(unformat_module, "generate_new_uuid", lambda: "uuid-unformatted")
    monkeypatch.setattr("app.services.undo_state.record_update", lambda *args, **kwargs: None)

    command = unformat_module.CmdUnformatContent(
        note_id="note-1",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )

    command.execute()

    assert captured["update"] == ("note-1", "{{word}}", "{{project}}", "token")


def test_cmd_unformat_content_updates_when_only_style_tags_change(monkeypatch) -> None:
    record = _Record(
        id="note-1",
        content="Already plain",
        tags="@red @todo",
    )
    monkeypatch.setattr(unformat_module, "store", _FakeStore(record))

    captured = {"update": None}

    def _fake_apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
        captured["update"] = (note_id, content, tags, token)

    monkeypatch.setattr(unformat_module, "apply_update_content", _fake_apply_update_content)
    monkeypatch.setattr(unformat_module, "generate_new_uuid", lambda: "uuid-unformatted")
    monkeypatch.setattr("app.services.undo_state.record_update", lambda *args, **kwargs: None)

    command = unformat_module.CmdUnformatContent(
        note_id="note-1",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )

    result = command.execute()

    assert captured["update"] == ("note-1", "Already plain", "@todo", "token")
    assert result == {"status": "updated", "updateUUID": "uuid-unformatted"}


def test_cmd_unformat_content_noops_when_content_is_already_plain(monkeypatch) -> None:
    record = _Record(
        id="note-1",
        content="Already plain",
        tags="@todo",
    )
    monkeypatch.setattr(unformat_module, "store", _FakeStore(record))
    monkeypatch.setattr(unformat_module, "generate_new_uuid", lambda: "uuid-noop")

    command = unformat_module.CmdUnformatContent(
        note_id="note-1",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )
    result = command.execute()

    assert result == {"status": "noop", "updateUUID": "uuid-noop"}
