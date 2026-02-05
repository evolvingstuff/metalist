from __future__ import annotations

import re

from app.utils.text_utils import strip_html


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_tag_bar_comment_text(tags: str) -> str:
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")

    comments: list[str] = []
    index = 0
    while index < len(tags):
        start = tags.find("/*", index)
        if start == -1:
            break

        end = tags.find("*/", start + 2)
        if end == -1:
            break

        inner = tags[start + 2 : end]
        normalized = _normalize_whitespace(inner)
        if normalized:
            comments.append(normalized)

        index = end + 2

    return " ".join(comments)


def build_searchable_text_casefold_from_plaintext(content_text: str, tags: str) -> str:
    if not isinstance(content_text, str):
        raise TypeError(f"content_text must be a string, got {type(content_text)}")
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")

    comment_text = extract_tag_bar_comment_text(tags)

    combined = content_text
    if comment_text:
        if combined:
            combined = f"{combined} {comment_text}"
        else:
            combined = comment_text

    return combined.casefold()


def build_searchable_text_casefold(content_html: str, tags: str) -> str:
    if not isinstance(content_html, str):
        raise TypeError(f"content_html must be a string, got {type(content_html)}")
    if not isinstance(tags, str):
        raise TypeError(f"tags must be a string, got {type(tags)}")

    visible_text = strip_html(content_html)
    return build_searchable_text_casefold_from_plaintext(visible_text, tags)
