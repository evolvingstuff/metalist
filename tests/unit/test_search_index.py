from app.services.search_index import SearchIndex, SearchRecord, extract_tags_for_search
from app.services.search_query import parse_search_query
from app.utils.text_utils import strip_html


def _build_index(records: list[SearchRecord]) -> SearchIndex:
    index = SearchIndex()
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


def test_strip_html_ignores_script_and_inserts_whitespace() -> None:
    assert strip_html("<div>Hello</div><div>world</div>") == "Hello world"
    assert strip_html("<div>ok</div><script>alert(1)</script>hi") == "ok hi"


def test_search_query_parser_tags_and_text() -> None:
    parsed = parse_search_query("foo -bar \"hello world\" -'bad'")
    assert parsed.required_tags == frozenset({"foo"})
    assert parsed.forbidden_tags == frozenset({"bar"})
    assert parsed.required_text == ("hello world",)
    assert parsed.forbidden_text == ("bad",)


def test_search_index_tag_and_text_queries() -> None:
    index = _build_index(
        [
            SearchRecord(
                note_id="n1",
                content_text="Hello world",
                tags="foo",
                tag_terms=extract_tags_for_search("foo"),
            ),
            SearchRecord(
                note_id="n2",
                content_text="Other",
                tags="bar",
                tag_terms=extract_tags_for_search("bar"),
            ),
            SearchRecord(
                note_id="n3",
                content_text="Hello there",
                tags="foo bar",
                tag_terms=extract_tags_for_search("foo bar"),
            ),
        ]
    )

    assert index.query_note_ids('"hello"') == {"n1", "n3"}
    assert index.query_note_ids("foo") == {"n1", "n3"}
    assert index.query_note_ids("foo \"world\"") == {"n1"}
    assert index.query_note_ids("foo -bar") == {"n1"}
    assert index.query_note_ids("-\"world\"") == {"n2", "n3"}


def test_search_index_short_text_term_falls_back_to_verification() -> None:
    index = _build_index(
        [
            SearchRecord(
                note_id="n1",
                content_text="Hello",
                tags="",
                tag_terms=extract_tags_for_search(""),
            ),
            SearchRecord(
                note_id="n2",
                content_text="Other",
                tags="",
                tag_terms=extract_tags_for_search(""),
            ),
        ]
    )
    assert index.query_note_ids('"ll"') == {"n1"}


def test_search_index_tag_suggestions_rank_by_anchor_overlap() -> None:
    index = _build_index(
        [
            SearchRecord(
                note_id="n1",
                content_text="Alpha",
                tags="a b c alpine",
                tag_terms=extract_tags_for_search("a b c alpine"),
            ),
            SearchRecord(
                note_id="n2",
                content_text="Beta",
                tags="a b alpha",
                tag_terms=extract_tags_for_search("a b alpha"),
            ),
            SearchRecord(
                note_id="n3",
                content_text="Gamma",
                tags="alto",
                tag_terms=extract_tags_for_search("alto"),
            ),
        ]
    )

    suggestions = index.suggest_tag_completions(query="a b c al", limit=20)
    assert suggestions[:3] == ["alpine", "alpha", "alto"]

    suggestions = index.suggest_tag_completions(query="alpha ", limit=20)
    assert suggestions == ["a", "b"]

    suggestions = index.suggest_tag_completions(query="alpha", limit=20)
    assert suggestions == []


def test_search_index_tag_suggestions_ignore_quotes_and_include_prefix_only() -> None:
    index = _build_index(
        [
            SearchRecord(
                note_id="n1",
                content_text="Socrates",
                tags="socrates philosopher",
                tag_terms=extract_tags_for_search("socrates philosopher"),
            ),
            SearchRecord(
                note_id="n2",
                content_text="Other",
                tags="journal",
                tag_terms=extract_tags_for_search("journal"),
            ),
        ]
    )

    suggestions = index.suggest_tag_completions(query="socrates \"ancient greece\" phil", limit=20)
    assert suggestions == ["philosopher"]

    suggestions = index.suggest_tag_completions(query="a b c jour", limit=20)
    assert suggestions == ["journal"]


def test_search_index_tag_suggestions_include_meta_tags() -> None:
    index = _build_index([])

    suggestions = index.suggest_tag_completions(query="@", limit=100)
    assert "@json" in suggestions
    assert "@markdown" in suggestions
    assert "@LaTeX" in suggestions
    assert "@shell" in suggestions
    assert "@email" in suggestions
    assert "@heading" in suggestions
    assert "@list-bulleted" in suggestions
    assert "@list-numbered" in suggestions
    assert "@todo" in suggestions
    assert "@monospace" in suggestions
    assert "@dark-theme" not in suggestions

    suggestions = index.suggest_tag_completions(query="@d", limit=20)
    assert suggestions == ["@done"]


def test_search_index_meta_tag_suggestions_rank_by_usage() -> None:
    index = _build_index(
        [
            SearchRecord(
                note_id="n1",
                content_text="One",
                tags="@todo alpha",
                tag_terms=extract_tags_for_search("@todo alpha"),
            ),
            SearchRecord(
                note_id="n2",
                content_text="Two",
                tags="@todo beta",
                tag_terms=extract_tags_for_search("@todo beta"),
            ),
            SearchRecord(
                note_id="n3",
                content_text="Three",
                tags="@todo gamma",
                tag_terms=extract_tags_for_search("@todo gamma"),
            ),
            SearchRecord(
                note_id="n4",
                content_text="Four",
                tags="@done delta",
                tag_terms=extract_tags_for_search("@done delta"),
            ),
            SearchRecord(
                note_id="n5",
                content_text="Five",
                tags="@done epsilon",
                tag_terms=extract_tags_for_search("@done epsilon"),
            ),
            SearchRecord(
                note_id="n6",
                content_text="Six",
                tags="@LaTeX zeta",
                tag_terms=extract_tags_for_search("@LaTeX zeta"),
            ),
        ]
    )

    suggestions = index.suggest_tag_completions(query="@", limit=20)
    assert suggestions[:3] == ["@todo", "@done", "@LaTeX"]

    suggestions = index.suggest_tag_completions(query="@d", limit=20)
    assert suggestions == ["@done"]


def test_search_index_tag_suggestions_collapse_case_equivalent_terms() -> None:
    index = _build_index(
        [
            SearchRecord(
                note_id="n1",
                content_text="One",
                tags="databricks",
                tag_terms=extract_tags_for_search("databricks"),
            ),
            SearchRecord(
                note_id="n2",
                content_text="Two",
                tags="databricks",
                tag_terms=extract_tags_for_search("databricks"),
            ),
            SearchRecord(
                note_id="n3",
                content_text="Three",
                tags="Databricks",
                tag_terms=extract_tags_for_search("Databricks"),
            ),
            SearchRecord(
                note_id="n4",
                content_text="Four",
                tags="delta",
                tag_terms=extract_tags_for_search("delta"),
            ),
        ]
    )

    suggestions = index.suggest_tag_completions(query="", limit=20)
    assert "Databricks" not in suggestions
    assert suggestions[:2] == ["databricks", "delta"]

    suggestions = index.suggest_tag_completions(query="databricks", limit=20)
    assert suggestions == []

    suggestions = index.suggest_tag_completions(query="Databricks ", limit=20)
    assert suggestions == []


def test_search_index_tracks_raw_inherited_frequency_separately_from_ontology() -> None:
    records = [
        SearchRecord(
            note_id="n1",
            content_text="",
            tags="ML3",
            tag_terms=frozenset({"ML3", "math"}),
        ),
        SearchRecord(
            note_id="n2",
            content_text="",
            tags="",
            tag_terms=frozenset({"ML3", "math"}),
        ),
    ]
    index = SearchIndex()
    index.rebuild(
        records,
        raw_tag_terms_by_id={
            "n1": frozenset({"ML3"}),
            "n2": frozenset({"ML3"}),
        },
        progress_update=lambda _processed: None,
        progress_interval=1000,
    )

    assert index.list_tag_frequencies()["math"] == 2
    assert "math" not in index.list_raw_tag_frequencies_by_casefold()
    assert index.list_raw_tag_frequencies_by_casefold()["ml3"] == 2

    index.bulk_update_raw_tag_terms({"n2": frozenset({"ML3", "money"})})
    assert index.list_raw_tag_frequencies_by_casefold()["money"] == 1

    index.remove_many({"n2"})
    assert "money" not in index.list_raw_tag_frequencies_by_casefold()
