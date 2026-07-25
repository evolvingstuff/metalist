from __future__ import annotations

from app.services.search_index import SearchIndex
from app.services.search_index import SearchRecord
from app.services.search_index import extract_tags_for_search


def _build_index() -> SearchIndex:
    index = SearchIndex()
    records = [
        SearchRecord(
            note_id="n1",
            content_text="Dad birthday details",
            tags="Dad birthday",
            tag_terms=extract_tags_for_search("Dad birthday"),
        ),
        SearchRecord(
            note_id="n2",
            content_text="Mom birthday details",
            tags="mom birthday",
            tag_terms=extract_tags_for_search("mom birthday"),
        ),
    ]
    index.rebuild(
        records,
        raw_tag_terms_by_id={
            record.note_id: extract_tags_for_search(record.tags)
            for record in records
        },
        progress_update=lambda _processed: None,
        progress_interval=1000,
    )
    return index


def test_query_note_ids_matches_required_tags_case_insensitively() -> None:
    index = _build_index()

    assert index.query_note_ids("dad birthday") == {"n1"}
    assert index.query_note_ids("Dad birthday") == {"n1"}


def test_query_note_ids_matches_forbidden_tags_case_insensitively() -> None:
    index = _build_index()

    assert index.query_note_ids("birthday -dad") == {"n2"}
    assert index.query_note_ids("birthday -Dad") == {"n2"}
