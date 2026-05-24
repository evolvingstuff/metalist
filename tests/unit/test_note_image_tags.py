from __future__ import annotations

import app.services.note_image_tags as image_tags
import app.services.note_store as note_store_module


def test_infer_image_tag_terms_adds_tag_for_inline_img() -> None:
    tag_terms = image_tags.infer_image_tag_terms(
        content_html='<div><img src="data:image/png;base64,abc"></div>',
        is_image_file=lambda file_id: False,
    )

    assert tag_terms == frozenset({"@image"})


def test_infer_image_tag_terms_ignores_non_image_content() -> None:
    tag_terms = image_tags.infer_image_tag_terms(
        content_html="<div>plain note</div>",
        is_image_file=lambda file_id: False,
    )

    assert tag_terms == frozenset()


def test_content_contains_image_detects_image_file_reference() -> None:
    file_id = "11111111-1111-1111-1111-111111111111"

    assert image_tags.content_contains_image(
        content_html=f"<div>![[{file_id}]]</div>",
        is_image_file=lambda candidate: candidate == file_id,
    )


def test_content_contains_image_ignores_non_image_file_reference() -> None:
    file_id = "22222222-2222-2222-2222-222222222222"

    assert not image_tags.content_contains_image(
        content_html=f"<div>![[{file_id}]]</div>",
        is_image_file=lambda candidate: False,
    )


def test_note_store_derives_image_search_tag_without_changing_non_meta_terms() -> None:
    tag_terms, non_meta_tag_terms = note_store_module._derive_own_tag_terms(
        tags="project",
        content_html='<div><img src="data:image/webp;base64,abc"></div>',
    )

    assert tag_terms == frozenset({"project", "@image"})
    assert non_meta_tag_terms == frozenset({"project"})
