from app.services.agent.citation_tokens import ShortCitationTranslator


_IDS = {1: "page-0001", 12: "link-0012"}
_NOTES = {"n1": "11111111-1111-4111-8111-111111111111", "n12": "22222222-2222-4222-8222-222222222222"}


def _translator() -> ShortCitationTranslator:
    return ShortCitationTranslator(evidence_ids_by_number=lambda: dict(_IDS), note_ids_by_alias=_NOTES)


def test_short_tokens_become_full_tokens() -> None:
    translator = _translator()
    assert translator.feed("Story.[[web:12]] Note.[[n1]] Page.[[web:1]]") == (
        f"Story.[[web:link-0012]] Note.[[{_NOTES['n1']}]] Page.[[web:page-0001]]")
    assert translator.flush() == ""


def test_a_token_split_across_chunks_is_held_back_until_complete() -> None:
    translator = _translator()
    pieces = [translator.feed(chunk) for chunk in ("Story.[", "[we", "b:1", "2]", "] and [[n", "12", "]]!")]
    assert pieces == ["Story.", "", "", "", "[[web:link-0012]] and ", "", f"[[{_NOTES['n12']}]]!"]


def test_unknown_tokens_are_dropped_and_full_ids_and_brackets_pass_through() -> None:
    translator = _translator()
    full = "[[33333333-3333-4333-8333-333333333333]]"
    assert translator.feed(f"A [link](x), [[web:99]] [[n7]] and {full}") == f"A [link](x),   and {full}"
    # A trailing "[" waits for the next chunk; at the end of the turn it is shown as is.
    assert translator.feed("ends with [") == "ends with "
    assert translator.flush() == "["
