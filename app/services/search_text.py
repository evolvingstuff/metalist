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


def text_term_matches(term: str, text_casefold: str) -> bool:
    """Whether a quoted search term occurs in casefolded note text.

    A term matches anywhere, also inside words ("fat" in "father"), except that a
    space at its edge marks a word boundary on that side: "fat " needs the word to
    end there (a space, punctuation or the end of the text follows), " fat" needs it
    to start there (docs/ui/search-semantics.md).
    """
    if not isinstance(term, str) or not isinstance(text_casefold, str):
        raise TypeError("text_term_matches requires strings")
    core = term.strip().casefold()
    if core == "":
        raise ValueError("A quoted search term must not be blank")
    word_starts = term.startswith(" ")
    word_ends = term.endswith(" ")
    if not word_starts and not word_ends:
        return core in text_casefold
    start = text_casefold.find(core)
    while start != -1:
        end = start + len(core)
        if _is_word_edge(text_casefold, start - 1, word_starts) and _is_word_edge(text_casefold, end, word_ends):
            return True
        start = text_casefold.find(core, start + 1)
    return False


def _is_word_edge(text: str, index: int, required: bool) -> bool:
    """Whether position `index` (just outside a match) ends a word, when required."""
    if not required:
        return True
    if index < 0 or index >= len(text):
        return True
    return not text[index].isalnum()
