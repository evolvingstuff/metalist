from __future__ import annotations

from dataclasses import dataclass

import app.usecases.join_next_sibling as join_module


@dataclass
class _Record:
    id: str
    parent_id: str | None
    content: str
    tags: str


class _FakeStore:
    def __init__(self, records: dict[str, _Record], children_by_parent: dict[str | None, list[str]]) -> None:
        self._records = records
        self._children_by_parent = children_by_parent

    def get(self, note_id: str) -> _Record:
        return self._records[note_id]

    def children(self, parent_id: str | None) -> list[str]:
        if parent_id in self._children_by_parent:
            return list(self._children_by_parent[parent_id])
        return []


def test_merge_helpers_join_with_line_break_and_space() -> None:
    merged_content = join_module._merge_note_content_html("  foo  ", " bar ")
    merged_tags = join_module._merge_note_tags(" alpha ", " beta ")

    assert merged_content == "foo<br>bar"
    assert merged_tags == "alpha beta"


def test_merge_note_tags_dedupes_case_insensitive_preserving_order() -> None:
    merged_tags = join_module._merge_note_tags("Alpha beta", "beta BETA gamma alpha")
    assert merged_tags == "Alpha beta gamma"


def test_merge_helpers_avoids_extra_break_between_block_elements() -> None:
    merged_content = join_module._merge_note_content_html(
        "<div>foo</div><div>bar</div>",
        "<div>baz</div><div>qux</div>",
    )
    assert merged_content == "<div>foo</div><div>bar</div><div>baz</div><div>qux</div>"


def test_join_next_sibling_noop_when_no_next_sibling(monkeypatch) -> None:
    records = {
        "a": _Record(id="a", parent_id=None, content="foo", tags="alpha"),
    }
    children_by_parent = {
        None: ["a"],
    }
    fake_store = _FakeStore(records=records, children_by_parent=children_by_parent)
    monkeypatch.setattr(join_module, "store", fake_store)

    command = join_module.CmdJoinNextSibling(
        note_id="a",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )
    result = command.execute()

    assert result == {"status": "noop", "id": "a"}


def test_join_next_sibling_noop_when_next_sibling_has_children(monkeypatch) -> None:
    records = {
        "a": _Record(id="a", parent_id=None, content="foo", tags="alpha"),
        "b": _Record(id="b", parent_id=None, content="bar", tags="beta"),
        "child": _Record(id="child", parent_id="b", content="nested", tags="gamma"),
    }
    children_by_parent = {
        None: ["a", "b"],
        "b": ["child"],
    }
    fake_store = _FakeStore(records=records, children_by_parent=children_by_parent)
    monkeypatch.setattr(join_module, "store", fake_store)

    command = join_module.CmdJoinNextSibling(
        note_id="a",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )
    result = command.execute()

    assert result == {"status": "noop", "id": "a"}


def test_join_next_sibling_merges_and_records_undo(monkeypatch) -> None:
    records = {
        "a": _Record(id="a", parent_id=None, content="foo", tags="alpha beta"),
        "b": _Record(id="b", parent_id=None, content="bar", tags="beta gamma"),
    }
    children_by_parent = {
        None: ["a", "b"],
        "b": [],
    }
    fake_store = _FakeStore(records=records, children_by_parent=children_by_parent)
    monkeypatch.setattr(join_module, "store", fake_store)

    captured = {
        "updated": None,
        "deleted": None,
        "undo": None,
    }

    def _fake_snapshot(note_id: str):
        return [records[note_id]]

    def _fake_apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
        captured["updated"] = (note_id, content, tags, token)

    def _fake_apply_delete_subtree(note_id: str) -> None:
        captured["deleted"] = note_id

    def _fake_record_join_next(*args, **kwargs) -> None:
        captured["undo"] = (args, kwargs)

    monkeypatch.setattr(join_module, "_snapshot_subtree", _fake_snapshot)
    monkeypatch.setattr(join_module, "apply_update_content", _fake_apply_update_content)
    monkeypatch.setattr(join_module, "apply_delete_subtree", _fake_apply_delete_subtree)
    monkeypatch.setattr(join_module, "record_join_next", _fake_record_join_next)
    monkeypatch.setattr(join_module, "generate_new_uuid", lambda: "uuid-joined")

    command = join_module.CmdJoinNextSibling(
        note_id="a",
        token="token",
        client_id="client",
        undo_context="tab:1|search:|epoch:0",
        viewport={"scrollY": 0, "scrollAnchor": None},
    )
    result = command.execute()

    assert captured["updated"] == ("a", "foo<br>bar", "alpha beta gamma", "token")
    assert captured["deleted"] == "b"
    assert captured["undo"] is not None
    assert result == {
        "status": "joined",
        "id": "a",
        "removedId": "b",
        "updateUUID": "uuid-joined",
    }
