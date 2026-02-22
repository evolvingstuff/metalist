from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Dict
from typing import FrozenSet
from typing import List
from typing import Optional
from typing import Set

import pytest

from app.mcp.errors import NoteNotFoundError
from app.mcp.errors import VaultNotReadyError
from app.mcp.read_service import ReadService
import app.mcp.read_service as read_service_module


@dataclass(frozen=True)
class _FakeNoteRecord:
    id: str
    parent_id: Optional[str]
    prev_id: Optional[str]
    next_id: Optional[str]
    is_collapsed: bool
    content: str
    tags: str
    tag_terms: FrozenSet[str]
    non_meta_tag_terms: FrozenSet[str]
    created_at: datetime | None
    updated_at: datetime | None


class _FakeNoteStore:
    def __init__(
        self,
        *,
        loaded: bool,
        records: Dict[str, _FakeNoteRecord],
        children_by_parent: Dict[Optional[str], List[str]],
        inherited_non_meta_by_note: Dict[str, FrozenSet[str]],
    ) -> None:
        self.loaded = loaded
        self._records = records
        self._children_by_parent = children_by_parent
        self._inherited_non_meta_by_note = inherited_non_meta_by_note

    def has_note(self, note_id: str) -> bool:
        return note_id in self._records

    def list_note_ids(self) -> List[str]:
        return list(self._records.keys())

    def get_note(self, note_id: str) -> _FakeNoteRecord:
        if note_id not in self._records:
            raise KeyError(f"Missing fake note: {note_id}")
        return self._records[note_id]

    def get_children(self, parent_id: Optional[str]) -> List[str]:
        if parent_id not in self._children_by_parent:
            return []
        return list(self._children_by_parent[parent_id])

    def get_inherited_non_meta_tag_terms(self, note_id: str) -> FrozenSet[str]:
        if note_id not in self._records:
            raise KeyError(f"Missing fake note: {note_id}")
        if note_id not in self._inherited_non_meta_by_note:
            return frozenset()
        return self._inherited_non_meta_by_note[note_id]


class _FakeOntology:
    is_empty = False

    def infer_implication_only(self, *, base_tags: FrozenSet[str]) -> FrozenSet[str]:
        terms = set(base_tags)
        if "project" in base_tags:
            terms.add("focus")
        return frozenset(terms)

    def infer_effective_tags(self, *, base_tags: FrozenSet[str], plaintext: str) -> FrozenSet[str]:
        terms = set(self.infer_implication_only(base_tags=base_tags))
        if "TODO" in plaintext:
            terms.add("todo")
        return frozenset(terms)


class _FakeSearchIndex:
    def __init__(
        self,
        *,
        frequencies: Dict[str, int],
        query_results: Dict[str, Set[str]],
    ) -> None:
        self._frequencies = frequencies
        self._query_results = query_results
        self.last_query: str | None = None

    def list_tag_frequencies(self) -> Dict[str, int]:
        return dict(self._frequencies)

    def query_note_ids(self, search: str) -> Set[str]:
        self.last_query = search
        if search not in self._query_results:
            return set()
        return set(self._query_results[search])


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    loaded: bool,
) -> _FakeSearchIndex:
    now = datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc)
    records = {
        "root": _FakeNoteRecord(
            id="root",
            parent_id=None,
            prev_id=None,
            next_id="sibling",
            is_collapsed=False,
            content="<p>Root text</p>",
            tags="project @blue",
            tag_terms=frozenset({"project", "@blue"}),
            non_meta_tag_terms=frozenset({"project"}),
            created_at=now,
            updated_at=now,
        ),
        "child": _FakeNoteRecord(
            id="child",
            parent_id="root",
            prev_id=None,
            next_id=None,
            is_collapsed=False,
            content="<p>TODO child action</p>",
            tags="task",
            tag_terms=frozenset({"task"}),
            non_meta_tag_terms=frozenset({"task"}),
            created_at=now,
            updated_at=now,
        ),
        "sibling": _FakeNoteRecord(
            id="sibling",
            parent_id=None,
            prev_id="root",
            next_id=None,
            is_collapsed=False,
            content="<p>Sibling note</p>",
            tags="done",
            tag_terms=frozenset({"done"}),
            non_meta_tag_terms=frozenset({"done"}),
            created_at=now,
            updated_at=now,
        ),
    }
    children_by_parent: Dict[Optional[str], List[str]] = {
        None: ["root", "sibling"],
        "root": ["child"],
        "child": [],
        "sibling": [],
    }
    inherited_non_meta_by_note = {
        "root": frozenset(),
        "child": frozenset({"project"}),
        "sibling": frozenset(),
    }

    fake_store = _FakeNoteStore(
        loaded=loaded,
        records=records,
        children_by_parent=children_by_parent,
        inherited_non_meta_by_note=inherited_non_meta_by_note,
    )
    fake_search_index = _FakeSearchIndex(
        frequencies={"todo": 8, "project": 5, "focus": 4, "done": 2},
        query_results={
            "alpha project -done": {"root", "child"},
            "project": {"root", "child"},
        },
    )

    monkeypatch.setattr(read_service_module, "note_store", fake_store)
    monkeypatch.setattr(read_service_module, "search_index", fake_search_index)
    monkeypatch.setattr(read_service_module, "get_ontology", lambda: _FakeOntology())

    return fake_search_index


def test_get_note_returns_subtree_and_tag_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, loaded=True)
    service = ReadService()

    payload = service.get_note(note_id="root")

    assert payload["note"]["id"] == "root"
    assert payload["note"]["created_at"] == "2026-02-15T12:00:00+00:00"
    assert payload["tags"]["raw_tag_string"] == "project @blue"
    assert payload["tags"]["tag_terms"] == ["@blue", "project"]
    assert payload["tags"]["implied_tag_terms"] == ["focus"]
    assert payload["tags"]["effective_tag_terms"] == ["@blue", "focus", "project"]

    children = payload["children"]
    assert len(children) == 1
    child = children[0]
    assert child["note"]["id"] == "child"
    assert child["tags"]["tag_terms"] == ["task"]
    assert child["tags"]["implied_tag_terms"] == ["focus"]
    assert child["tags"]["effective_tag_terms"] == ["focus", "project", "task", "todo"]
    assert child["children"] == []


def test_get_note_missing_note_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, loaded=True)
    service = ReadService()

    with pytest.raises(NoteNotFoundError, match="Note not found"):
        service.get_note(note_id="missing")


def test_readiness_guard_blocks_locked_or_unhydrated_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, loaded=False)
    service = ReadService()

    status = service.health_check()
    assert status["ready"] is False

    with pytest.raises(VaultNotReadyError, match="Vault locked or not hydrated"):
        service.get_note(note_id="root")


def test_count_notes_returns_total_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, loaded=True)
    service = ReadService()

    payload = service.count_notes()

    assert payload["total_notes"] == 3


def test_list_children_returns_full_note_window(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, loaded=True)
    service = ReadService()

    payload = service.list_children(parent_id=None)

    assert payload["total_children"] == 2
    assert payload["returned_count"] == 2
    assert payload["has_more"] is False
    first_child = payload["children"][0]
    assert first_child["note"]["id"] == "root"
    assert first_child["tags"]["raw_tag_string"] == "project @blue"
    assert first_child["child_count"] == 1


def test_list_tags_applies_prefix_limit_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, loaded=True)
    service = ReadService()

    filtered = service.list_tags(prefix="to", limit=5, mode="effective")
    assert filtered["total_matches"] == 1
    assert filtered["returned_count"] == 1
    assert filtered["tags"] == [{"tag": "todo", "count": 8}]
    assert filtered["mode"] == "effective"

    top_two = service.list_tags(prefix="", limit=2, mode="effective")
    assert top_two["total_matches"] == 4
    assert top_two["returned_count"] == 2
    assert top_two["tags"] == [
        {"tag": "todo", "count": 8},
        {"tag": "project", "count": 5},
    ]
    assert top_two["mode"] == "effective"

    raw_top = service.list_tags(prefix="", limit=5, mode="raw")
    assert raw_top["total_matches"] == 3
    assert raw_top["returned_count"] == 3
    assert raw_top["tags"] == [
        {"tag": "done", "count": 1},
        {"tag": "project", "count": 1},
        {"tag": "task", "count": 1},
    ]
    assert raw_top["mode"] == "raw"


def test_search_notes_returns_total_and_returned_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_index = _install_fakes(monkeypatch, loaded=True)
    service = ReadService()

    payload = service.search_notes(
        query="alpha",
        required_tags=["project"],
        forbidden_tags=["done"],
        limit=1,
        offset=1,
    )

    assert fake_index.last_query == "alpha project -done"
    assert payload["total_matches"] == 2
    assert payload["returned_count"] == 1
    assert payload["results"][0]["note_id"] == "child"


def test_search_notes_supports_all_notes_when_query_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, loaded=True)
    service = ReadService()

    payload = service.search_notes(
        query="",
        required_tags=[],
        forbidden_tags=[],
        limit=2,
        offset=1,
    )

    assert payload["resolved_query"] == ""
    assert payload["total_matches"] == 3
    assert payload["returned_count"] == 2
    assert [entry["note_id"] for entry in payload["results"]] == ["child", "sibling"]
