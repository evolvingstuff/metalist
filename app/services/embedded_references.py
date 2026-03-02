from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from app.services.content_formatting import format_note_content_for_view
from app.utils.text_utils import strip_html


_HTML_TOKEN_SPLIT_RE = re.compile(r"(<[^>]+>)")
_FIRST_LINE_BOUNDARY_RE = re.compile(
    r"(?i)<br\s*/?>|</(?:div|p|li|h[1-6]|pre|blockquote|ul|ol|table|tr|td|th|section|article|header|footer)>\s*|\n"
)


@dataclass(frozen=True, slots=True)
class EmbedRenderContext:
    has_note: Callable[[str], bool]
    get_note: Callable[[str], object]
    get_children: Callable[[Optional[str]], List[str]]


@dataclass(frozen=True, slots=True)
class ReferenceToken:
    note_id: str
    start: int
    end: int
    is_embed: bool
    occurrence_index: int


def collect_reference_tokens_from_html(content_html: str) -> List[ReferenceToken]:
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")

    parts = _HTML_TOKEN_SPLIT_RE.split(content_html)
    tokens: List[ReferenceToken] = []
    text_offset = 0
    occurrence_index = 0
    for part in parts:
        if _is_html_segment(part):
            text_offset += len(part)
            continue
        part_tokens = _collect_reference_tokens_in_text(
            text=part,
            text_offset=text_offset,
            occurrence_start=occurrence_index,
        )
        tokens.extend(part_tokens)
        occurrence_index += len(part_tokens)
        text_offset += len(part)
    return tokens


def replace_reference_token_mode_in_html(
    *,
    content_html: str,
    reference_note_id: str,
    occurrence_index: int,
    target_mode: str,
) -> tuple[str, bool]:
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")
    if not isinstance(reference_note_id, str) or reference_note_id == "":
        raise TypeError("reference_note_id must be a non-empty string")
    if not isinstance(occurrence_index, int):
        raise TypeError("occurrence_index must be an integer")
    if occurrence_index < 0:
        raise ValueError("occurrence_index must be >= 0")
    if target_mode not in {"embed", "link"}:
        raise ValueError("target_mode must be 'embed' or 'link'")

    tokens = collect_reference_tokens_from_html(content_html)
    if occurrence_index >= len(tokens):
        return content_html, False

    token = tokens[occurrence_index]
    if token.note_id != reference_note_id:
        return content_html, False

    token_mode = "embed" if token.is_embed else "link"
    if token_mode == target_mode:
        return content_html, False

    replacement = _format_reference_token(note_id=token.note_id, mode=target_mode)
    updated_content = f"{content_html[:token.start]}{replacement}{content_html[token.end:]}"
    return updated_content, True


def render_note_content_with_embeds(
    *,
    note_id: str,
    content_html: str,
    tags: str,
    context: EmbedRenderContext,
) -> str:
    if not isinstance(note_id, str) or note_id == "":
        raise TypeError("note_id must be a non-empty string")
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")
    if not isinstance(tags, str):
        raise TypeError("tags must be a string")

    content_with_embeds = _replace_reference_tokens_in_html(
        host_note_id=note_id,
        content_html=content_html,
        context=context,
        ancestry=(note_id,),
    )
    return format_note_content_for_view(content_html=content_with_embeds, tags=tags)


def _replace_reference_tokens_in_html(
    *,
    host_note_id: str,
    content_html: str,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
) -> str:
    parts = _HTML_TOKEN_SPLIT_RE.split(content_html)
    output: List[str] = []
    occurrence_index = 0
    for part in parts:
        if _is_html_segment(part):
            output.append(part)
            continue
        replaced_text, next_occurrence_index = _replace_reference_tokens_in_text(
            host_note_id=host_note_id,
            text=part,
            context=context,
            ancestry=ancestry,
            occurrence_start=occurrence_index,
        )
        output.append(replaced_text)
        occurrence_index = next_occurrence_index
    return "".join(output)


def _replace_reference_tokens_in_text(
    *,
    host_note_id: str,
    text: str,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
    occurrence_start: int,
) -> tuple[str, int]:
    if text == "":
        return "", occurrence_start

    output: List[str] = []
    index = 0
    occurrence_index = occurrence_start
    while index < len(text):
        token_start, token_open_length, is_embed = _find_next_reference_token_start(text=text, start=index)
        if token_start is None:
            output.append(text[index:])
            break

        output.append(text[index:token_start])
        end = text.find("]]", token_start + token_open_length)
        if end == -1:
            output.append(text[token_start:])
            break

        raw_id = text[token_start + token_open_length : end]
        reference_note_id = raw_id.strip()

        if not _is_valid_embed_note_id(reference_note_id):
            output.append(text[token_start : end + 2])
            index = end + 2
            continue

        output.append(
            _render_reference_block(
                host_note_id=host_note_id,
                reference_note_id=reference_note_id,
                occurrence_index=occurrence_index,
                is_embed=is_embed,
                context=context,
                ancestry=ancestry,
            )
        )
        occurrence_index += 1
        index = end + 2

    return "".join(output), occurrence_index


def _collect_reference_tokens_in_text(
    *,
    text: str,
    text_offset: int,
    occurrence_start: int,
) -> List[ReferenceToken]:
    tokens: List[ReferenceToken] = []
    index = 0
    occurrence_index = occurrence_start
    while index < len(text):
        token_start, token_open_length, is_embed = _find_next_reference_token_start(text=text, start=index)
        if token_start is None:
            break

        token_end_inner = text.find("]]", token_start + token_open_length)
        if token_end_inner == -1:
            break

        raw_id = text[token_start + token_open_length : token_end_inner]
        note_id = raw_id.strip()
        if _is_valid_embed_note_id(note_id):
            tokens.append(
                ReferenceToken(
                    note_id=note_id,
                    start=text_offset + token_start,
                    end=text_offset + token_end_inner + 2,
                    is_embed=is_embed,
                    occurrence_index=occurrence_index,
                )
            )
            occurrence_index += 1

        index = token_end_inner + 2

    return tokens


def _find_next_reference_token_start(*, text: str, start: int) -> tuple[Optional[int], int, bool]:
    index = start
    while index < len(text):
        if text.startswith("![[", index):
            return index, 3, True
        if text.startswith("[[", index):
            return index, 2, False
        index += 1
    return None, 0, False


def _is_valid_embed_note_id(note_id: str) -> bool:
    if note_id == "":
        return False
    for ch in note_id:
        if ch.isspace():
            return False
    return True


def _render_reference_block(
    *,
    host_note_id: str,
    reference_note_id: str,
    occurrence_index: int,
    is_embed: bool,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
) -> str:
    mode = "embed" if is_embed else "link"
    target_mode = "link" if is_embed else "embed"
    toggle_symbol = "-" if is_embed else "+"
    toggle_label = "Switch to link view" if is_embed else "Switch to embedded view"
    escaped_reference_note_id = html.escape(reference_note_id, quote=True)
    escaped_host_note_id = html.escape(host_note_id, quote=True)
    note_exists = context.has_note(reference_note_id)

    wrapper_classes = "note-reference-block"
    if is_embed:
        wrapper_classes = f"{wrapper_classes} note-reference-embed note-embed-block"
    else:
        wrapper_classes = f"{wrapper_classes} note-reference-link-mode"

    if is_embed:
        body_html = _render_embed_body(
            reference_note_id=reference_note_id,
            note_exists=note_exists,
            context=context,
            ancestry=ancestry,
        )
    else:
        body_html = _render_link_body(
            reference_note_id=reference_note_id,
            note_exists=note_exists,
            context=context,
        )

    toggle_button_html = ""
    if note_exists:
        toggle_button_html = (
            f'<button type="button" class="note-reference-toggle" aria-label="{toggle_label}" title="{toggle_label}">{toggle_symbol}</button>'
        )

    return (
        f'<div class="{wrapper_classes}" '
        f'data-ref-host-note-id="{escaped_host_note_id}" '
        f'data-ref-note-id="{escaped_reference_note_id}" '
        f'data-ref-occurrence="{occurrence_index}" '
        f'data-ref-mode="{mode}" '
        f'data-ref-target-mode="{target_mode}" '
        f'data-embed-ref-id="{escaped_reference_note_id}">'
        f"{toggle_button_html}"
        f'<div class="note-reference-content">{body_html}</div>'
        "</div>"
    )


def _render_embed_body(
    *,
    reference_note_id: str,
    note_exists: bool,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
) -> str:
    escaped_note_id = html.escape(reference_note_id, quote=True)

    if reference_note_id in ancestry:
        return (
            '<div class="note-reference-marker note-embed-cycle">'
            '<span class="note-embed-marker-icon" aria-hidden="true">&#8635;</span>'
            f'<span class="note-embed-marker-text">Circular reference: {escaped_note_id}</span>'
            "</div>"
        )

    if not note_exists:
        return (
            '<div class="note-reference-marker note-embed-missing">'
            '<span class="note-embed-marker-icon" aria-hidden="true">&#9888;</span>'
            f'<span class="note-embed-marker-text">Missing reference: {escaped_note_id}</span>'
            "</div>"
        )

    root_html = _render_embedded_note_node(
        note_id=reference_note_id,
        context=context,
        ancestry=ancestry + (reference_note_id,),
        is_root=True,
    )
    return root_html


def _render_link_body(
    *,
    reference_note_id: str,
    note_exists: bool,
    context: EmbedRenderContext,
) -> str:
    escaped_note_id = html.escape(reference_note_id, quote=True)
    if not note_exists:
        return (
            '<div class="note-reference-marker note-embed-missing">'
            '<span class="note-embed-marker-icon" aria-hidden="true">&#9888;</span>'
            f'<span class="note-embed-marker-text">Missing reference: {escaped_note_id}</span>'
            "</div>"
        )

    record = context.get_note(reference_note_id)
    record_content = record.content
    if not isinstance(record_content, str):
        raise TypeError("linked note content must be a string")
    preview = _extract_first_line_preview(record_content)
    if preview == "":
        preview = "(empty note)"
    escaped_preview = html.escape(preview)
    return (
        f'<a href="#" class="note-reference-link" data-ref-note-id="{escaped_note_id}">'
        f"{escaped_preview}"
        "</a>"
    )


def _render_embedded_note_node(
    *,
    note_id: str,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
    is_root: bool,
) -> str:
    record = context.get_note(note_id)
    record_content = record.content
    record_tags = record.tags
    if not isinstance(record_content, str):
        raise TypeError("embedded note content must be a string")
    if not isinstance(record_tags, str):
        raise TypeError("embedded note tags must be a string")

    rendered_content = _replace_reference_tokens_in_html(
        host_note_id=note_id,
        content_html=record_content,
        context=context,
        ancestry=ancestry,
    )
    rendered_content = format_note_content_for_view(
        content_html=rendered_content,
        tags=record_tags,
    )

    escaped_note_id = html.escape(note_id, quote=True)
    classes = "note-embed-node"
    if is_root:
        classes = f"{classes} note-embed-root"

    children_html = ""
    child_ids = context.get_children(note_id)
    if child_ids:
        child_parts: List[str] = []
        for child_id in child_ids:
            child_parts.append(
                _render_embedded_note_node(
                    note_id=child_id,
                    context=context,
                    ancestry=ancestry + (child_id,),
                    is_root=False,
                )
            )
        children_html = f'<div class="note-embed-children">{"".join(child_parts)}</div>'

    return (
        f'<div class="{classes}" data-embed-note-id="{escaped_note_id}">'
        f'<div class="note-embed-content">{rendered_content}</div>'
        f"{children_html}"
        "</div>"
    )


def _extract_first_line_preview(content_html: str) -> str:
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")
    if content_html == "":
        return ""

    for segment in _FIRST_LINE_BOUNDARY_RE.split(content_html):
        preview = strip_html(segment)
        if preview:
            return preview
    return strip_html(content_html)


def _format_reference_token(*, note_id: str, mode: str) -> str:
    if mode == "embed":
        return f"![[{note_id}]]"
    if mode == "link":
        return f"[[{note_id}]]"
    raise ValueError("mode must be 'embed' or 'link'")


def _is_html_segment(value: str) -> bool:
    return value.startswith("<") and value.endswith(">")
