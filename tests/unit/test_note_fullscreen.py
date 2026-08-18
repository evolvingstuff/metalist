from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

import app.api.routes.notes as notes_route
import app.services.note_fullscreen as fullscreen_module


@dataclass(frozen=True)
class _Note:
    id: str
    parent_id: Optional[str]
    content: str
    tags: str


class _FakeNoteStore:
    def __init__(self, *, notes: Dict[str, _Note], children: Dict[Optional[str], List[str]]) -> None:
        self._notes = notes
        self._children = children

    def has_note(self, note_id: str) -> bool:
        return note_id in self._notes

    def get_note(self, note_id: str) -> _Note:
        return self._notes[note_id]

    def get_children(self, parent_id: Optional[str]) -> List[str]:
        return list(self._children.get(parent_id, []))


class _FakeFileRegistry:
    def has_file(self, file_id: str) -> bool:
        return False


def test_fullscreen_markup_ignores_ancestors_and_renders_all_descendants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        "parent": _Note("parent", None, "Parent must be absent", ""),
        "root": _Note("root", "parent", "Selected root", "@list-bulleted"),
        "child": _Note("child", "root", "Collapsed child", ""),
        "grandchild": _Note("grandchild", "child", "Grandchild", ""),
    }
    store = _FakeNoteStore(
        notes=notes,
        children={
            None: ["parent"],
            "parent": ["root"],
            "root": ["child"],
            "child": ["grandchild"],
        },
    )
    render_calls: list[dict[str, object]] = []

    def _render(**kwargs: object) -> str:
        render_calls.append(kwargs)
        return str(kwargs["content_html"])

    monkeypatch.setattr(fullscreen_module, "note_store", store)
    monkeypatch.setattr(fullscreen_module, "file_registry", _FakeFileRegistry())
    monkeypatch.setattr(fullscreen_module, "render_note_content_with_embeds", _render)

    markup = fullscreen_module.build_note_fullscreen_markup("root")

    assert "Parent must be absent" not in markup
    assert "Selected root" in markup
    assert "Collapsed child" in markup
    assert "Grandchild" in markup
    assert 'class="note list-bulleted"' in markup
    assert markup.count('class="note-children"') == 2
    assert [call["note_id"] for call in render_calls] == ["root", "child", "grandchild"]
    assert all(call["static_export"] is False for call in render_calls)
    assert all(call["redact_passwords"] is False for call in render_calls)


def test_fullscreen_route_requires_note_and_returns_markup(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeNoteStore(
        notes={"note-123": _Note("note-123", None, "content", "")},
        children={},
    )
    monkeypatch.setattr(notes_route, "note_store", store)
    monkeypatch.setattr(
        notes_route,
        "build_note_fullscreen_markup",
        lambda note_id: f"<article>{note_id}</article>",
    )

    assert notes_route.note_fullscreen("note-123") == {
        "html": "<article>note-123</article>",
    }

    with pytest.raises(notes_route.HTTPException) as excinfo:
        notes_route.note_fullscreen("missing")
    assert excinfo.value.status_code == 404


def test_fullscreen_markup_rejects_hierarchy_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeNoteStore(
        notes={
            "root": _Note("root", None, "Root", ""),
            "child": _Note("child", "root", "Child", ""),
        },
        children={"root": ["child"], "child": ["root"]},
    )
    monkeypatch.setattr(fullscreen_module, "note_store", store)
    monkeypatch.setattr(fullscreen_module, "file_registry", _FakeFileRegistry())
    monkeypatch.setattr(
        fullscreen_module,
        "render_note_content_with_embeds",
        lambda **kwargs: str(kwargs["content_html"]),
    )

    with pytest.raises(RuntimeError, match="Hierarchy cycle detected"):
        fullscreen_module.build_note_fullscreen_markup("root")
