from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.tag_suggestions as tag_suggestions_module
from app.services.search_index import SearchIndex
from app.services.search_index import SearchRecord
from app.services.search_index import extract_tags_for_search


class _EmptyOntology:
    is_empty = True


class _MatcherButNoImplicationOntology:
    is_empty = False

    def infer_implication_only(self, *, base_tags):
        return base_tags

    def infer_effective_tags(self, *, base_tags, plaintext):
        inferred = set(base_tags)
        if "sleep" in plaintext.casefold():
            inferred.add("sleep")
        return frozenset(inferred)


def _build_note_record(
    *,
    note_id: str,
    parent_id: str | None,
    content: str,
    tags: str,
) -> SimpleNamespace:
    tag_terms = extract_tags_for_search(tags)
    non_meta_tag_terms = frozenset(term for term in tag_terms if not term.startswith("@"))
    return SimpleNamespace(
        id=note_id,
        parent_id=parent_id,
        content=content,
        tag_terms=tag_terms,
        non_meta_tag_terms=non_meta_tag_terms,
    )


class _FakeHierarchyNoteStore:
    def __init__(
        self,
        *,
        records: list[SimpleNamespace],
        inherited_non_meta_by_note: dict[str, frozenset[str]],
    ) -> None:
        self._records = {record.id: record for record in records}
        self._children_by_parent: dict[str | None, list[str]] = {}
        for record in records:
            self._children_by_parent.setdefault(record.parent_id, []).append(record.id)
        self._inherited_non_meta_by_note = dict(inherited_non_meta_by_note)

    def get_inherited_non_meta_tag_terms(self, note_id: str) -> frozenset[str]:
        return self._inherited_non_meta_by_note.get(note_id, frozenset())

    def list_note_ids(self) -> list[str]:
        return list(self._records.keys())

    def has_note(self, note_id: str) -> bool:
        return note_id in self._records

    def get_note(self, note_id: str) -> SimpleNamespace:
        if note_id not in self._records:
            raise KeyError(note_id)
        return self._records[note_id]

    def get_children(self, parent_id: str | None) -> list[str]:
        return list(self._children_by_parent.get(parent_id, []))


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
        explicit_tags=[],
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
        explicit_tags=[],
        prefix="wor",
        content_html="<p>blah blah workspaces blah blah</p>",
    )

    assert suggestions[:2] == ["workspaces", "databricks-workspaces"]
    assert tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=[],
        explicit_tags=[],
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
        explicit_tags=[],
        prefix="",
        content_html="<p>Team Lime (github?)</p>",
    )

    assert suggestions[0] == "github"


def test_tag_suggestions_ignore_numeric_only_content_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "Hearts-of-Iron-4"),
            ("n2", "GPT-5.4"),
            ("n3", "alcohol"),
            ("n4", "alcohol"),
            ("n5", "alcohol"),
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
        explicit_tags=[],
        prefix="",
        content_html="<p>4</p>",
    )

    assert suggestions[0] == "alcohol"


def test_tag_suggestions_ignore_single_character_content_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "a-b-test"),
            ("n2", "alpha"),
            ("n3", "alpha"),
            ("n4", "alpha"),
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
        explicit_tags=[],
        prefix="",
        content_html="<p>a</p>",
    )

    assert suggestions[0] == "alpha"


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
        explicit_tags=[],
        prefix="d",
        content_html="<p>databricks delta</p>",
    )

    assert "Databricks" not in suggestions
    assert suggestions.count("databricks") == 1
    assert suggestions[:2] == ["databricks", "delta"]


def test_tag_suggestions_do_not_repeat_current_explicit_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "Pandoc"),
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
        explicit_tags=["Pandoc"],
        prefix="Pandoc",
        content_html="<p>experimenting with pandoc outputs</p>",
    )

    assert suggestions == []


def test_tag_suggestions_rank_meta_tags_by_frequency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "@todo alpha"),
            ("n2", "@todo beta"),
            ("n3", "@todo gamma"),
            ("n4", "@done delta"),
            ("n5", "@done epsilon"),
            ("n6", "@LaTeX zeta"),
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
        explicit_tags=[],
        prefix="@",
        content_html="<p></p>",
    )

    assert suggestions[:3] == ["@todo", "@done", "@LaTeX"]


def test_tag_suggestions_prefer_earlier_content_hits_when_scores_tie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "github"),
            ("n2", "project"),
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
        explicit_tags=[],
        prefix="",
        content_html="<p>My boss has a github project called Dex</p>",
    )

    assert suggestions[:2] == ["github", "project"]


def test_tag_suggestions_include_literal_content_hits_even_without_anchor_cooccurrence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "diagram veggie-peeler"),
            ("n2", "diagram project"),
            ("n3", "diagram projects"),
            ("n4", "LucidCharts"),
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
        anchors=["diagram"],
        explicit_tags=["diagram"],
        prefix="",
        content_html="<p>port diagram to LucidCharts?</p>",
    )

    assert suggestions[0] == "LucidCharts"
    assert suggestions[1:] == ["project", "projects", "veggie-peeler"]


def test_tag_suggestions_include_acronym_content_hits_even_without_anchor_cooccurrence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "LinuxVM databricks"),
            ("n2", "LinuxVM DBX"),
            ("n3", "AVD"),
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
        anchors=["LinuxVM"],
        explicit_tags=["LinuxVM"],
        prefix="",
        content_html=(
            "<p>why do we need the LinuxVM? Can I install enterprise codex directly on the "
            "AVD? can I do git pulls on the AVD?</p>"
        ),
    )

    assert suggestions[0] == "AVD"
    assert suggestions[1:] == ["databricks", "DBX"]


def test_tag_suggestions_include_inherited_context_in_cooccurrence_ranking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "journal projects ML3 productive"),
            ("n2", "journal projects ML3 search-recency"),
            ("n3", "journal salmon-nigiri-Ballard-Market"),
        ]
    )

    monkeypatch.setattr(
        tag_suggestions_module,
        "note_store",
        SimpleNamespace(
            get_inherited_non_meta_tag_terms=lambda _note_id: frozenset({"journal", "projects", "ML3"}),
        ),
    )
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=["@done"],
        explicit_tags=["@done"],
        prefix="",
        content_html="<p>switching my personal stuff over to ML3</p>",
    )

    assert suggestions[:3] == ["productive", "search-recency", "salmon-nigiri-Ballard-Market"]


def test_tag_suggestions_prioritize_exact_content_hit_over_global_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "productive"),
            ("n2", "salmon-nigiri-Ballard-Market"),
            ("n3", "smart-RAG"),
        ]
    )

    monkeypatch.setattr(
        tag_suggestions_module,
        "note_store",
        SimpleNamespace(
            get_inherited_non_meta_tag_terms=lambda _note_id: frozenset({"do-stuff"}),
        ),
    )
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="note-1",
        anchors=["@done"],
        explicit_tags=["@done"],
        prefix="",
        content_html="<p>productive</p>",
    )

    assert suggestions[0] == "productive"


def test_tag_suggestions_use_local_hierarchy_content_before_global_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "search-recency"),
            ("n2", "sorting-features"),
            ("n3", "salmon-nigiri-Ballard-Market"),
        ]
    )
    store = _FakeHierarchyNoteStore(
        records=[
            _build_note_record(note_id="journal", parent_id=None, content="journal", tags=""),
            _build_note_record(note_id="projects", parent_id="journal", content="projects", tags=""),
            _build_note_record(note_id="ml3", parent_id="projects", content="ML3", tags=""),
            _build_note_record(
                note_id="current",
                parent_id="ml3",
                content="switching my personal stuff over to ML3!",
                tags="",
            ),
            _build_note_record(note_id="sibling-1", parent_id="ml3", content="search recency", tags="search-recency"),
            _build_note_record(note_id="sibling-2", parent_id="ml3", content="sorting features", tags="sorting-features"),
            _build_note_record(
                note_id="elsewhere",
                parent_id="journal",
                content="ballard trip",
                tags="salmon-nigiri-Ballard-Market",
            ),
        ],
        inherited_non_meta_by_note={},
    )

    monkeypatch.setattr(tag_suggestions_module, "note_store", store)
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="current",
        anchors=["@done"],
        explicit_tags=["@done"],
        prefix="",
        content_html="<p>switching my personal stuff over to ML3!</p>",
    )

    assert suggestions[:3] == ["search-recency", "sorting-features", "salmon-nigiri-Ballard-Market"]


def test_tag_suggestions_prioritize_descendant_explicit_tag_for_current_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _build_index(
        [
            ("n1", "journal health"),
            ("n2", "journal health"),
            ("n3", "journal biology"),
            ("n4", "journal science"),
            ("n5", "journal sleep"),
        ]
    )
    store = _FakeHierarchyNoteStore(
        records=[
            _build_note_record(note_id="entry", parent_id=None, content="2026-04-19 Sun", tags="journal"),
            _build_note_record(note_id="sleep-note", parent_id="entry", content="sleep", tags="sleep"),
            _build_note_record(note_id="diet-note", parent_id="entry", content="diet", tags="diet"),
        ],
        inherited_non_meta_by_note={},
    )

    monkeypatch.setattr(tag_suggestions_module, "note_store", store)
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", index)

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="entry",
        anchors=["journal"],
        explicit_tags=["journal"],
        prefix="",
        content_html="<p>2026-04-19 Sun</p>",
    )

    assert suggestions[0] == "sleep"


def test_tag_suggestions_match_connector_segment_prefix_in_saved_note_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeHierarchyNoteStore(
        records=[
            _build_note_record(note_id="root", parent_id=None, content="root", tags=""),
            _build_note_record(note_id="n1", parent_id="root", content="alpha", tags="foo-bar-baz"),
            _build_note_record(note_id="n2", parent_id="root", content="beta", tags="foo-baz"),
        ],
        inherited_non_meta_by_note={},
    )

    monkeypatch.setattr(tag_suggestions_module, "note_store", store)
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", _build_index([]))

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="root",
        anchors=[],
        explicit_tags=[],
        prefix="bar",
        content_html="<p></p>",
    )

    assert suggestions[0] == "foo-bar-baz"


def test_tag_suggestions_break_local_ties_by_global_frequency_not_alphabetically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeHierarchyNoteStore(
        records=[
            _build_note_record(note_id="root", parent_id=None, content="root", tags=""),
            _build_note_record(note_id="current", parent_id="root", content="current", tags=""),
            _build_note_record(note_id="sibling-rare", parent_id="root", content="rare", tags="A-Programmer's-Introduction-to-Mathematics"),
            _build_note_record(note_id="sibling-common", parent_id="root", content="common", tags="search-recency"),
            _build_note_record(note_id="extra-1", parent_id=None, content="extra", tags="search-recency"),
            _build_note_record(note_id="extra-2", parent_id=None, content="extra", tags="search-recency"),
            _build_note_record(note_id="extra-3", parent_id=None, content="extra", tags="search-recency"),
        ],
        inherited_non_meta_by_note={},
    )

    monkeypatch.setattr(tag_suggestions_module, "note_store", store)
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", _build_index([]))

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="current",
        anchors=["@done"],
        explicit_tags=["@done"],
        prefix="",
        content_html="<p>current</p>",
    )

    assert suggestions[:2] == ["search-recency", "A-Programmer's-Introduction-to-Mathematics"]


def test_tag_suggestions_do_not_suppress_literal_tag_due_to_matcher_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeHierarchyNoteStore(
        records=[
            _build_note_record(note_id="root", parent_id=None, content="root", tags=""),
            _build_note_record(note_id="current", parent_id="root", content="sleep", tags=""),
            _build_note_record(note_id="other", parent_id="root", content="other", tags="sleep"),
        ],
        inherited_non_meta_by_note={},
    )

    monkeypatch.setattr(tag_suggestions_module, "note_store", store)
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _MatcherButNoImplicationOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", _build_index([]))

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="current",
        anchors=[],
        explicit_tags=[],
        prefix="",
        content_html="<p>sleep</p>",
    )

    assert suggestions[0] == "sleep"


def test_tag_suggestions_rank_full_context_overlap_before_partial_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeHierarchyNoteStore(
        records=[
            _build_note_record(note_id="current", parent_id=None, content="current", tags=""),
            _build_note_record(note_id="full-1", parent_id=None, content="full", tags="sorting"),
            _build_note_record(note_id="full-2", parent_id=None, content="full", tags="sorting"),
            _build_note_record(note_id="full-3", parent_id=None, content="full", tags="tags"),
            _build_note_record(note_id="partial-1", parent_id=None, content="partial", tags="xLSTM"),
            _build_note_record(note_id="partial-2", parent_id=None, content="partial", tags="xAI"),
        ],
        inherited_non_meta_by_note={
            "current": frozenset({"journal", "projects", "ML3"}),
            "full-1": frozenset({"journal", "projects", "ML3"}),
            "full-2": frozenset({"journal", "projects", "ML3"}),
            "full-3": frozenset({"journal", "projects", "ML3"}),
            "partial-1": frozenset({"journal", "projects"}),
            "partial-2": frozenset({"journal", "projects"}),
        },
    )

    monkeypatch.setattr(tag_suggestions_module, "note_store", store)
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", _build_index([]))

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="current",
        anchors=[],
        explicit_tags=[],
        prefix="",
        content_html="<p>current</p>",
    )

    assert suggestions[:4] == ["sorting", "tags", "xAI", "xLSTM"]


def test_tag_suggestions_use_current_anchor_in_overlap_tiering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeHierarchyNoteStore(
        records=[
            _build_note_record(note_id="current", parent_id=None, content="4", tags=""),
            _build_note_record(note_id="other-1", parent_id=None, content="entry", tags="alcohol bad-decision"),
            _build_note_record(note_id="other-2", parent_id=None, content="entry", tags="alcohol bad-decision"),
            _build_note_record(note_id="other-3", parent_id=None, content="entry", tags="hangover"),
        ],
        inherited_non_meta_by_note={
            "current": frozenset({"journal"}),
            "other-1": frozenset({"journal"}),
            "other-2": frozenset({"journal"}),
            "other-3": frozenset({"journal"}),
        },
    )

    monkeypatch.setattr(tag_suggestions_module, "note_store", store)
    monkeypatch.setattr(tag_suggestions_module, "get_ontology", lambda: _EmptyOntology())
    monkeypatch.setattr(tag_suggestions_module, "search_index", _build_index([]))

    suggestions = tag_suggestions_module.suggest_tags_for_note(
        note_id="current",
        anchors=["bad-decision"],
        explicit_tags=["bad-decision"],
        prefix="",
        content_html="<p>4</p>",
    )

    assert suggestions[:2] == ["alcohol", "hangover"]
