from app.usecases.search_comment_autofill import compute_initial_tags_for_new_note


def test_compute_initial_tags_for_new_note_keeps_meta_for_root() -> None:
    tags = compute_initial_tags_for_new_note(
        parent_id=None,
        search_query="@list-bulleted",
    )
    assert tags == "@list-bulleted"


def test_compute_initial_tags_for_new_note_drops_meta_for_children() -> None:
    tags = compute_initial_tags_for_new_note(
        parent_id="parent-note",
        search_query="@list-bulleted",
    )
    assert tags == ""
