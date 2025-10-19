"""Development-time integrity guards for note operations."""

from __future__ import annotations

from typing import Optional

from app.core.config import integrity_checks_enabled
from app.db.schema import NOTES_TABLE
from app.models.database import SafeSession
from app.models.linked_list import LinkedListManager
from app.services.note_store import store as note_store
from app.models.list_traversal import ListTraversal


def should_run_integrity_checks() -> bool:
    return integrity_checks_enabled()


def snapshot_note_count(db: SafeSession) -> int:
    with SafeSession.allow_reads("integrity:snapshot"):
        row = db.connection().execute(
            f"SELECT COUNT(*) AS count FROM {NOTES_TABLE}"
        ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def assert_note_count(
    db: SafeSession,
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


def assert_linked_list_integrity(db: SafeSession, operation: str) -> None:
    # Validate every parent scope (root + each note)
    parent_ids = [None]
    with SafeSession.allow_reads("integrity:parent_ids"):
        rows = db.connection().execute(
            f"SELECT id FROM {NOTES_TABLE}"
        ).fetchall()
    parent_ids.extend(row[0] for row in rows)

    for parent_id in parent_ids:
        if not ListTraversal.validate_list(db, parent_id):
            scope = parent_id or "root"
            raise RuntimeError(
                f"Linked list integrity check failed for parent '{scope}' during '{operation}'."
            )


def count_subtree(db: SafeSession, note_id: str) -> int:
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
