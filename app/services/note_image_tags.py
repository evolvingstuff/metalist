from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Callable, FrozenSet

from app.services.embedded_references import collect_reference_tokens_from_html


IMAGE_TAG = "@image"

_DATA_IMAGE_RE = re.compile(r"\bdata:image/[a-z0-9.+-]+", re.IGNORECASE)
_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]\n]*\]\([^)]+?\.(?:avif|bmp|gif|heic|heif|jpe?g|png|svg|tiff?|webp)(?:[?#][^)]*)?\)",
    re.IGNORECASE,
)


class _ImageHtmlDetector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_image_tag = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "img":
            self.has_image_tag = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


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
    if _MARKDOWN_IMAGE_RE.search(content_html):
        return True

    for reference_token in collect_reference_tokens_from_html(content_html):
        file_id = reference_token.note_id
        if is_image_file(file_id):
            return True
    return False


def _contains_inline_image_markup(content_html: str) -> bool:
    detector = _ImageHtmlDetector()
    detector.feed(content_html)
    if detector.has_image_tag:
        return True
    return bool(_DATA_IMAGE_RE.search(content_html))
