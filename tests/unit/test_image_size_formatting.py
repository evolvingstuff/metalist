from app.services.image_size_formatting import apply_image_size_action
from app.services.inline_image_occurrences import annotate_inline_image_occurrences


FILE_ID = "123e4567-e89b-12d3-a456-426614174000"


def _is_image_file(note_id: str) -> bool:
    return note_id == FILE_ID


def test_annotate_inline_image_occurrences_marks_each_raw_image() -> None:
    content = '<div><img src="one.png"> text <img alt="x > y" src="two.png"></div>'

    assert annotate_inline_image_occurrences(content) == (
        '<div><img data-inline-image-occurrence="0" src="one.png"> text '
        '<img data-inline-image-occurrence="1" alt="x > y" src="two.png"></div>'
    )


def test_annotate_inline_image_occurrences_replaces_pasted_marker() -> None:
    content = '<img data-inline-image-occurrence="99" src="one.png">'

    assert annotate_inline_image_occurrences(content) == (
        '<img data-inline-image-occurrence="0" src="one.png">'
    )


def test_bigger_wraps_unformatted_inline_image() -> None:
    content = '<div>before <img src="one.png"> after</div>'

    result = apply_image_size_action(
        content_html=content,
        tags="foo",
        source_kind="inline",
        occurrence_index=0,
        action="bigger",
        is_image_file=_is_image_file,
    )

    assert result.content_html == '<div>before {<img src="one.png">} after</div>'
    assert result.tags == "foo {@size=1.25}"
    assert result.size_factor == "1.25"
    assert result.changed is True


def test_repeated_bigger_steps_existing_scope() -> None:
    result = apply_image_size_action(
        content_html='<div>{<img src="one.png">}</div>',
        tags="{@size=1.25}",
        source_kind="inline",
        occurrence_index=0,
        action="bigger",
        is_image_file=_is_image_file,
    )

    assert result.content_html == '<div>{<img src="one.png">}</div>'
    assert result.tags == "{@size=1.5}"
    assert result.size_factor == "1.5"


def test_smaller_to_normal_removes_size_scope() -> None:
    result = apply_image_size_action(
        content_html='<div>{<img src="one.png">}</div>',
        tags="{@size=1.25}",
        source_kind="inline",
        occurrence_index=0,
        action="smaller",
        is_image_file=_is_image_file,
    )

    assert result.content_html == '<div><img src="one.png"></div>'
    assert result.tags == ""
    assert result.size_factor == "1.0"


def test_reset_preserves_scope_with_another_style() -> None:
    result = apply_image_size_action(
        content_html='<div>{<img src="one.png">}</div>',
        tags="{@red @size=2.0}",
        source_kind="inline",
        occurrence_index=0,
        action="reset",
        is_image_file=_is_image_file,
    )

    assert result.content_html == '<div>{<img src="one.png">}</div>'
    assert result.tags == "{@red}"
    assert result.size_factor == "1.0"


def test_smaller_wraps_file_image_reference_by_occurrence() -> None:
    result = apply_image_size_action(
        content_html=f"before ![[{FILE_ID}]] after",
        tags="",
        source_kind="file",
        occurrence_index=0,
        action="smaller",
        is_image_file=_is_image_file,
    )

    assert result.content_html == f"before {{![[{FILE_ID}]]}} after"
    assert result.tags == "{@size=0.75}"
    assert result.size_factor == "0.75"


def test_reset_without_existing_size_is_noop() -> None:
    content = '<img src="one.png">'

    result = apply_image_size_action(
        content_html=content,
        tags="foo",
        source_kind="inline",
        occurrence_index=0,
        action="reset",
        is_image_file=_is_image_file,
    )

    assert result.content_html == content
    assert result.tags == "foo"
    assert result.size_factor == "1.0"
    assert result.changed is False


def test_reset_removes_every_scope_owned_by_the_shared_size_tag() -> None:
    result = apply_image_size_action(
        content_html='<div>{<img src="one.png">} {<img src="two.png">}</div>',
        tags="{@size=2.0}",
        source_kind="inline",
        occurrence_index=1,
        action="reset",
        is_image_file=_is_image_file,
    )

    assert result.content_html == '<div><img src="one.png"> <img src="two.png"></div>'
    assert result.tags == ""


def test_smaller_can_step_below_fifty_percent() -> None:
    first = apply_image_size_action(
        content_html='<div>{<img src="one.png">}</div>',
        tags="{@size=0.5}",
        source_kind="inline",
        occurrence_index=0,
        action="smaller",
        is_image_file=_is_image_file,
    )
    second = apply_image_size_action(
        content_html=first.content_html,
        tags=first.tags,
        source_kind="inline",
        occurrence_index=0,
        action="smaller",
        is_image_file=_is_image_file,
    )

    assert first.tags == "{@size=0.25}"
    assert second.tags == "{@size=0.1}"
