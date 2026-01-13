from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.usecases import delete_subtree


def test_snapshot_subtree_does_not_construct_note_record(monkeypatch: pytest.MonkeyPatch) -> None:
    child_map = {
        "root": ["child"],
        "child": [],
    }
    record_map = {
        "root": SimpleNamespace(
            id="root",
            parent_id=None,
            prev_id=None,
            next_id=None,
            is_collapsed=False,
            content="root content",
            tags="@root",
            created_at=None,
            updated_at=None,
        ),
        "child": SimpleNamespace(
            id="child",
            parent_id="root",
            prev_id=None,
            next_id=None,
            is_collapsed=False,
            content="child content",
            tags="@child",
            created_at=None,
            updated_at=None,
        ),
    }

    class FakeStore:
        def children(self, note_id: str) -> list[str]:
            return list(child_map[note_id])

        def get(self, note_id: str) -> SimpleNamespace:
            return record_map[note_id]

    monkeypatch.setattr(delete_subtree, "store", FakeStore())
    monkeypatch.setattr(
        delete_subtree,
        "NodeRecord",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("_snapshot_subtree should not instantiate NodeRecord")
        ),
    )

    snapshot = delete_subtree._snapshot_subtree("root")
    assert {rec.id for rec in snapshot} == {"root", "child"}

