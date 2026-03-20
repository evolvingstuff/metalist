from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.tag_suggestions as tag_suggestions_module
from app.services.search_index import SearchIndex
from app.services.search_index import SearchRecord
from app.services.search_index import extract_tags_for_search


class _EmptyOntology:
    is_empty = True


def _build_index(tag_rows: list[tuple[str, str]]) -> SearchIndex:
    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id=note_id,
                content_text="",
                tags=tags,
                tag_terms=extract_tags_for_search(tags),
            )
            for note_id, tags in tag_rows
        ],
        progress_update=lambda _processed: None,
        progress_interval=1000,
    )
    return index


def test_search_completion_matches_connector_separated_segments() -> None:
    index = _build_index(
        [
            ("n1", "workspaces databricks-workspaces databricks.workspaces databricks_workspaces"),
        ]
    )

    suggestions = index.suggest_tag_completions(query="wor", limit=20)

    assert "workspaces" in suggestions
    assert "databricks-workspaces" in suggestions
    assert "databricks.workspaces" in suggestions
    assert "databricks_workspaces" in suggestions
    assert index.suggest_tag_completions(query="orksp", limit=20) == []


def test_tag_suggestions_promote_specific_multi_segment_content_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "databricks"),
            ("n2", "workspaces"),
            ("n3", "databricks-workspaces"),
        ]
    )

    monkeypatch.setattr(
        tag_suggestions_module,
        "note_store",
        SimpleNamespace(get_inherited_non_meta_tag_terms=lambda _note_id: frozenset()),
    )
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=[],
        prefix="",
        content_html="<p>blah blah databricks workspaces blah blah</p>",
    )

    assert suggestions[:3] == ["databricks-workspaces", "databricks", "workspaces"]


def test_tag_suggestions_include_segment_literal_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "workspaces"),
            ("n2", "databricks-workspaces"),
        ]
    )

    monkeypatch.setattr(
        tag_suggestions_module,
        "note_store",
        SimpleNamespace(get_inherited_non_meta_tag_terms=lambda _note_id: frozenset()),
    )
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=[],
        prefix="wor",
        content_html="<p>blah blah workspaces blah blah</p>",
    )

    assert suggestions[:2] == ["workspaces", "databricks-workspaces"]
    assert tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=[],
        prefix="orksp",
        content_html="<p>blah blah workspaces blah blah</p>",
    ) == []


def test_tag_suggestions_promote_content_matches_wrapped_in_punctuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "databricks"),
            ("n2", "notes"),
            ("n3", "github"),
        ]
    )

    monkeypatch.setattr(
        tag_suggestions_module,
        "note_store",
        SimpleNamespace(get_inherited_non_meta_tag_terms=lambda _note_id: frozenset()),
    )
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=[],
        prefix="",
        content_html="<p>Team Lime (github?)</p>",
    )

    assert suggestions[0] == "github"


def test_tag_suggestions_collapse_case_equivalent_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "Databricks"),
            ("n2", "databricks"),
            ("n3", "delta"),
        ]
    )

    monkeypatch.setattr(
        tag_suggestions_module,
        "note_store",
        SimpleNamespace(get_inherited_non_meta_tag_terms=lambda _note_id: frozenset()),
    )
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=[],
        prefix="d",
        content_html="<p>databricks delta</p>",
    )

    assert "Databricks" not in suggestions
    assert suggestions.count("databricks") == 1
    assert suggestions[:2] == ["databricks", "delta"]
