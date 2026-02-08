from app.services.search_index import SearchIndex, SearchRecord, extract_tags_for_search
from app.services.search_query import parse_search_query
from app.utils.text_utils import strip_html


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
    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id="n1",
                content_html="<div>Hello world</div>",
                tags="foo",
                tag_terms=extract_tags_for_search("foo"),
            ),
            SearchRecord(
                note_id="n2",
                content_html="<div>Other</div>",
                tags="bar",
                tag_terms=extract_tags_for_search("bar"),
            ),
            SearchRecord(
                note_id="n3",
                content_html="<div>Hello there</div>",
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
    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id="n1",
                content_html="<div>Hello</div>",
                tags="",
                tag_terms=extract_tags_for_search(""),
            ),
            SearchRecord(
                note_id="n2",
                content_html="<div>Other</div>",
                tags="",
                tag_terms=extract_tags_for_search(""),
            ),
        ]
    )
    assert index.query_note_ids('"ll"') == {"n1"}


def test_search_index_tag_suggestions_rank_by_anchor_overlap() -> None:
    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id="n1",
                content_html="<div>Alpha</div>",
                tags="a b c alpine",
                tag_terms=extract_tags_for_search("a b c alpine"),
            ),
            SearchRecord(
                note_id="n2",
                content_html="<div>Beta</div>",
                tags="a b alpha",
                tag_terms=extract_tags_for_search("a b alpha"),
            ),
            SearchRecord(
                note_id="n3",
                content_html="<div>Gamma</div>",
                tags="alto",
                tag_terms=extract_tags_for_search("alto"),
            ),
        ]
    )

    suggestions = index.suggest_tag_completions(query="a b c al")
    assert suggestions[:3] == ["alpine", "alpha", "alto"]

    suggestions = index.suggest_tag_completions(query="alpha ")
    assert suggestions == ["a", "b"]

    suggestions = index.suggest_tag_completions(query="alpha")
    assert suggestions == ["a", "b"]


def test_search_index_tag_suggestions_ignore_quotes_and_include_prefix_only() -> None:
    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id="n1",
                content_html="<div>Socrates</div>",
                tags="socrates philosopher",
                tag_terms=extract_tags_for_search("socrates philosopher"),
            ),
            SearchRecord(
                note_id="n2",
                content_html="<div>Other</div>",
                tags="journal",
                tag_terms=extract_tags_for_search("journal"),
            ),
        ]
    )

    suggestions = index.suggest_tag_completions(query="socrates \"ancient greece\" phil")
    assert suggestions == ["philosopher"]

    suggestions = index.suggest_tag_completions(query="a b c jour")
    assert suggestions == ["journal"]


def test_search_index_tag_suggestions_include_meta_tags() -> None:
    index = SearchIndex()
    index.rebuild([])

    suggestions = index.suggest_tag_completions(query="@")
    assert "@json" in suggestions
    assert "@todo" in suggestions
    assert "@monospace" in suggestions

    suggestions = index.suggest_tag_completions(query="@d")
    assert suggestions == ["@done"]
