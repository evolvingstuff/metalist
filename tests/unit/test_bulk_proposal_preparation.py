from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.usecases.bulk_tag_proposals as bulk_tag_proposals


class _Store:
    def __init__(self, records: dict[str, SimpleNamespace]) -> None:
        self._records = records

    def get_note(self, note_id: str) -> SimpleNamespace:
        return self._records[note_id]


def _records() -> dict[str, SimpleNamespace]:
    return {
        "untouched": SimpleNamespace(tags=" {{@bold keep}} OR @red ", proposed_tags=""),
        "proposed": SimpleNamespace(tags="alpha", proposed_tags="beta gamma"),
        "already": SimpleNamespace(tags="alpha delta", proposed_tags="delta"),
    }


def test_accept_changes_only_notes_with_selected_proposals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bulk_tag_proposals, "store", _Store(_records()))

    changes, count, affected = bulk_tag_proposals.prepare_proposal_changes(
        ("untouched", "proposed", "already"), "accept", "", {},
    )

    assert "untouched" not in changes
    assert changes["proposed"] == ("alpha beta gamma", "")
    # An already-accepted proposal is cleared without rewriting the tags.
    assert changes["already"] == ("alpha delta", "")
    assert set(affected) == {"proposed", "already"}
    assert count == 3


def test_remove_leaves_tags_exactly_as_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bulk_tag_proposals, "store", _Store(_records()))

    changes, _count, affected = bulk_tag_proposals.prepare_proposal_changes(
        ("untouched", "proposed"), "remove", "", {},
    )

    assert changes == {"proposed": ("alpha", "")}
    assert set(affected) == {"proposed"}
