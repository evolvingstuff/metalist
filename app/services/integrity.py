"""Development-time integrity guards for note operations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import integrity_checks_enabled
from app.models.database import DBNote
from app.models.linked_list import LinkedListManager
from app.services.note_store import store as note_store
from app.models.list_traversal import ListTraversal


def should_run_integrity_checks() -> bool:
    return integrity_checks_enabled()


def snapshot_note_count(db: Session) -> int:
    return db.query(DBNote).count()


def assert_note_count(
    db: Session,
    snapshot: Optional[int],
    expected_delta: Optional[int],
    operation: str,
) -> None:
    if snapshot is None or expected_delta is None:
        return

    current = snapshot_note_count(db)
    expected = snapshot + expected_delta
    if current != expected:
        raise RuntimeError(
            f"Integrity failure during '{operation}': expected note count {expected} but found {current}."
        )


def assert_linked_list_integrity(db: Session, operation: str) -> None:
    # Validate every parent scope (root + each note)
    parent_ids = [None]
    parent_ids.extend(id_ for (id_,) in db.query(DBNote.id))

    for parent_id in parent_ids:
        if not ListTraversal.validate_list(db, parent_id):
            scope = parent_id or "root"
            raise RuntimeError(
                f"Linked list integrity check failed for parent '{scope}' during '{operation}'."
            )


def count_subtree(db: Session, note_id: str) -> int:
    if note_store.loaded:
        try:
            note_store.get_note(note_id)
        except KeyError as exc:
            raise ValueError(f"Note {note_id} not found") from exc

        def _count_store(current_id: str) -> int:
            total = 1
            for child_id in note_store.get_children(current_id):
                total += _count_store(child_id)
            return total

        return _count_store(note_id)

    node = LinkedListManager.get_note(db, note_id)
    if not node:
        raise ValueError(f"Note {note_id} not found")

    def _count(current_id: str) -> int:
        note = LinkedListManager.get_note(db, current_id)
        if not note:
            return 0
        total = 1
        for child in LinkedListManager.get_ordered_child_list(db, current_id):
            total += _count(child.id)
        return total

    return _count(note_id)
