from __future__ import annotations

import json
from types import MappingProxyType

import pytest

import app.services.agent.investigation as investigation_module
from app.services.agent.investigation import InvestigationState
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.scope import AgentScopeDescriptor
from app.services.agent.scope import FrozenScopedNote
from app.services.agent.scope import FrozenScopedTreeNode
from app.services.agent.scope import ScopedSearchSnapshot
from app.services.tag_ontology import TagOntology


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


def _tagged_search_tree_snapshot() -> ScopedSearchSnapshot:
    descriptor = AgentScopeDescriptor(
        scope_kind="search",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="ML3 -journal",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="ML3 -journal",
    )
    notes = {
        "root-a": _note(
            "root-a", "root-a", "first root", ("ML3", "@heading"), 0,
        ),
        "child-a": _note(
            "child-a", "root-a", "matching child", ("feature",), 1,
        ),
        "sibling-a": _note(
            "sibling-a", "root-a", "unrelated sibling", ("branch-b",), 2,
        ),
        "grandchild-a": _note(
            "grandchild-a", "root-a", "matching descendant", (), 3,
        ),
        "root-b": _note("root-b", "root-b", "second root", ("ML3",), 4),
        "child-b": _note("child-b", "root-b", "other child", (), 5),
    }
    return ScopedSearchSnapshot(
        run_id="run-search",
        session_key="session-1",
        descriptor=descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=("root-a", "root-b"),
        ordered_note_ids=(
            "root-a",
            "child-a",
            "grandchild-a",
            "sibling-a",
            "root-b",
            "child-b",
        ),
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=MappingProxyType(
            {
                "root-a": FrozenScopedTreeNode(
                    note_id="root-a",
                    parent_id="",
                    root_note_id="root-a",
                    child_ids=("child-a", "sibling-a"),
                ),
                "child-a": FrozenScopedTreeNode(
                    note_id="child-a",
                    parent_id="root-a",
                    root_note_id="root-a",
                    child_ids=("grandchild-a",),
                ),
                "grandchild-a": FrozenScopedTreeNode(
                    note_id="grandchild-a",
                    parent_id="child-a",
                    root_note_id="root-a",
                    child_ids=(),
                ),
                "sibling-a": FrozenScopedTreeNode(
                    note_id="sibling-a",
                    parent_id="root-a",
                    root_note_id="root-a",
                    child_ids=(),
                ),
                "root-b": FrozenScopedTreeNode(
                    note_id="root-b",
                    parent_id="",
                    root_note_id="root-b",
                    child_ids=("child-b",),
                ),
                "child-b": FrozenScopedTreeNode(
                    note_id="child-b",
                    parent_id="root-b",
                    root_note_id="root-b",
                    child_ids=(),
                ),
            }
        ),
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


def test_facets_communicate_ontology_synonyms() -> None:
    ontology = TagOntology(
        implication_out_edges={},
        implication_closure={},
        implied_by_closure={},
        scc_members_by_tag={
            "foo": frozenset({"foo", "alternate-foo"}),
        },
        matcher_rules=(),
    )
    state = InvestigationState.start_with_ontology(
        snapshot=_snapshot(),
        settings=_settings(),
        ontology=ontology,
    )

    facets = state.current_facet_page()
    foo = next(facet for facet in facets.facets if facet.tag == "foo")

    assert foo.synonyms == ("alternate-foo",)


def test_narrowing_merges_and_caches_ontology_synonyms_across_case_variant_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ontology = TagOntology(
        implication_out_edges={},
        implication_closure={},
        implied_by_closure={},
        scc_members_by_tag={
            "FOO": frozenset({"FOO", "upper-synonym"}),
            "foo": frozenset({"foo", "lower-synonym"}),
        },
        matcher_rules=(),
    )
    state = InvestigationState.start_with_ontology(
        snapshot=_snapshot(),
        settings=_settings(),
        ontology=ontology,
    )
    focus_call_count = 0
    original_focus_view = TagOntology.focus_view

    def counted_focus_view(
        self: TagOntology,
        *,
        tag: str,
    ) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        nonlocal focus_call_count
        focus_call_count += 1
        return original_focus_view(self, tag=tag)

    monkeypatch.setattr(TagOntology, "focus_view", counted_focus_view)

    facets = state.current_narrowing_facet_page()
    foo = next(facet for facet in facets.facets if facet.tag == "foo")

    assert foo.synonyms == ("lower-synonym", "upper-synonym")
    assert focus_call_count == 2


def test_narrowing_facet_matching_scales_with_unique_tags_not_note_tag_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note_ids = tuple(f"note-{index}" for index in range(100))
    notes = {
        note_id: _note(
            note_id,
            note_id,
            f"evidence {index}",
            (f"tag-{index % 10}",),
            index,
        )
        for index, note_id in enumerate(note_ids)
    }
    snapshot = ScopedSearchSnapshot(
        run_id="run-repeated-tags",
        session_key="session-1",
        descriptor=_snapshot().descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=note_ids,
        ordered_note_ids=note_ids,
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=MappingProxyType(
            {
                note_id: FrozenScopedTreeNode(
                    note_id=note_id,
                    parent_id="",
                    root_note_id=note_id,
                    child_ids=(),
                )
                for note_id in note_ids
            }
        ),
    )
    state = InvestigationState.start(snapshot=snapshot, settings=_settings())
    match_call_count = 0
    original_match = investigation_module.tag_term_matches_prefix

    def counted_match(*, term: str, prefix: str) -> bool:
        nonlocal match_call_count
        match_call_count += 1
        return original_match(term=term, prefix=prefix)

    monkeypatch.setattr(
        investigation_module,
        "tag_term_matches_prefix",
        counted_match,
    )

    facets = state.current_narrowing_facet_page()

    assert facets.total_facets == 10
    assert match_call_count <= 100


def test_cumulative_tag_narrowing_rejects_zero_and_keeps_best_nonempty() -> None:
    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())
    state.current_facet_page()
    state.current_note_page()

    result = state.narrow_by_ordered_tags(
        ordered_tags=["foo", "rare-tag", "baz"],
        target_approximate_tokens=1,
    )

    assert [attempt.tags for attempt in result.attempts] == [
        ("foo",),
        ("foo", "rare-tag"),
        ("foo", "rare-tag", "baz"),
    ]
    assert result.attempts[-1].rejected_zero_results is True
    assert result.selected_tags == ("foo", "rare-tag")
    assert result.did_narrow is True
    assert state.current_note_ids == ("a", "a-child")
    assert set(state.current_note_ids).issubset(_snapshot().ordered_note_ids)


def test_cumulative_tag_narrowing_prefers_first_subset_at_or_below_target() -> None:
    measuring_state = InvestigationState.start(
        snapshot=_snapshot(),
        settings=_settings(),
    )
    measuring_state.current_facet_page()
    measuring_state.current_note_page()
    measured = measuring_state.narrow_by_ordered_tags(
        ordered_tags=["foo", "rare-tag"],
        target_approximate_tokens=1,
    )
    first_attempt_tokens = measured.attempts[0].approximate_token_count
    second_attempt_tokens = measured.attempts[1].approximate_token_count
    assert second_attempt_tokens < first_attempt_tokens - 1

    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())
    state.current_facet_page()
    state.current_note_page()
    result = state.narrow_by_ordered_tags(
        ordered_tags=["foo", "rare-tag"],
        target_approximate_tokens=first_attempt_tokens - 1,
    )

    assert result.attempts[0].approximate_token_count > (
        result.target_approximate_token_count
    )
    assert result.attempts[1].approximate_token_count <= (
        result.target_approximate_token_count
    )
    assert result.selected_tags == ("foo", "rare-tag")
    assert result.selected.approximate_token_count == second_attempt_tokens


def test_cumulative_tag_narrowing_measures_later_prefixes_after_reaching_target() -> None:
    measuring_state = InvestigationState.start(
        snapshot=_snapshot(),
        settings=_settings(),
    )
    measuring_state.current_facet_page()
    measuring_state.current_note_page()
    measured = measuring_state.narrow_by_ordered_tags(
        ordered_tags=["foo", "rare-tag"],
        target_approximate_tokens=1,
    )
    second_attempt_tokens = measured.attempts[1].approximate_token_count

    state = InvestigationState.start(snapshot=_snapshot(), settings=_settings())
    state.current_facet_page()
    state.current_note_page()
    result = state.narrow_by_ordered_tags(
        ordered_tags=["foo", "rare-tag", "baz"],
        target_approximate_tokens=second_attempt_tokens,
    )

    assert len(result.attempts) == 3
    assert result.attempts[2].rejected_zero_results is True
    assert result.selected_tags == ("foo", "rare-tag")


def test_narrowing_candidates_exclude_tags_required_by_user_search() -> None:
    state = InvestigationState.start(
        snapshot=_tagged_search_tree_snapshot(),
        settings=_settings(),
    )

    facets = state.current_narrowing_facet_page()

    assert [facet.tag for facet in facets.facets] == ["feature", "branch-b"]
    assert all(not facet.tag.startswith("@") for facet in facets.facets)
    feature = next(facet for facet in facets.facets if facet.tag == "feature")
    assert feature.note_count == 2
    assert feature.result_tree_count == 1
    assert state.required_scope_tags == frozenset({"ml3"})


def test_narrowing_rejects_required_user_scope_tag_even_if_note_page_discloses_it() -> None:
    state = InvestigationState.start(
        snapshot=_tagged_search_tree_snapshot(),
        settings=_settings(),
    )
    state.current_note_page()

    with pytest.raises(ValueError, match="already required"):
        state.narrow_by_ordered_tags(
            ordered_tags=["ML3"],
            target_approximate_tokens=1,
        )


def test_tag_narrowing_retains_matching_descendants_and_structural_ancestors() -> None:
    snapshot = _tagged_search_tree_snapshot()
    state = InvestigationState.start(snapshot=snapshot, settings=_settings())
    state.current_narrowing_facet_page()

    result = state.narrow_by_ordered_tags(
        ordered_tags=["feature"],
        target_approximate_tokens=1,
    )

    assert result.selected_tags == ("feature",)
    assert state.current_note_ids == ("child-a", "grandchild-a")
    page = state.current_note_page()
    assert page.result_trees[0]["note_id"] == "root-a"
    assert "content_text" not in page.result_trees[0]
    assert [child["note_id"] for child in page.result_trees[0]["children"]] == [
        "child-a"
    ]
    assert page.result_trees[0]["children"][0]["children"][0]["note_id"] == (
        "grandchild-a"
    )
    assert "sibling-a" not in json.dumps(page.result_trees)


def test_cumulative_sibling_tags_reject_root_with_no_matching_inheritance_path() -> None:
    state = InvestigationState.start(
        snapshot=_tagged_search_tree_snapshot(),
        settings=_settings(),
    )
    state.current_narrowing_facet_page()

    result = state.narrow_by_ordered_tags(
        ordered_tags=["feature", "branch-b"],
        target_approximate_tokens=1,
    )

    assert result.attempts[0].rejected_zero_results is False
    assert result.attempts[1].rejected_zero_results is True
    assert result.selected_tags == ("feature",)


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


def test_retained_root_prefix_uses_token_budget_not_result_tree_cap(
    monkeypatch,
) -> None:
    snapshot = _many_root_snapshot(count=5)
    state = InvestigationState.start(
        snapshot=snapshot,
        settings=AgentRetrievalSettings(
            max_note_characters=500,
            max_page_characters=5_000,
            max_notes_per_page=1,
            max_page_approximate_tokens=500,
            max_ranked_tags_per_page=2,
            max_working_summary_characters=8_000,
        ),
    )

    retention = state.retain_root_prefix_within_token_budget()
    real_estimate_input_tokens = investigation_module.estimate_input_tokens
    token_estimate_calls = 0

    def counted_estimate_input_tokens(value: object) -> int:
        nonlocal token_estimate_calls
        token_estimate_calls += 1
        return real_estimate_input_tokens(value)

    monkeypatch.setattr(
        investigation_module,
        "estimate_input_tokens",
        counted_estimate_input_tokens,
    )
    page = state.current_scope_as_single_page()

    assert retention.retained_root_ids == snapshot.ordered_root_ids
    assert retention.dropped_root_ids == ()
    assert retention.retained_approximate_token_count <= 500
    assert state.current_note_ids == snapshot.ordered_note_ids
    assert page.result_tree_ids == snapshot.ordered_root_ids
    assert page.total_pages == 1
    assert token_estimate_calls == 1


def test_retained_root_prefix_stops_counting_after_first_root_over_budget(
    monkeypatch,
) -> None:
    snapshot = _many_root_snapshot(count=5)
    state = InvestigationState.start(
        snapshot=snapshot,
        settings=AgentRetrievalSettings(
            max_note_characters=500,
            max_page_characters=5_000,
            max_notes_per_page=50,
            max_page_approximate_tokens=500,
            max_ranked_tags_per_page=2,
            max_working_summary_characters=8_000,
        ),
    )
    visited_root_ids: list[str] = []

    def fixed_root_cost(*, root_id: str, note_ids: list[str]) -> int:
        assert note_ids
        visited_root_ids.append(root_id)
        return 200

    monkeypatch.setattr(state, "_full_root_page_token_cost", fixed_root_cost)

    retention = state.retain_root_prefix_within_token_budget()

    assert retention.retained_root_ids == snapshot.ordered_root_ids[:2]
    assert retention.dropped_root_ids == snapshot.ordered_root_ids[2:]
    assert retention.retained_approximate_token_count == 400
    assert visited_root_ids == list(snapshot.ordered_root_ids[:3])


def test_retained_root_prefix_omits_an_oversized_first_root_and_everything_after(
    monkeypatch,
) -> None:
    snapshot = _many_root_snapshot(count=3)
    state = InvestigationState.start(
        snapshot=snapshot,
        settings=AgentRetrievalSettings(
            max_note_characters=500,
            max_page_characters=5_000,
            max_notes_per_page=50,
            max_page_approximate_tokens=500,
            max_ranked_tags_per_page=2,
            max_working_summary_characters=8_000,
        ),
    )
    visited_root_ids: list[str] = []

    def oversized_root_cost(*, root_id: str, note_ids: list[str]) -> int:
        assert note_ids
        visited_root_ids.append(root_id)
        return 501

    monkeypatch.setattr(state, "_full_root_page_token_cost", oversized_root_cost)

    retention = state.retain_root_prefix_within_token_budget()

    assert retention.retained_root_ids == ()
    assert retention.dropped_root_ids == snapshot.ordered_root_ids
    assert retention.retained_note_count == 0
    assert state.current_note_ids == ()
    assert visited_root_ids == [snapshot.ordered_root_ids[0]]
