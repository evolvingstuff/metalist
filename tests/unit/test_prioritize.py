from __future__ import annotations

from dataclasses import dataclass

import pytest

import app.api.routes.notes as notes_route
import app.usecases.prioritize as prioritize_module
from app.services.snapshot import SearchScope
from app.usecases.prioritize import CmdPrioritize
from app.usecases.prioritize import list_prioritize_tag_suggestions


@dataclass
class _FakeRecord:
    id: str
    parent_id: str | None
    tags: str


class _FakeStore:
    def __init__(self, root_ids: list[str], *, tags_by_note_id: dict[str, str]) -> None:
        if not isinstance(tags_by_note_id, dict):
            raise TypeError("tags_by_note_id must be a dict")
        self.root_ids = list(root_ids)
        self._records = {}
        for note_id in root_ids:
            tags = ""
            if note_id in tags_by_note_id:
                tags = tags_by_note_id[note_id]
            self._records[note_id] = _FakeRecord(id=note_id, parent_id=None, tags=tags)

    def get(self, note_id: str) -> _FakeRecord:
        return self._records[note_id]

    def children(self, parent_id: str | None) -> list[str]:
        if parent_id is not None:
            return []
        return list(self.root_ids)


def _install_root_move_fakes(
    *,
    monkeypatch: pytest.MonkeyPatch,
    fake_store: _FakeStore,
    module,
) -> list[tuple[str, str | None, str | None, str | None]]:
    monkeypatch.setattr(module, "store", fake_store)

    def fake_neighbors(note_id: str) -> tuple[str | None, str | None, str | None]:
        idx = fake_store.root_ids.index(note_id)
        prev_id = None
        if idx > 0:
            prev_id = fake_store.root_ids[idx - 1]
        next_id = None
        if idx + 1 < len(fake_store.root_ids):
            next_id = fake_store.root_ids[idx + 1]
        return None, prev_id, next_id

    move_calls: list[tuple[str, str | None, str | None, str | None]] = []

    def fake_apply_move(
        note_id: str,
        new_parent_id: str | None,
        prev_id: str | None,
        next_id: str | None,
    ) -> None:
        assert new_parent_id is None
        root_ids = fake_store.root_ids
        root_ids.remove(note_id)
        if prev_id is None:
            insert_index = 0
        else:
            insert_index = root_ids.index(prev_id) + 1
        if next_id is not None:
            assert insert_index == root_ids.index(next_id)
        root_ids.insert(insert_index, note_id)
        move_calls.append((note_id, new_parent_id, prev_id, next_id))

    monkeypatch.setattr(module, "_neighbors", fake_neighbors)
    monkeypatch.setattr(module, "apply_move", fake_apply_move)
    monkeypatch.setattr(module, "_assert_neighbors", lambda *args: None)
    return move_calls


def test_prioritize_front_reorders_visible_roots_and_records_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeStore(
        ["hidden-root", "root-b", "root-c", "root-d", "after-root"],
        tags_by_note_id={},
    )
    move_calls = _install_root_move_fakes(
        monkeypatch=monkeypatch,
        fake_store=fake_store,
        module=prioritize_module,
    )

    monkeypatch.setattr(
        prioritize_module,
        "resolve_search_scope",
        lambda *, search, editing_note_id, sort_mode, ordered_root_ids: SearchScope(
            search_active=True,
            allowed_note_ids={"root-b", "root-c", "root-d"},
            search_root_ids_ordered=["root-b", "root-c", "root-d"],
            search_root_count_total=3,
        ),
    )
    monkeypatch.setattr(
        prioritize_module.search_index,
        "query_note_ids",
        lambda query: {"root-d"} if query == "foo" else set(),
    )

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        prioritize_module,
        "record_move_batch",
        lambda client_id, undo_context, *, move_ops, viewport: captured.update(
            client_id=client_id,
            undo_context=undo_context,
            move_ops=move_ops,
            viewport=viewport,
        ),
    )
    monkeypatch.setattr(prioritize_module, "generate_new_uuid", lambda: "uuid-prioritize-front")

    result = CmdPrioritize(
        tag="foo",
        direction="front",
        search_query="journal",
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert fake_store.root_ids == ["hidden-root", "root-d", "root-b", "root-c", "after-root"]
    assert move_calls == [("root-d", None, "hidden-root", "root-b")]
    assert captured["client_id"] == "client-1"
    assert captured["undo_context"] == "undo-1"
    assert captured["viewport"] == {"scrollY": 0}
    assert captured["move_ops"] == [
        {
            "note_id": "root-d",
            "before_parent": None,
            "before_prev": "root-c",
            "before_next": "after-root",
            "before_tags": "",
            "after_parent": None,
            "after_prev": "hidden-root",
            "after_next": "root-b",
            "after_tags": "",
        }
    ]
    assert result == {
        "status": "moved",
        "movedRootCount": 1,
        "matchedRootCount": 1,
        "visibleRootCount": 3,
        "updateUUID": "uuid-prioritize-front",
    }


def test_prioritize_back_keeps_match_and_non_match_order_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeStore(
        ["root-a", "root-b", "root-c", "root-d", "root-e", "root-f"],
        tags_by_note_id={},
    )
    _install_root_move_fakes(
        monkeypatch=monkeypatch,
        fake_store=fake_store,
        module=prioritize_module,
    )

    monkeypatch.setattr(
        prioritize_module,
        "resolve_search_scope",
        lambda *, search, editing_note_id, sort_mode, ordered_root_ids: SearchScope(
            search_active=True,
            allowed_note_ids={"root-b", "root-c", "root-d", "root-e"},
            search_root_ids_ordered=["root-b", "root-c", "root-d", "root-e"],
            search_root_count_total=4,
        ),
    )
    monkeypatch.setattr(
        prioritize_module.search_index,
        "query_note_ids",
        lambda query: {"root-b", "root-d"} if query == "foo" else set(),
    )
    monkeypatch.setattr(prioritize_module, "record_move_batch", lambda *args, **kwargs: None)
    monkeypatch.setattr(prioritize_module, "generate_new_uuid", lambda: "uuid-prioritize-back")

    result = CmdPrioritize(
        tag="foo",
        direction="back",
        search_query="journal",
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert fake_store.root_ids == ["root-a", "root-c", "root-e", "root-b", "root-d", "root-f"]
    assert result == {
        "status": "moved",
        "movedRootCount": 2,
        "matchedRootCount": 2,
        "visibleRootCount": 4,
        "updateUUID": "uuid-prioritize-back",
    }


def test_prioritize_noops_when_no_visible_roots_match(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _FakeStore(["root-a", "root-b", "root-c"], tags_by_note_id={})
    _install_root_move_fakes(
        monkeypatch=monkeypatch,
        fake_store=fake_store,
        module=prioritize_module,
    )
    monkeypatch.setattr(
        prioritize_module,
        "resolve_search_scope",
        lambda *, search, editing_note_id, sort_mode, ordered_root_ids: SearchScope(
            search_active=True,
            allowed_note_ids={"root-a", "root-b"},
            search_root_ids_ordered=["root-a", "root-b"],
            search_root_count_total=2,
        ),
    )
    monkeypatch.setattr(prioritize_module.search_index, "query_note_ids", lambda query: set())

    called = {"recorded": False}
    monkeypatch.setattr(
        prioritize_module,
        "record_move_batch",
        lambda *args, **kwargs: called.update(recorded=True),
    )

    result = CmdPrioritize(
        tag="foo",
        direction="front",
        search_query="journal",
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert fake_store.root_ids == ["root-a", "root-b", "root-c"]
    assert called["recorded"] is False
    assert result == {
        "status": "noop",
        "reason": "no_matches",
        "matchedRootCount": 0,
        "visibleRootCount": 2,
    }


def test_prioritize_noops_when_order_is_already_prioritized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeStore(
        ["root-a", "root-b", "root-d", "root-c", "root-e"],
        tags_by_note_id={},
    )
    _install_root_move_fakes(
        monkeypatch=monkeypatch,
        fake_store=fake_store,
        module=prioritize_module,
    )
    monkeypatch.setattr(
        prioritize_module,
        "resolve_search_scope",
        lambda *, search, editing_note_id, sort_mode, ordered_root_ids: SearchScope(
            search_active=True,
            allowed_note_ids={"root-b", "root-d", "root-c"},
            search_root_ids_ordered=["root-b", "root-d", "root-c"],
            search_root_count_total=3,
        ),
    )
    monkeypatch.setattr(
        prioritize_module.search_index,
        "query_note_ids",
        lambda query: {"root-b", "root-d"} if query == "foo" else set(),
    )

    called = {"recorded": False}
    monkeypatch.setattr(
        prioritize_module,
        "record_move_batch",
        lambda *args, **kwargs: called.update(recorded=True),
    )

    result = CmdPrioritize(
        tag="foo",
        direction="front",
        search_query="journal",
        client_id="client-1",
        undo_context="undo-1",
        viewport={"scrollY": 0},
    ).execute()

    assert fake_store.root_ids == ["root-a", "root-b", "root-d", "root-c", "root-e"]
    assert called["recorded"] is False
    assert result == {
        "status": "noop",
        "reason": "already_prioritized",
        "matchedRootCount": 2,
        "visibleRootCount": 3,
    }


def test_prioritize_rejects_invalid_tag() -> None:
    with pytest.raises(ValueError, match="single valid tag token"):
        CmdPrioritize(
            tag="bad tag",
            direction="front",
            search_query=None,
            client_id="client-1",
            undo_context="undo-1",
            viewport={"scrollY": 0},
        ).execute()


def test_list_prioritize_tag_suggestions_limits_to_visible_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeStore(
        ["hidden-root", "root-a", "root-b", "root-c"],
        tags_by_note_id={
            "hidden-root": "hidden",
            "root-a": "foo workspaces",
            "root-b": "Foo databricks-workspaces",
            "root-c": "bar",
        },
    )
    monkeypatch.setattr(prioritize_module, "store", fake_store)
    monkeypatch.setattr(
        prioritize_module,
        "resolve_search_scope",
        lambda *, search, editing_note_id, sort_mode, ordered_root_ids: SearchScope(
            search_active=True,
            allowed_note_ids={"root-a", "root-b", "root-c"},
            search_root_ids_ordered=["root-a", "root-b", "root-c"],
            search_root_count_total=3,
        ),
    )

    suggestions = list_prioritize_tag_suggestions(
        search_query="journal",
        query="",
        limit=10,
    )

    assert suggestions == ["foo", "bar", "databricks-workspaces", "workspaces"]


def test_list_prioritize_tag_suggestions_filters_by_segment_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakeStore(
        ["root-a", "root-b", "root-c"],
        tags_by_note_id={
            "root-a": "workspaces",
            "root-b": "databricks-workspaces",
            "root-c": "personal",
        },
    )
    monkeypatch.setattr(prioritize_module, "store", fake_store)
    monkeypatch.setattr(
        prioritize_module,
        "resolve_search_scope",
        lambda *, search, editing_note_id, sort_mode, ordered_root_ids: SearchScope(
            search_active=True,
            allowed_note_ids={"root-a", "root-b", "root-c"},
            search_root_ids_ordered=["root-a", "root-b", "root-c"],
            search_root_count_total=3,
        ),
    )

    suggestions = list_prioritize_tag_suggestions(
        search_query="journal",
        query="wor",
        limit=10,
    )

    assert suggestions == ["workspaces", "databricks-workspaces"]


def test_prioritize_route_normalizes_empty_search_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notes_route, "_require_viewport", lambda body: {"scrollY": 0})

    captured: dict[str, object] = {}

    class _FakeCmdPrioritize:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def execute(self) -> dict[str, str]:
            return {"status": "moved"}

    monkeypatch.setattr(notes_route, "CmdPrioritize", _FakeCmdPrioritize)

    result = notes_route.prioritize_in_view_endpoint(
        {
            "tag": "foo",
            "direction": "front",
            "search_query": "",
            "clientId": "client-1",
            "undoContext": "undo-1",
            "viewport": {"scrollY": 0},
        }
    )

    assert captured == {
        "tag": "foo",
        "direction": "front",
        "search_query": None,
        "client_id": "client-1",
        "undo_context": "undo-1",
        "viewport": {"scrollY": 0},
    }
    assert result == {"status": "moved"}


def test_prioritize_tag_suggestions_route_normalizes_empty_search_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        notes_route,
        "list_prioritize_tag_suggestions",
        lambda *, search_query, query, limit: captured.update(
            search_query=search_query,
            query=query,
            limit=limit,
        ) or ["foo"],
    )

    result = notes_route.prioritize_tag_suggestions(
        {
            "query": "fo",
            "search_query": "",
        }
    )

    assert captured == {
        "search_query": None,
        "query": "fo",
        "limit": 20,
    }
    assert result == {"suggestions": ["foo"]}


def test_search_suggestions_route_uses_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(notes_route, "MAX_SEARCH_SUGGESTIONS", 7)
    monkeypatch.setattr(
        notes_route.search_index,
        "suggest_tag_completions",
        lambda *, query, limit: captured.update(query=query, limit=limit) or ["foo"],
    )

    result = notes_route.search_suggestions(None, {"query": "foo bar"})

    assert captured == {
        "query": "foo bar",
        "limit": 7,
    }
    assert result == {"suggestions": ["foo"]}


def test_prioritize_tag_suggestions_route_uses_configured_tag_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(notes_route, "MAX_TAG_SUGGESTIONS", 6)
    monkeypatch.setattr(
        notes_route,
        "list_prioritize_tag_suggestions",
        lambda *, search_query, query, limit: captured.update(
            search_query=search_query,
            query=query,
            limit=limit,
        ) or ["foo"],
    )

    result = notes_route.prioritize_tag_suggestions(
        {
            "query": "fo",
            "search_query": "active",
        }
    )

    assert captured == {
        "search_query": "active",
        "query": "fo",
        "limit": 6,
    }
    assert result == {"suggestions": ["foo"]}


def test_note_tag_suggestions_route_uses_configured_tag_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(notes_route, "MAX_TAG_SUGGESTIONS", 5)
    monkeypatch.setattr(notes_route, "_require_note_present", lambda note_id, *, context: None)
    monkeypatch.setattr(
        notes_route,
        "suggest_tags_for_note",
        lambda *, note_id, anchors, explicit_tags, prefix, content_html, limit: captured.update(
            note_id=note_id,
            anchors=anchors,
            explicit_tags=explicit_tags,
            prefix=prefix,
            content_html=content_html,
            limit=limit,
        ) or ["foo"],
    )

    result = notes_route.tag_suggestions(
        {
            "note_id": "note-1",
            "anchors": ["alpha"],
            "explicit_tags": ["alpha"],
            "prefix": "f",
            "content_html": "<p>foo</p>",
        }
    )

    assert captured == {
        "note_id": "note-1",
        "anchors": ["alpha"],
        "explicit_tags": ["alpha"],
        "prefix": "f",
        "content_html": "<p>foo</p>",
        "limit": 5,
    }
    assert result == {"suggestions": ["foo"]}
