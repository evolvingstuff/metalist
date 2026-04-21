from app.services.tag_term_matching import list_significant_content_match_segments
from app.services.tag_term_matching import match_tag_term_in_normalized_content
from app.services.tag_term_matching import normalize_tag_match_text


def test_list_significant_content_match_segments_excludes_common_stopwords() -> None:
    assert list_significant_content_match_segments("no-propranolol") == ("propranolol",)
    assert list_significant_content_match_segments("A-Programmer's-Introduction-to-Mathematics") == (
        "programmer's",
        "introduction",
        "mathematics",
    )
    assert list_significant_content_match_segments("I-plug-in") == ("plug",)


def test_match_tag_term_in_normalized_content_ignores_stopword_only_matches() -> None:
    normalized_content = normalize_tag_match_text("No more of that I guess")

    assert match_tag_term_in_normalized_content(
        term="no-propranolol",
        normalized_content=normalized_content,
    ) is None
    assert match_tag_term_in_normalized_content(
        term="A-Programmer's-Introduction-to-Mathematics",
        normalized_content=normalized_content,
    ) is None
    assert match_tag_term_in_normalized_content(
        term="I-plug-in",
        normalized_content=normalized_content,
    ) is None


def test_match_tag_term_in_normalized_content_keeps_non_prose_uppercase_single_letters() -> None:
    match = match_tag_term_in_normalized_content(
        term="X-Y-Z",
        normalized_content=normalize_tag_match_text("Y Z"),
    )

    assert match is not None
    assert match.matched_segments == ("y", "z")
