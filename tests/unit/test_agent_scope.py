from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.agent.scope import AgentScopeDescriptor
from app.services.agent.scope import ScopedSearchSnapshotFactory
from app.services.note_store import NoteRecord
from app.services.snapshot import ResolvedViewScope


class _FakeNotes:
    def __init__(self) -> None:
        timestamp = datetime(2026, 8, 29, tzinfo=timezone.utc)
        self.records = {
            "root": NoteRecord(
                id="root",
                parent_id=None,
                prev_id=None,
                next_id=None,
                is_collapsed=False,
                content="<p>Root heading</p>",
                tags="project-foo",
                tag_terms=frozenset({"project-foo"}),
                non_meta_tag_terms=frozenset({"project-foo"}),
                created_at=timestamp,
                updated_at=timestamp,
            ),
            "match": NoteRecord(
                id="match",
                parent_id="root",
                prev_id=None,
                next_id="gray",
                is_collapsed=False,
                content="<p>lorem ipsum evidence</p>",
                tags="rare-tag useful-tag",
                tag_terms=frozenset({"useful-tag", "rare-tag"}),
                non_meta_tag_terms=frozenset({"useful-tag", "rare-tag"}),
                created_at=timestamp,
                updated_at=timestamp,
            ),
            "gray": NoteRecord(
                id="gray",
                parent_id="root",
                prev_id="match",
                next_id="secret",
                is_collapsed=False,
                content="<p>gray bar text</p>",
                tags="gray-exclusive",
                tag_terms=frozenset({"gray-exclusive"}),
                non_meta_tag_terms=frozenset({"gray-exclusive"}),
                created_at=timestamp,
                updated_at=timestamp,
            ),
            "secret": NoteRecord(
                id="secret",
                parent_id="root",
                prev_id="gray",
                next_id=None,
                is_collapsed=False,
                content="<p>credential value</p>",
                tags="@password secret-exclusive",
                tag_terms=frozenset({"@password", "secret-exclusive"}),
                non_meta_tag_terms=frozenset({"secret-exclusive"}),
                created_at=timestamp,
                updated_at=timestamp,
            ),
        }
        self.children = {
            "": ["root"],
            "root": ["match", "gray", "secret"],
            "match": [],
            "gray": [],
            "secret": [],
        }

    def get_note(self, note_id: str) -> NoteRecord:
        return self.records[note_id]

    def get_children(self, parent_id: str | None) -> list[str]:
        key = ""
        if parent_id is not None:
            key = parent_id
        return list(self.children[key])

    def has_note(self, note_id: str) -> bool:
        return note_id in self.records

    def list_note_ids(self) -> list[str]:
        return list(self.records)


def _descriptor() -> AgentScopeDescriptor:
    return AgentScopeDescriptor(
        scope_kind="search",
        active_tab_id="tab-1",
        search_query="useful-tag",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="useful-tag",
    )


def test_scope_descriptor_requires_all_flat_fields() -> None:
    payload = _descriptor().model_dump()
    del payload["active_tab_id"]

    with pytest.raises(ValidationError):
        AgentScopeDescriptor.model_validate(payload)


def test_scope_descriptor_rejects_all_notes_with_search_text() -> None:
    payload = _descriptor().model_dump()
    payload["scope_kind"] = "all_notes"

    with pytest.raises(ValidationError, match="all_notes requires empty search_query"):
        AgentScopeDescriptor.model_validate(payload)


def test_frozen_scope_uses_matches_not_render_only_ancestors_or_gray_bars() -> None:
    resolved = ResolvedViewScope(
        filter_active=True,
        allowed_note_ids=frozenset({"root", "match"}),
        matched_note_ids=frozenset({"match"}),
        ordered_root_ids=("root",),
        total_root_count=1,
    )
    factory = ScopedSearchSnapshotFactory(
        notes=_FakeNotes(),
        view_scope_resolver=lambda **_arguments: resolved,
    )

    snapshot = factory.freeze(
        descriptor=_descriptor(),
        authoritative_search_query="useful-tag",
        authoritative_sort_mode="normal",
        authoritative_date_filter={},
        run_id="run-1",
        session_key="session-1",
    )

    assert snapshot.ordered_note_ids == ("match",)
    assert set(snapshot.notes_by_id) == {"match"}
    assert tuple(snapshot.tree_nodes_by_id) == ("root", "match")
    assert snapshot.tree_nodes_by_id["root"].child_ids == ("match",)
    assert snapshot.notes_by_id["match"].explicit_tag_terms == (
        "rare-tag",
        "useful-tag",
    )


def test_frozen_scope_excludes_protected_notes_and_their_tags() -> None:
    resolved = ResolvedViewScope(
        filter_active=False,
        allowed_note_ids=frozenset({"root", "match", "gray", "secret"}),
        matched_note_ids=frozenset({"root", "match", "gray", "secret"}),
        ordered_root_ids=("root",),
        total_root_count=1,
    )
    descriptor = _descriptor().model_copy(
        update={"scope_kind": "all_notes", "search_query": "", "label": "All notes"}
    )
    factory = ScopedSearchSnapshotFactory(
        notes=_FakeNotes(),
        view_scope_resolver=lambda **_arguments: resolved,
    )

    snapshot = factory.freeze(
        descriptor=descriptor,
        authoritative_search_query="",
        authoritative_sort_mode="normal",
        authoritative_date_filter={},
        run_id="run-1",
        session_key="session-1",
    )

    assert "secret" not in snapshot.notes_by_id
    assert snapshot.ordered_note_ids == ("root", "match", "gray")


def test_frozen_scope_rejects_stale_client_view_state() -> None:
    factory = ScopedSearchSnapshotFactory(
        notes=_FakeNotes(),
        view_scope_resolver=lambda **_arguments: pytest.fail("resolver must not run"),
    )

    with pytest.raises(ValueError, match="search query changed before Send"):
        factory.freeze(
            descriptor=_descriptor(),
            authoritative_search_query="different-tag",
            authoritative_sort_mode="normal",
            authoritative_date_filter={},
            run_id="run-1",
            session_key="session-1",
        )


def test_scope_descriptor_rejects_spoofed_label() -> None:
    payload = _descriptor().model_dump()
    payload["label"] = "Something else"

    with pytest.raises(ValidationError, match="label must equal search_query"):
        AgentScopeDescriptor.model_validate(payload)
