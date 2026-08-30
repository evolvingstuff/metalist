from __future__ import annotations

from types import MappingProxyType

import pytest

from app.services.agent.investigation import InvestigationState
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.scope import AgentScopeDescriptor
from app.services.agent.scope import FrozenScopedNote
from app.services.agent.scope import FrozenScopedTreeNode
from app.services.agent.scope import ScopedSearchSnapshot


def _note(
    note_id: str,
    root_note_id: str,
    content: str,
    explicit_tags: tuple[str, ...],
    order_index: int,
) -> FrozenScopedNote:
    parent_id = ""
    if note_id != root_note_id:
        parent_id = root_note_id
    return FrozenScopedNote(
        note_id=note_id,
        parent_id=parent_id,
        root_note_id=root_note_id,
        content_text=content,
        explicit_tags_text=" ".join(explicit_tags),
        explicit_tag_terms=explicit_tags,
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:00+00:00",
        order_index=order_index,
    )


def _snapshot() -> ScopedSearchSnapshot:
    notes = {
        "a": _note(
            "a", "a", "lorem ipsum alpha", ("foo", "rare-tag"), 0,
        ),
        "a-child": _note(
            "a-child", "a", "lorem ipsum child", ("bar",), 1,
        ),
        "b": _note(
            "b", "b", "different evidence", ("foo", "baz"), 2,
        ),
        "c": _note(
            "c", "c", "last evidence " + ("! " * 300), ("baz",), 3,
        ),
    }
    descriptor = AgentScopeDescriptor(
        scope_kind="all_notes",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="All notes",
    )
    return ScopedSearchSnapshot(
        run_id="run-1",
        session_key="session-1",
        descriptor=descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=("a", "b", "c"),
        ordered_note_ids=("a", "a-child", "b", "c"),
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=MappingProxyType(
            {
                "a": FrozenScopedTreeNode(
                    note_id="a",
                    parent_id="",
                    root_note_id="a",
                    child_ids=("a-child",),
                ),
                "a-child": FrozenScopedTreeNode(
                    note_id="a-child",
                    parent_id="a",
                    root_note_id="a",
                    child_ids=(),
                ),
                "b": FrozenScopedTreeNode(
                    note_id="b",
                    parent_id="",
                    root_note_id="b",
                    child_ids=(),
                ),
                "c": FrozenScopedTreeNode(
                    note_id="c",
                    parent_id="",
                    root_note_id="c",
                    child_ids=(),
                ),
            }
        ),
    )


def _settings() -> AgentRetrievalSettings:
    return AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=2,
        max_page_approximate_tokens=500,
        max_ranked_tags_per_page=2,
        max_working_summary_characters=8_000,
    )


def _many_root_snapshot(*, count: int) -> ScopedSearchSnapshot:
    note_ids = tuple(f"note-{index}" for index in range(count))
    notes = {
        note_id: _note(note_id, note_id, f"evidence {index}", (), index)
        for index, note_id in enumerate(note_ids)
    }
    tree_nodes = {
        note_id: FrozenScopedTreeNode(
            note_id=note_id,
            parent_id="",
            root_note_id=note_id,
            child_ids=(),
        )
        for note_id in note_ids
    }
    return ScopedSearchSnapshot(
        run_id="run-many",
        session_key="session-1",
        descriptor=_snapshot().descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=note_ids,
        ordered_note_ids=note_ids,
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=MappingProxyType(tree_nodes),
    )


def test_facets_count_unique_notes_and_result_trees_over_full_subset() -> None:
    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())

    facets = state.current_facet_page()

    assert [(facet.tag, facet.note_count, facet.result_tree_count) for facet in facets.facets] == [
        ("baz", 2, 2),
        ("foo", 2, 2),
    ]
    assert facets.total_facets == 4
    assert facets.total_pages == 2


def test_note_page_is_root_ordered_and_discloses_exact_tags() -> None:
    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())

    page = state.current_note_page()

    assert page.result_tree_ids == ("a", "b")
    assert [tree["note_id"] for tree in page.result_trees] == ["a", "b"]
    first_tree = page.result_trees[0]
    assert first_tree["tags"] == ["foo", "rare-tag"]
    assert [child["note_id"] for child in first_tree["children"]] == ["a-child"]
    assert first_tree["children"][0]["tags"] == ["bar"]
    assert state.observed_source_ids == frozenset({"a", "a-child", "b"})
    assert "rare-tag" in state.disclosed_tags
    assert "bar" in state.disclosed_tags


def test_note_page_enforces_configured_result_tree_count_cap() -> None:
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=1,
        max_page_approximate_tokens=24_000,
        max_ranked_tags_per_page=50,
        max_working_summary_characters=8_000,
    )
    state = InvestigationState.start(snapshot=_snapshot(), settings=settings)

    first = state.current_note_page()
    second = state.page_next()
    third = state.page_next()

    assert first.result_tree_ids == ("a",)
    assert second.result_tree_ids == ("b",)
    assert third.result_tree_ids == ("c",)
    assert first.total_pages == second.total_pages == third.total_pages == 3


def test_note_page_uses_contentless_ancestor_to_preserve_nested_result_tree() -> None:
    child = FrozenScopedNote(
        note_id="child",
        parent_id="middle",
        root_note_id="root",
        content_text="matching child evidence",
        explicit_tags_text="child-tag",
        explicit_tag_terms=("child-tag",),
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:00+00:00",
        order_index=0,
    )
    snapshot = ScopedSearchSnapshot(
        run_id="run-1",
        session_key="session-1",
        descriptor=_snapshot().descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=("root",),
        ordered_note_ids=("child",),
        notes_by_id=MappingProxyType({"child": child}),
        tree_nodes_by_id=MappingProxyType(
            {
                "root": FrozenScopedTreeNode(
                    note_id="root",
                    parent_id="",
                    root_note_id="root",
                    child_ids=("middle",),
                ),
                "middle": FrozenScopedTreeNode(
                    note_id="middle",
                    parent_id="root",
                    root_note_id="root",
                    child_ids=("child",),
                ),
                "child": FrozenScopedTreeNode(
                    note_id="child",
                    parent_id="middle",
                    root_note_id="root",
                    child_ids=(),
                ),
            }
        ),
    )
    state = InvestigationState.start(snapshot=snapshot, settings=_settings())

    page = state.current_note_page()

    assert page.result_trees == (
        {
            "note_id": "root",
            "is_evidence": False,
            "children": [
                {
                    "note_id": "middle",
                    "is_evidence": False,
                    "children": [
                        {
                            "note_id": "child",
                            "content_text": "matching child evidence",
                            "created_at": "2026-08-29T00:00:00+00:00",
                            "updated_at": "2026-08-29T00:00:00+00:00",
                            "tags": ["child-tag"],
                        }
                    ],
                }
            ],
        },
    )


def test_tag_refinement_is_a_strict_subset_and_backtracking_restores_scope() -> None:
    snapshot = _snapshot()
    state = InvestigationState.start(snapshot=snapshot, settings=_settings())
    initial_state_id = state.current_state_id
    state.current_note_page()

    refined = state.refine_tags(expression="rare-tag")

    assert refined.matching_note_count == 1
    assert refined.result_tree_ids == ("a",)
    assert set(state.current_note_ids).issubset(set(snapshot.ordered_note_ids))
    assert state.current_state_id != initial_state_id

    restored = state.backtrack(state_id=initial_state_id)

    assert restored.matching_note_count == 4
    assert state.current_note_ids == snapshot.ordered_note_ids


def test_refinement_rejects_undisclosed_tag_even_when_it_exists_in_scope() -> None:
    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())

    with pytest.raises(ValueError, match="has not been disclosed"):
        state.refine_tags(expression="rare-tag")


def test_exact_text_refinement_is_case_insensitive_and_cumulative() -> None:
    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())
    state.current_note_page()
    state.refine_tags(expression="foo")

    page = state.refine_exact_text(text="LOREM IPSUM")

    assert [tree["note_id"] for tree in page.result_trees] == ["a"]
    assert "children" not in page.result_trees[0]
    assert page.matching_note_count == 1


def test_reopen_sources_rejects_unobserved_and_duplicate_ids() -> None:
    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())
    state.current_note_page()

    with pytest.raises(ValueError, match="previously observed"):
        state.reopen_sources(note_ids=["c"])
    with pytest.raises(ValueError, match="unique"):
        state.reopen_sources(note_ids=["a", "a"])

    reopened = state.reopen_sources(note_ids=["a-child"])
    assert reopened[0]["content_text"] == "lorem ipsum child"


def test_final_answer_rehydration_accepts_32_sources_but_rejects_33() -> None:
    snapshot = _many_root_snapshot(count=33)
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=100_000,
        max_notes_per_page=100,
        max_page_approximate_tokens=24_000,
        max_ranked_tags_per_page=2,
        max_working_summary_characters=8_000,
    )
    state = InvestigationState.start(snapshot=snapshot, settings=settings)
    page = state.current_note_page()
    assert page.evidence_note_ids == snapshot.ordered_note_ids

    rehydrated = state.rehydrate_answer_sources(
        note_ids=list(snapshot.ordered_note_ids[:32])
    )
    assert len(rehydrated) == 32

    with pytest.raises(ValueError, match="at most 32 note ids"):
        state.rehydrate_answer_sources(note_ids=list(snapshot.ordered_note_ids))


def test_page_next_fails_at_last_page() -> None:
    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())
    second = state.page_next()

    assert second.page == 2
    with pytest.raises(ValueError, match="no next note page"):
        state.page_next()


def test_note_pages_pack_complete_root_trees_by_approximate_token_budget() -> None:
    base = _snapshot()
    notes = {
        "large": _note(
            "large",
            "large",
            "x" * 1_600,
            (),
            0,
        ),
        "small-a": _note(
            "small-a",
            "small-a",
            "alpha",
            (),
            1,
        ),
        "small-b": _note(
            "small-b",
            "small-b",
            "beta",
            (),
            2,
        ),
    }
    snapshot = ScopedSearchSnapshot(
        run_id="run-token-pages",
        session_key="session-1",
        descriptor=base.descriptor,
        created_at=base.created_at,
        ordered_root_ids=("large", "small-a", "small-b"),
        ordered_note_ids=("large", "small-a", "small-b"),
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=MappingProxyType(
            {
                note_id: FrozenScopedTreeNode(
                    note_id=note_id,
                    parent_id="",
                    root_note_id=note_id,
                    child_ids=(),
                )
                for note_id in notes
            }
        ),
    )
    state = InvestigationState.start(
        snapshot=snapshot,
        settings=AgentRetrievalSettings(
            max_note_characters=2_000,
            max_page_characters=100_000,
            max_notes_per_page=100,
            max_page_approximate_tokens=500,
        ),
    )

    first = state.current_note_page()
    second = state.page_next()

    assert first.result_tree_ids == ("large",)
    assert second.result_tree_ids == ("small-a", "small-b")
    assert first.total_pages == second.total_pages == 2
    assert state.total_note_pages == 2
    assert first.returned_approximate_token_count <= 500
    assert second.returned_approximate_token_count <= 500
    assert "tags" not in first.result_trees[0]
    assert "tags" not in second.result_trees[0]
