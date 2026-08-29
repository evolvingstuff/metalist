"""Render AI chat Markdown with readable note mentions and reference links."""

from __future__ import annotations

import html
import re
from collections.abc import Callable

from app.services.embedded_references import EmbedRenderContext
from app.services.embedded_references import get_note_reference_preview
from app.services.embedded_references import render_compact_note_reference_link
from app.services.markdown_rendering import render_markdown_to_html
from app.services.note_store import NoteStore


_UUID_DASH_CHARACTERS = "-‐‑‒–—−"
_UUID_SEPARATOR_PATTERN = f"[{re.escape(_UUID_DASH_CHARACTERS)}]"
_UUID_BOUNDARY_PATTERN = f"0-9a-fA-F{re.escape(_UUID_DASH_CHARACTERS)}"
_UUID_PATTERN = (
    rf"[0-9a-fA-F]{{8}}{_UUID_SEPARATOR_PATTERN}"
    rf"[0-9a-fA-F]{{4}}{_UUID_SEPARATOR_PATTERN}"
    rf"[0-9a-fA-F]{{4}}{_UUID_SEPARATOR_PATTERN}"
    rf"[0-9a-fA-F]{{4}}{_UUID_SEPARATOR_PATTERN}"
    r"[0-9a-fA-F]{12}"
)
_NOTE_CITATION_RE = re.compile(
    rf"\[\[(?P<reference>{_UUID_PATTERN})\]\]"
    rf"|(?<![{_UUID_BOUNDARY_PATTERN}])(?P<bare>{_UUID_PATTERN})"
    rf"(?![{_UUID_BOUNDARY_PATTERN}])"
)
_BRACKETED_NOTE_CITATION_RE = re.compile(rf"\[\[{_UUID_PATTERN}\]\]")
_FENCE_MARKER_RE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})")
_HTML_SEGMENT_RE = re.compile(r"(<[^>]+>)")
_OPEN_TAG_RE = re.compile(r"^<\s*([a-zA-Z][a-zA-Z0-9:-]*)\b")
_CLOSE_TAG_RE = re.compile(r"^<\s*/\s*([a-zA-Z][a-zA-Z0-9:-]*)\s*>")
_VOID_TAGS = frozenset({"br", "hr", "img"})
_CITATION_SUPPRESSING_TAGS = frozenset({"a", "code", "pre"})
_UUID_DASH_TRANSLATION = str.maketrans(
    {
        dash_character: "-"
        for dash_character in _UUID_DASH_CHARACTERS
        if dash_character != "-"
    }
)


def render_ai_chat_markdown_to_html(
    markdown_text: str,
    *,
    notes: NoteStore,
    allowed_note_ids: frozenset[str],
) -> str:
    _validate_allowed_note_ids(allowed_note_ids)
    rendered_html = render_markdown_to_html(markdown_text)
    if rendered_html == "":
        return ""
    context = EmbedRenderContext(
        has_note=notes.has_note,
        get_note=notes.get_note,
        get_children=lambda _parent_id: [],
        has_file=lambda _file_id: False,
        get_file=_reject_file_reference,
    )
    body_html, cited_note_ids = _replace_note_citations(
        rendered_html=rendered_html,
        context=context,
        allowed_note_ids=allowed_note_ids,
    )
    if len(cited_note_ids) == 0:
        return body_html
    reference_root_ids = _resolve_reference_root_ids(
        cited_note_ids=cited_note_ids,
        context=context,
    )
    return f"{body_html}{_render_references_section(reference_root_ids, context=context)}"


def _reject_file_reference(file_id: str) -> object:
    raise RuntimeError(f"AI note citation unexpectedly resolved as file {file_id}")


def strip_note_citations_for_history(markdown_text: str) -> str:
    """Remove bracketed note-reference metadata from later model context."""
    if not isinstance(markdown_text, str) or markdown_text == "":
        raise ValueError("AI history content must be a non-empty string")
    stripped = _transform_markdown_outside_fences(
        markdown_text=markdown_text,
        transform=lambda text: _BRACKETED_NOTE_CITATION_RE.sub("", text),
    ).strip()
    if stripped == "":
        raise RuntimeError("AI response contains only note citation metadata")
    return stripped


def sanitize_ai_chat_markdown_citations(
    markdown_text: str,
    *,
    notes: NoteStore,
    allowed_note_ids: frozenset[str],
) -> str:
    """Keep only citations backed by notes retrieved during the current run."""
    if not isinstance(markdown_text, str) or markdown_text == "":
        raise ValueError("AI response content must be a non-empty string")
    _validate_allowed_note_ids(allowed_note_ids)

    def sanitize_text(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            raw_note_id = _raw_note_id_from_match(match)
            note_id = raw_note_id.translate(_UUID_DASH_TRANSLATION).lower()
            if note_id not in allowed_note_ids:
                return ""
            if not notes.has_note(note_id):
                raise RuntimeError("Allowed AI citation note is missing from NoteStore")
            return f"[[{note_id}]]"

        return _NOTE_CITATION_RE.sub(replace, text)

    sanitized = _transform_markdown_outside_fences(
        markdown_text=markdown_text,
        transform=sanitize_text,
    ).strip()
    if sanitized == "":
        raise RuntimeError("AI response contains only unauthorized note citations")
    return sanitized


def find_note_citation_ids(
    markdown_text: str,
    *,
    notes: NoteStore,
) -> frozenset[str]:
    if not isinstance(markdown_text, str) or markdown_text == "":
        raise ValueError("AI response content must be a non-empty string")
    cited_note_ids: set[str] = set()

    def collect(text: str) -> str:
        for match in _NOTE_CITATION_RE.finditer(text):
            raw_note_id = _raw_note_id_from_match(match)
            note_id = raw_note_id.translate(_UUID_DASH_TRANSLATION).lower()
            if notes.has_note(note_id):
                cited_note_ids.add(note_id)
        return text

    _transform_markdown_outside_fences(
        markdown_text=markdown_text,
        transform=collect,
    )
    return frozenset(cited_note_ids)


def _transform_markdown_outside_fences(
    *,
    markdown_text: str,
    transform: Callable[[str], str],
) -> str:
    output: list[str] = []
    fence_character = ""
    fence_length = 0
    for line in markdown_text.splitlines(keepends=True):
        marker_match = _FENCE_MARKER_RE.match(line)
        if fence_character == "":
            if marker_match is not None:
                marker = marker_match.group("marker")
                fence_character = marker[0]
                fence_length = len(marker)
                output.append(line)
                continue
            output.append(transform(line))
            continue

        output.append(line)
        if marker_match is None:
            continue
        marker = marker_match.group("marker")
        if marker[0] == fence_character and len(marker) >= fence_length:
            fence_character = ""
            fence_length = 0
    return "".join(output)


def _validate_allowed_note_ids(allowed_note_ids: frozenset[str]) -> None:
    if not isinstance(allowed_note_ids, frozenset):
        raise TypeError("allowed_note_ids must be a frozenset")
    for note_id in allowed_note_ids:
        if not isinstance(note_id, str) or note_id == "":
            raise ValueError("allowed_note_ids must contain non-empty strings")


def _raw_note_id_from_match(match: re.Match[str]) -> str:
    reference_note_id = match.group("reference")
    if reference_note_id is not None:
        return reference_note_id
    bare_note_id = match.group("bare")
    assert isinstance(bare_note_id, str) and bare_note_id != ""
    return bare_note_id


def _replace_note_citations(
    *,
    rendered_html: str,
    context: EmbedRenderContext,
    allowed_note_ids: frozenset[str],
) -> tuple[str, list[str]]:
    output: list[str] = []
    cited_note_ids: list[str] = []
    seen_note_ids: set[str] = set()
    open_tags: list[str] = []
    segments = _HTML_SEGMENT_RE.split(rendered_html)
    segment_index = 0
    while segment_index < len(segments):
        segment = segments[segment_index]
        if segment == "":
            segment_index += 1
            continue
        if not segment.startswith("<"):
            if any(tag in _CITATION_SUPPRESSING_TAGS for tag in open_tags):
                output.append(segment)
            else:
                replaced_text, segment_note_ids, _ = _replace_citations_in_text(
                    text=segment,
                    context=context,
                    allowed_note_ids=allowed_note_ids,
                )
                output.append(replaced_text)
                for note_id in segment_note_ids:
                    if note_id in seen_note_ids:
                        continue
                    seen_note_ids.add(note_id)
                    cited_note_ids.append(note_id)
            segment_index += 1
            continue

        close_match = _CLOSE_TAG_RE.match(segment)
        if close_match is not None:
            closing_tag = close_match.group(1).casefold()
            if len(open_tags) == 0 or open_tags[-1] != closing_tag:
                raise RuntimeError(
                    f"AI Markdown renderer produced mismatched closing tag {closing_tag}"
                )
            open_tags.pop()
            output.append(segment)
            segment_index += 1
            continue

        open_match = _OPEN_TAG_RE.match(segment)
        if open_match is None:
            raise RuntimeError("AI Markdown renderer produced an unrecognized HTML segment")
        opening_tag = open_match.group(1).casefold()
        can_replace_inline_code = (
            opening_tag == "code"
            and not any(tag in _CITATION_SUPPRESSING_TAGS for tag in open_tags)
            and segment_index + 2 < len(segments)
        )
        if can_replace_inline_code:
            code_text = segments[segment_index + 1]
            closing_code_segment = segments[segment_index + 2]
            closing_code_match = _CLOSE_TAG_RE.match(closing_code_segment)
            is_complete_inline_code = (
                closing_code_match is not None
                and closing_code_match.group(1).casefold() == "code"
            )
            if is_complete_inline_code:
                replaced_text, inline_note_ids, handled_note_citation = (
                    _replace_citations_in_text(
                        text=code_text,
                        context=context,
                        allowed_note_ids=allowed_note_ids,
                    )
                )
                if handled_note_citation:
                    output.append(replaced_text)
                    for note_id in inline_note_ids:
                        if note_id in seen_note_ids:
                            continue
                        seen_note_ids.add(note_id)
                        cited_note_ids.append(note_id)
                    segment_index += 3
                    continue
        if opening_tag not in _VOID_TAGS and not segment.rstrip().endswith("/>"):
            open_tags.append(opening_tag)
        output.append(segment)
        segment_index += 1

    if len(open_tags) != 0:
        raise RuntimeError(f"AI Markdown renderer left unclosed tags: {open_tags}")
    return "".join(output), cited_note_ids


def _replace_citations_in_text(
    *,
    text: str,
    context: EmbedRenderContext,
    allowed_note_ids: frozenset[str],
) -> tuple[str, list[str], bool]:
    output: list[str] = []
    cited_note_ids: list[str] = []
    handled_note_citation = False
    cursor = 0
    for match in _NOTE_CITATION_RE.finditer(text):
        output.append(text[cursor : match.start()])
        reference_note_id = match.group("reference")
        if reference_note_id is not None:
            note_id = reference_note_id
        else:
            note_id = match.group("bare")
        assert isinstance(note_id, str) and note_id != ""
        note_id = note_id.translate(_UUID_DASH_TRANSLATION).lower()
        handled_note_citation = True
        if note_id not in allowed_note_ids:
            cursor = match.end()
            continue
        if not context.has_note(note_id):
            raise RuntimeError("Allowed AI citation note is missing from NoteStore")
        preview = get_note_reference_preview(
            reference_note_id=note_id,
            context=context,
            redact_passwords=True,
        )
        output.append(
            '<span class="ai-chat-note-mention">'
            f"“{html.escape(preview)}”"
            "</span>"
        )
        cited_note_ids.append(note_id)
        cursor = match.end()
    output.append(text[cursor:])
    return "".join(output), cited_note_ids, handled_note_citation


def _render_references_section(
    cited_note_ids: list[str],
    *,
    context: EmbedRenderContext,
) -> str:
    if len(cited_note_ids) == 0:
        raise ValueError("References section requires at least one cited note")
    reference_items: list[str] = []
    for note_id in cited_note_ids:
        reference_link = render_compact_note_reference_link(
            reference_note_id=note_id,
            context=context,
            redact_passwords=True,
        )
        reference_items.append(f"<li>{reference_link}</li>")

    open_all_html = ""
    if len(cited_note_ids) > 1:
        reference_query = " OR ".join(cited_note_ids)
        escaped_query = html.escape(reference_query, quote=True)
        open_all_html = (
            '<a href="#" class="ai-chat-open-all-references" '
            f'data-ref-query="{escaped_query}">Open all references</a>'
        )

    return (
        '<section class="ai-chat-references" aria-label="References">'
        "<h4>References</h4>"
        f'<ol>{"".join(reference_items)}</ol>'
        f"{open_all_html}"
        "</section>"
    )


def _resolve_reference_root_ids(
    *,
    cited_note_ids: list[str],
    context: EmbedRenderContext,
) -> list[str]:
    if len(cited_note_ids) == 0:
        raise ValueError("Reference root resolution requires cited notes")
    root_ids: list[str] = []
    seen_root_ids: set[str] = set()
    for cited_note_id in cited_note_ids:
        current_note_id = cited_note_id
        visited_note_ids: set[str] = set()
        while True:
            if current_note_id in visited_note_ids:
                raise RuntimeError(
                    "Cycle detected while resolving AI citation root: "
                    f"{cited_note_id}"
                )
            visited_note_ids.add(current_note_id)
            record = context.get_note(current_note_id)
            parent_id = record.parent_id
            if parent_id is None:
                root_note_id = current_note_id
                break
            if not isinstance(parent_id, str) or parent_id == "":
                raise RuntimeError(
                    "AI citation note has invalid parent id: "
                    f"note_id={current_note_id} parent_id={parent_id}"
                )
            if not context.has_note(parent_id):
                raise RuntimeError(
                    "AI citation hierarchy contains a missing parent: "
                    f"note_id={current_note_id} parent_id={parent_id}"
                )
            current_note_id = parent_id
        if root_note_id in seen_root_ids:
            continue
        seen_root_ids.add(root_note_id)
        root_ids.append(root_note_id)
    return root_ids
