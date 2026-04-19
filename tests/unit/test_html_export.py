from __future__ import annotations

import base64
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest

import app.services.html_export as export_module
import app.services.snapshot as snapshot_module
from app.services.html_export import build_notes_export_document
from app.services.search_index import SearchIndex
from app.services.search_index import SearchRecord
from app.services.search_index import extract_tags_for_search


@dataclass(frozen=True)
class _Note:
    id: str
    parent_id: Optional[str]
    prev_id: Optional[str]
    next_id: Optional[str]
    is_collapsed: bool
    content: str
    tags: str


class _FakeNoteStore:
    def __init__(self, *, notes: Dict[str, _Note], children_by_parent: Dict[Optional[str], List[str]]):
        self._notes = notes
        self._children_by_parent = children_by_parent

    def has_note(self, note_id: str) -> bool:
        return note_id in self._notes

    def get_note(self, note_id: str) -> _Note:
        return self._notes[note_id]

    def get_children(self, parent_id: Optional[str]) -> List[str]:
        return list(self._children_by_parent.get(parent_id, []))


class _FakeFileRegistry:
    def __init__(self, file_ids: set[str]) -> None:
        self._file_ids = file_ids

    def has_file(self, file_id: str) -> bool:
        return file_id in self._file_ids


def test_build_notes_export_document_expands_collapsed_notes_and_redacts_passwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        "root": _Note("root", None, None, None, True, "<div>Parent</div>", ""),
        "child": _Note("child", "root", None, None, False, "<div>sekret</div>", "@password"),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["root"], "root": ["child"]},
    )

    monkeypatch.setattr(export_module, "note_store", store)
    monkeypatch.setattr(export_module, "file_registry", _FakeFileRegistry(set()))

    html = build_notes_export_document(search=None, theme="light", token="token")

    assert 'data-theme="light"' in html
    assert "Parent" in html
    assert "meta-credential-password" in html
    assert "sekret" not in html
    assert "XXXXXX" in html
    assert '<button class="note-collapse-toggle"' not in html
    assert 'class="note-children"' in html
    assert "filter: blur(4px)" in html
    assert 'id="login-page"' not in html
    assert 'id="main-app"' not in html
    assert 'id="search-input"' not in html
    assert "\n" in html
    assert '  <main id="notes-container">' in html
    assert '    <article class="note" id="note-root">' in html
    assert '      <div class="note-content">' in html


def test_build_notes_export_document_uses_search_scope_and_static_reference_markup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_id = "f9989d26-5ec9-4b09-9647-909c58ad997a"
    notes = {
        "a": _Note("a", None, None, "b", False, f"<div>[[b]] ![[{file_id}]]</div>", "match"),
        "b": _Note("b", None, "a", None, False, "<div>linked first line</div><div>linked second line</div>", ""),
        "c": _Note("c", "a", None, None, False, "<div>hidden child</div>", ""),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["a", "b"], "a": ["c"]},
    )
    index = SearchIndex()
    index.rebuild(
        [
            SearchRecord(
                note_id=note.id,
                content_text=note.content,
                tags=note.tags,
                tag_terms=extract_tags_for_search(note.tags),
            )
            for note in notes.values()
        ],
        progress_update=lambda _: None,
        progress_interval=1000,
    )
    file_record = SimpleNamespace(
        id=file_id,
        title="photo.png",
        original_filename="photo.png",
        mime_type="image/png",
        size_bytes=8192,
        thumbnail_kind="image",
    )

    monkeypatch.setattr(export_module, "note_store", store)
    monkeypatch.setattr(snapshot_module, "note_store", store)
    monkeypatch.setattr(snapshot_module, "search_index", index)
    monkeypatch.setattr(export_module, "file_registry", _FakeFileRegistry({file_id}))
    monkeypatch.setattr(export_module, "get_file_reference_record", lambda file_id, token: file_record)
    monkeypatch.setattr(
        export_module,
        "download_file",
        lambda file_id, token: SimpleNamespace(record=file_record, content_bytes=b"png-bytes"),
    )

    html = build_notes_export_document(search="match", theme="dark", token="token")

    assert 'data-theme="dark"' in html
    assert "linked first line" in html
    assert "linked second line" not in html
    assert "hidden child" not in html
    assert 'class="note-reference-toggle"' not in html
    assert "download image" not in html
    assert "Image attachment: photo.png" not in html
    assert "note-file-image-static" in html
    assert 'src="data:image/png;base64,' in html
    assert base64.b64encode(b"png-bytes").decode("ascii") in html
    assert 'id="login-page"' not in html
    assert 'id="main-app"' not in html


def test_build_notes_export_document_redacts_password_reference_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        "a": _Note("a", None, None, "b", False, "<div>[[b]]</div>", ""),
        "b": _Note("b", None, "a", None, False, "<div>sekret</div>", "@password"),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["a", "b"]},
    )

    monkeypatch.setattr(export_module, "note_store", store)
    monkeypatch.setattr(snapshot_module, "note_store", store)
    monkeypatch.setattr(export_module, "file_registry", _FakeFileRegistry(set()))

    html = build_notes_export_document(search=None, theme="light", token="token")

    assert "sekret" not in html
    assert "XXXXXX" in html
    assert "note-reference-link-static meta-credential-password" in html
    assert 'id="login-page"' not in html
    assert 'id="main-app"' not in html


def test_build_notes_export_document_renders_markdown_meta_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        "root": _Note(
            "root",
            None,
            None,
            None,
            False,
            "<div># Title</div><div>Paragraph with [docs](https://example.com)</div><div>- one</div><div>- two</div>",
            "@markdown",
        ),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["root"]},
    )

    monkeypatch.setattr(export_module, "note_store", store)
    monkeypatch.setattr(export_module, "file_registry", _FakeFileRegistry(set()))

    html = build_notes_export_document(search=None, theme="light", token="token")

    assert 'data-markdown-rendered="true"' in html
    assert "<h1>Title</h1>" in html
    assert '<ul><li>one</li><li>two</li></ul>' in html
    assert (
        '<a href="https://example.com" target="_blank" rel="noopener noreferrer">docs</a>'
        in html
    )
    assert "# Title" not in html


def test_build_notes_export_document_renders_latex_meta_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        "root": _Note(
            "root",
            None,
            None,
            None,
            False,
            "<div>\\frac{1}{2}</div>",
            "@latex",
        ),
    }
    store = _FakeNoteStore(
        notes=notes,
        children_by_parent={None: ["root"]},
    )

    monkeypatch.setattr(export_module, "note_store", store)
    monkeypatch.setattr(export_module, "file_registry", _FakeFileRegistry(set()))

    html = build_notes_export_document(search=None, theme="dark", token="token")

    assert '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">' in html
    assert "<mfrac>" in html
    assert "\\frac{1}{2}" not in html
