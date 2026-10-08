"""Text files dropped into MetaList: their pill label and their preview note.

A dropped `.txt`, `.md`, `.csv` or `.json` file is stored like any file, and its text is
also copied into a child note of the note holding the file's pill, so it can be
read, searched and collapsed like any note. Markdown, CSV and JSON children get
the meta tag that renders them (`@markdown`, `@csv`, `@json`). The child is an ordinary note:
editing it never changes the stored file (docs/ui/references.md).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import PurePath


# Larger files keep only their pill: a preview that long is not a preview.
MAX_PREVIEW_BYTES = 200 * 1024
_UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class _TextFileKind:
    badge: str
    render_tag: str


_TEXT_FILE_KINDS_BY_EXTENSION = {
    ".txt": _TextFileKind(badge=".TXT", render_tag=""),
    ".md": _TextFileKind(badge=".MD", render_tag="@markdown"),
    ".markdown": _TextFileKind(badge=".MD", render_tag="@markdown"),
    ".csv": _TextFileKind(badge=".CSV", render_tag="@csv"),
    ".json": _TextFileKind(badge=".JSON", render_tag="@json"),
}


@dataclass(frozen=True)
class FileTextPreview:
    """What a dropped file's preview child gets, or why it gets none.

    `status` is "ready", "not_previewable" (not a .txt/.md/.csv/.json file), "too_large"
    or "not_text" (not UTF-8). Content and tags are empty unless it is "ready".
    """

    status: str
    content_html: str
    render_tag: str


def text_file_badge(original_filename: str) -> str:
    """The pill label for a previewable text file by its extension, or "" for any other file."""
    assert isinstance(original_filename, str) and original_filename != ""
    extension = PurePath(original_filename).suffix.lower()
    if extension not in _TEXT_FILE_KINDS_BY_EXTENSION:
        return ""
    return _TEXT_FILE_KINDS_BY_EXTENSION[extension].badge


def build_file_text_preview(*, original_filename: str, content_bytes: bytes) -> FileTextPreview:
    assert isinstance(original_filename, str) and original_filename != ""
    assert isinstance(content_bytes, bytes)
    extension = PurePath(original_filename).suffix.lower()
    if extension not in _TEXT_FILE_KINDS_BY_EXTENSION:
        return FileTextPreview(status="not_previewable", content_html="", render_tag="")
    if len(content_bytes) > MAX_PREVIEW_BYTES:
        return FileTextPreview(status="too_large", content_html="", render_tag="")
    text_bytes = content_bytes.removeprefix(_UTF8_BOM)
    text = text_bytes.decode("utf-8", errors="replace")
    if text.encode("utf-8") != text_bytes:
        # A user's file in another encoding: it keeps its pill without a preview.
        return FileTextPreview(status="not_text", content_html="", render_tag="")
    return FileTextPreview(
        status="ready",
        content_html=plain_text_to_note_html(text),
        render_tag=_TEXT_FILE_KINDS_BY_EXTENSION[extension].render_tag,
    )


def plain_text_to_note_html(text: str) -> str:
    """Note HTML holding `text` line for line, as the renderers read it back."""
    assert isinstance(text, str)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n")
    return "<br>".join(html.escape(line, quote=False) for line in lines)
