from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from app.services.content_formatting import format_note_content_for_view


_HTML_TOKEN_SPLIT_RE = re.compile(r"(<[^>]+>)")


@dataclass(frozen=True, slots=True)
class EmbedRenderContext:
    has_note: Callable[[str], bool]
    get_note: Callable[[str], object]
    get_children: Callable[[Optional[str]], List[str]]


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

    content_with_embeds = _replace_embed_tokens_in_html(
        content_html=content_html,
        context=context,
        ancestry=(note_id,),
    )
    return format_note_content_for_view(content_html=content_with_embeds, tags=tags)


def _replace_embed_tokens_in_html(
    *,
    content_html: str,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
) -> str:
    parts = _HTML_TOKEN_SPLIT_RE.split(content_html)
    output: List[str] = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            output.append(part)
            continue
        output.append(
            _replace_embed_tokens_in_text(
                text=part,
                context=context,
                ancestry=ancestry,
            )
        )
    return "".join(output)


def _replace_embed_tokens_in_text(
    *,
    text: str,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
) -> str:
    if text == "":
        return ""

    output: List[str] = []
    index = 0
    while index < len(text):
        start = text.find("![[", index)
        if start == -1:
            output.append(text[index:])
            break

        output.append(text[index:start])
        end = text.find("]]", start + 3)
        if end == -1:
            output.append(text[start:])
            break

        raw_id = text[start + 3 : end]
        embed_note_id = raw_id.strip()

        if not _is_valid_embed_note_id(embed_note_id):
            output.append(text[start : end + 2])
            index = end + 2
            continue

        output.append(
            _render_embed_block(
                embed_note_id=embed_note_id,
                context=context,
                ancestry=ancestry,
            )
        )
        index = end + 2

    return "".join(output)


def _is_valid_embed_note_id(note_id: str) -> bool:
    if note_id == "":
        return False
    for ch in note_id:
        if ch.isspace():
            return False
    return True


def _render_embed_block(
    *,
    embed_note_id: str,
    context: EmbedRenderContext,
    ancestry: Tuple[str, ...],
) -> str:
    escaped_note_id = html.escape(embed_note_id, quote=True)

    if embed_note_id in ancestry:
        return (
            '<div class="note-embed-block note-embed-cycle" '
            f'data-embed-ref-id="{escaped_note_id}">'
            '<span class="note-embed-marker-icon" aria-hidden="true">&#8635;</span>'
            f'<span class="note-embed-marker-text">Circular reference: {escaped_note_id}</span>'
            "</div>"
        )

    if not context.has_note(embed_note_id):
        return (
            '<div class="note-embed-block note-embed-missing" '
            f'data-embed-ref-id="{escaped_note_id}">'
            '<span class="note-embed-marker-icon" aria-hidden="true">&#9888;</span>'
            f'<span class="note-embed-marker-text">Missing reference: {escaped_note_id}</span>'
            "</div>"
        )

    root_html = _render_embedded_note_node(
        note_id=embed_note_id,
        context=context,
        ancestry=ancestry + (embed_note_id,),
        is_root=True,
    )
    return (
        '<div class="note-embed-block" '
        f'data-embed-ref-id="{escaped_note_id}">{root_html}</div>'
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

    rendered_content = _replace_embed_tokens_in_html(
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
