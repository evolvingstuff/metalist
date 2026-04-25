from types import SimpleNamespace

import app.usecases.search_context_tags as search_context_tags_module
from app.usecases.search_context_tags import ensure_tags_match_search_query


def test_ensure_tags_match_search_query_uses_existing_tag_case(monkeypatch) -> None:
    monkeypatch.setattr(
        search_context_tags_module.search_index,
        "list_tag_frequencies",
        lambda: {"ML3": 3},
    )

    tags = ensure_tags_match_search_query(
        parent_id=None,
        content="",
        tags="",
        search_query="ml3",
    )

    assert tags == "ML3"


def test_ensure_tags_match_search_query_dedupes_case_equivalent_search_tags(monkeypatch) -> None:
    monkeypatch.setattr(
        search_context_tags_module.search_index,
        "list_tag_frequencies",
        lambda: {"ML3": 3},
    )

    tags = ensure_tags_match_search_query(
        parent_id=None,
        content="",
        tags="",
        search_query="ml3 ML3",
    )

    assert tags == "ML3"


def test_ensure_tags_match_search_query_compares_explicit_tags_case_insensitively(monkeypatch) -> None:
    monkeypatch.setattr(
        search_context_tags_module.search_index,
        "list_tag_frequencies",
        lambda: {"ML3": 3},
    )

    tags = ensure_tags_match_search_query(
        parent_id=None,
        content="",
        tags="ML3",
        search_query="ml3",
    )

    assert tags == "ML3"


def test_ensure_tags_match_search_query_compares_inherited_tags_case_insensitively(monkeypatch) -> None:
    monkeypatch.setattr(
        search_context_tags_module.search_index,
        "list_tag_frequencies",
        lambda: {"ML3": 3},
    )
    monkeypatch.setattr(
        search_context_tags_module,
        "store",
        SimpleNamespace(
            get=lambda note_id: SimpleNamespace(
                id=note_id,
                parent_id=None,
                content="",
                tags="ML3",
            )
        ),
    )

    tags = ensure_tags_match_search_query(
        parent_id="parent-note",
        content="",
        tags="",
        search_query="ml3",
    )

    assert tags == ""
