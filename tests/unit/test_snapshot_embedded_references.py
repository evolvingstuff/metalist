from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

from app.services.snapshot import build_view_state


@dataclass
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


HOST_ID = "11111111-1111-1111-1111-111111111111"
TARGET_ID = "22222222-2222-2222-2222-222222222222"
CHILD_ID = "33333333-3333-3333-3333-333333333333"
OTHER_ID = "44444444-4444-4444-4444-444444444444"
MISSING_ID = "99999999-9999-9999-9999-999999999999"


def _state_for(
    *,
    monkeypatch: pytest.MonkeyPatch,
    notes: Dict[str, _Note],
    children_by_parent: Dict[Optional[str], List[str]],
    **kwargs: object,
):
    editing_note_id = None
    if "editing_note_id" in kwargs:
        editing_note_id = kwargs["editing_note_id"]
    if editing_note_id is not None and not isinstance(editing_note_id, str):
        raise TypeError("editing_note_id must be a string or None")
    store = _FakeNoteStore(notes=notes, children_by_parent=children_by_parent)

    import app.services.snapshot as snapshot

    monkeypatch.setattr(snapshot, "note_store", store)
    monkeypatch.setattr(snapshot, "get_all_locks", lambda: {})
    return build_view_state(
        editing_note_id=editing_note_id,
        search=None,
        sort_mode="normal",
        date_filter=None,
        client_known_note_ids=set(),
        client_seen_root_ids=set(),
        anchor_root_id=None,
    )


def test_embed_reference_renders_as_block_and_includes_descendants(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, TARGET_ID, False, f"<div>blah ![[{TARGET_ID}]] yada</div>", ""),
        TARGET_ID: _Note(TARGET_ID, None, HOST_ID, None, True, "<div>embedded root</div>", ""),
        CHILD_ID: _Note(CHILD_ID, TARGET_ID, None, None, False, "<div>embedded child</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID, TARGET_ID], TARGET_ID: [CHILD_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "note-embed-block" in rendered
    assert f'data-embed-ref-id="{TARGET_ID}"' in rendered
    assert "embedded root" in rendered
    assert "embedded child" in rendered
    assert rendered.index("blah") < rendered.index("note-embed-block")
    assert rendered.index("note-embed-block") < rendered.index("yada")


def test_embed_reference_missing_uuid_shows_missing_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, None, False, f"<div>![[{MISSING_ID}]]</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "note-embed-missing" in rendered
    assert f"Missing reference: {MISSING_ID}" in rendered
    assert "note-reference-toggle" not in rendered


def test_link_reference_missing_uuid_shows_missing_marker_without_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, None, False, f"<div>[[{MISSING_ID}]]</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "note-embed-missing" in rendered
    assert f"Missing reference: {MISSING_ID}" in rendered
    assert "note-reference-toggle" not in rendered


def test_non_uuid_double_square_tokens_remain_literal_without_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        HOST_ID: _Note(
            HOST_ID,
            None,
            None,
            None,
            False,
            "<div>e.g. [[3]] with tag [[@counter]]</div>",
            "",
        ),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "[[3]]" in rendered
    assert "[[@counter]]" in rendered
    assert "note-embed-missing" not in rendered
    assert "Missing reference:" not in rendered


def test_scoped_double_square_latex_is_not_treated_as_link_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notes = {
        HOST_ID: _Note(
            HOST_ID,
            None,
            None,
            None,
            False,
            "<div>enqueue is [[$O(N)$]]</div>",
            "[[@LaTeX]]",
        ),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "Missing reference: $O(N)$" not in rendered
    assert "note-embed-missing" not in rendered
    assert 'class="meta-latex meta-latex-inline"' in rendered
    assert '<math xmlns="http://www.w3.org/1998/Math/MathML" display="inline">' in rendered


def test_embed_reference_cycle_shows_cycle_marker_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, None, False, f"<div>![[{TARGET_ID}]]</div>", ""),
        TARGET_ID: _Note(TARGET_ID, None, None, None, False, f"<div>![[{HOST_ID}]]</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID, TARGET_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "note-embed-block" in rendered
    assert "note-embed-cycle" in rendered
    assert f"Circular reference: {HOST_ID}" in rendered


def test_plain_reference_renders_link_mode_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, None, False, f"<div>prefix [[{TARGET_ID}]] suffix</div>", ""),
        TARGET_ID: _Note(TARGET_ID, None, None, None, False, "<div>linked first line</div><div>linked second line</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID, TARGET_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "note-reference-link-mode" in rendered
    assert "note-reference-link" in rendered
    assert "linked first line" in rendered
    assert "linked second line" not in rendered
    assert 'data-ref-mode="link"' in rendered
    assert 'data-ref-target-mode="embed"' in rendered


def test_link_mode_preview_strips_nested_reference_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    nested_ref_id = "69dc0ad7-6ad6-4be9-8ad8-7c30704e5c1a"
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, None, False, f"<div>[[{TARGET_ID}]]</div>", ""),
        TARGET_ID: _Note(
            TARGET_ID,
            None,
            None,
            None,
            False,
            f"<div>blah ![[{nested_ref_id}]]</div><div>linked second line</div>",
            "",
        ),
        nested_ref_id: _Note(nested_ref_id, None, None, None, False, "<div>child</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID, TARGET_ID, nested_ref_id]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert "note-reference-link-mode" in rendered
    assert "blah" in rendered
    assert nested_ref_id not in rendered


def test_multiple_references_expose_stable_occurrence_indices(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, None, False, f"<div>[[{TARGET_ID}]] ![[{CHILD_ID}]] [[{TARGET_ID}]]</div>", ""),
        TARGET_ID: _Note(TARGET_ID, None, None, CHILD_ID, False, "<div>B</div>", ""),
        CHILD_ID: _Note(CHILD_ID, None, TARGET_ID, None, False, "<div>C</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID, TARGET_ID, CHILD_ID]},
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert rendered.count('data-ref-occurrence="0"') == 1
    assert rendered.count('data-ref-occurrence="1"') == 1
    assert rendered.count('data-ref-occurrence="2"') == 1


def test_edit_mode_keeps_literal_embed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, TARGET_ID, False, f"<div>![[{TARGET_ID}]]</div>", ""),
        TARGET_ID: _Note(TARGET_ID, None, HOST_ID, None, False, "<div>embedded</div>", ""),
    }
    state = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent={None: [HOST_ID, TARGET_ID]},
        editing_note_id=HOST_ID,
    )

    rendered = state.payloads[HOST_ID]["content"]
    assert f"![[{TARGET_ID}]]" in rendered
    assert "note-embed-block" not in rendered


def test_embed_host_hash_changes_when_referenced_note_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = {
        HOST_ID: _Note(HOST_ID, None, None, TARGET_ID, False, f"<div>![[{TARGET_ID}]]</div>", ""),
        TARGET_ID: _Note(TARGET_ID, None, HOST_ID, None, False, "<div>before</div>", ""),
    }
    children_by_parent = {None: [HOST_ID, TARGET_ID]}
    state_one = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent=children_by_parent,
    )
    first_hash = state_one.payloads[HOST_ID]["hash"]

    notes[TARGET_ID].content = "<div>after</div>"
    state_two = _state_for(
        monkeypatch=monkeypatch,
        notes=notes,
        children_by_parent=children_by_parent,
    )
    second_hash = state_two.payloads[HOST_ID]["hash"]

    assert first_hash != second_hash
