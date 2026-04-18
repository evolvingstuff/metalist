from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import html
from pathlib import Path

from app.services.content_formatting import find_list_style
from app.services.embedded_references import EmbedRenderContext
from app.services.embedded_references import render_note_content_with_embeds
from app.services.file_registry import file_registry
from app.services.file_storage import get_file_reference_record
from app.services.note_store import store as note_store
from app.services.snapshot import resolve_search_scope


_VALID_EXPORT_THEMES = frozenset({"dark", "light"})
_EXPORT_STYLE_OVERRIDES = """
html {
    scrollbar-gutter: auto;
}

body.html-export-body {
    max-width: 800px;
}

.html-export-body #notes-container {
    margin-top: 0;
}

.html-export-body .note {
    transition: none;
}

.html-export-body .note:not(.editing):not(.memory-selected):not(.locked):hover:not(:has(.note:hover)) {
    border-color: #e6e6e6;
}

html[data-theme="dark"] .html-export-body .note:not(.editing):not(.memory-selected):not(.locked):hover:not(:has(.note:hover)) {
    border-color: #2a2a2a;
}

.html-export-body .note-content,
.html-export-body .note-content * {
    -webkit-user-select: text !important;
    user-select: text !important;
}

.html-export-body .note-reference-toggle,
.html-export-body .note-collapse-toggle,
.html-export-body .note-tags,
.html-export-body .lock-icon,
.html-export-body .drag-handle {
    display: none !important;
}

.html-export-body .note-file-reference-link-static,
.html-export-body .note-file-image-static {
    cursor: default;
}

.html-export-body .note-file-reference-link-static .note-file-reference-title {
    text-decoration: none;
}
"""


def build_notes_export_document(*, search: str | None, theme: str) -> str:
    if search is not None and not isinstance(search, str):
        raise TypeError("search must be a string or null")
    if not isinstance(theme, str):
        raise TypeError("theme must be a string")

    normalized_theme = theme.strip().lower()
    if normalized_theme not in _VALID_EXPORT_THEMES:
        raise ValueError("theme must be 'light' or 'dark'")

    notes_markup = _render_exported_notes_markup(search=search)
    stylesheet = _load_export_stylesheet()
    return (
        "<!DOCTYPE html>"
        f'<html lang="en" data-theme="{normalized_theme}">'
        "<head>"
        '<meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        "<title>MetaList Export</title>"
        f"<style>{stylesheet}</style>"
        "</head>"
        '<body class="html-export-body">'
        f'<main id="notes-container">{notes_markup}</main>'
        "</body>"
        "</html>"
    )


def build_notes_export_filename() -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"metalist-export-{timestamp}.html"


def _render_exported_notes_markup(*, search: str | None) -> str:
    normalized_search = search
    if normalized_search == "":
        normalized_search = None

    search_scope = resolve_search_scope(
        search=normalized_search,
        editing_note_id=None,
    )
    allowed_note_ids = search_scope.allowed_note_ids

    if search_scope.search_active:
        if search_scope.search_root_ids_ordered is None:
            root_ids = []
        else:
            root_ids = list(search_scope.search_root_ids_ordered)
    else:
        root_ids = note_store.get_children(None)

    file_record_cache: dict[str, object] = {}

    def _get_file_record(file_id: str) -> object:
        if file_id not in file_record_cache:
            file_record_cache[file_id] = get_file_reference_record(file_id, token=None)
        return file_record_cache[file_id]

    embed_render_context = EmbedRenderContext(
        has_note=note_store.has_note,
        get_note=note_store.get_note,
        get_children=note_store.get_children,
        has_file=file_registry.has_file,
        get_file=_get_file_record,
    )

    parts: list[str] = []
    for root_id in root_ids:
        if allowed_note_ids is not None and root_id not in allowed_note_ids:
            continue
        parts.append(
            _render_exported_note(
                note_id=root_id,
                allowed_note_ids=allowed_note_ids,
                embed_render_context=embed_render_context,
            )
        )
    return "".join(parts)


def _render_exported_note(
    *,
    note_id: str,
    allowed_note_ids: set[str] | None,
    embed_render_context: EmbedRenderContext,
) -> str:
    record = note_store.get_note(note_id)
    record_content = record.content
    record_tags = record.tags
    if not isinstance(record_content, str):
        raise TypeError("note content must be a string")
    if not isinstance(record_tags, str):
        raise TypeError("note tags must be a string")

    rendered_content = render_note_content_with_embeds(
        note_id=note_id,
        content_html=record_content,
        tags=record_tags,
        context=embed_render_context,
        static_export=True,
        redact_passwords=True,
    )

    classes = ["note"]
    list_style = find_list_style(record_tags)
    if list_style == "bulleted":
        classes.append("list-bulleted")
    elif list_style == "numbered":
        classes.append("list-numbered")

    children_html_parts: list[str] = []
    for child_id in note_store.get_children(note_id):
        if allowed_note_ids is not None and child_id not in allowed_note_ids:
            continue
        children_html_parts.append(
            _render_exported_note(
                note_id=child_id,
                allowed_note_ids=allowed_note_ids,
                embed_render_context=embed_render_context,
            )
        )

    children_html = ""
    if children_html_parts:
        children_html = f'<div class="note-children">{"".join(children_html_parts)}</div>'

    escaped_note_id = html.escape(note_id, quote=True)
    class_attr = " ".join(classes)
    return (
        f'<article class="{class_attr}" id="note-{escaped_note_id}">'
        f'<div class="note-content">{rendered_content}</div>'
        f"{children_html}"
        "</article>"
    )


@lru_cache(maxsize=1)
def _load_export_stylesheet() -> str:
    css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "main.css"
    if not css_path.is_file():
        raise FileNotFoundError(f"MetaList stylesheet missing at {css_path}")
    return css_path.read_text(encoding="utf-8") + "\n" + _EXPORT_STYLE_OVERRIDES
