from __future__ import annotations

import re
from typing import Callable, FrozenSet

from app.services.embedded_references import collect_reference_tokens_from_html


IMAGE_TAG = "@image"

_INLINE_IMAGE_RE = re.compile(
    r"<img(?=[\s/>])|\bdata:image/[a-z0-9.+-]+",
    re.IGNORECASE,
)
_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]\n]*\]\([^)]+?\.(?:avif|bmp|gif|heic|heif|jpe?g|png|svg|tiff?|webp)(?:[?#][^)]*)?\)",
    re.IGNORECASE,
)


def infer_image_tag_terms(
    *,
    content_html: str,
    is_image_file: Callable[[str], bool],
) -> FrozenSet[str]:
    if not isinstance(content_html, str):
        raise TypeError(f"content_html must be a string, got {type(content_html)}")
    if not callable(is_image_file):
        raise TypeError("is_image_file must be callable")
    if content_contains_image(content_html=content_html, is_image_file=is_image_file):
        return frozenset({IMAGE_TAG})
    return frozenset()


def content_contains_image(*, content_html: str, is_image_file: Callable[[str], bool]) -> bool:
    if not isinstance(content_html, str):
        raise TypeError(f"content_html must be a string, got {type(content_html)}")
    if not callable(is_image_file):
        raise TypeError("is_image_file must be callable")

    if _contains_inline_image_markup(content_html):
        return True
    if "![" in content_html and _MARKDOWN_IMAGE_RE.search(content_html):
        return True

    if "[[" not in content_html:
        return False
    for reference_token in collect_reference_tokens_from_html(content_html):
        file_id = reference_token.note_id
        if is_image_file(file_id):
            return True
    return False


def _contains_inline_image_markup(content_html: str) -> bool:
    return _INLINE_IMAGE_RE.search(content_html) is not None
