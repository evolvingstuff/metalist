from app.services.agent.web_citation_tokens import ShortWebTokenTranslator


_IDS = {1: "page-0001", 12: "link-0012"}


def _translator() -> ShortWebTokenTranslator:
    return ShortWebTokenTranslator(evidence_ids_by_number=lambda: dict(_IDS))


def test_short_tokens_become_full_evidence_tokens() -> None:
    translator = _translator()
    assert translator.feed("Story.[[web:12]] Page.[[web:1]]") == "Story.[[web:link-0012]] Page.[[web:page-0001]]"
    assert translator.flush() == ""


def test_a_token_split_across_chunks_is_held_back_until_complete() -> None:
    translator = _translator()
    pieces = [translator.feed(chunk) for chunk in ("Story.[", "[we", "b:1", "2]", "] next")]
    assert pieces == ["Story.", "", "", "", "[[web:link-0012]] next"]


def test_unknown_numbers_are_dropped_and_ordinary_brackets_pass_through() -> None:
    translator = _translator()
    assert translator.feed("A [link](x) and [[web:99]] gone") == "A [link](x) and  gone"
    # A trailing "[" waits for the next chunk; at the end of the turn it is shown as is.
    assert translator.feed("ends with [") == "ends with "
    assert translator.flush() == "["
