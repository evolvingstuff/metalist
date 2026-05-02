"""Development-time integrity guards for note operations."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.db.schema import NOTES_TABLE
from app.models.database import SafeSession
from app.models.linked_list import LinkedListManager
from app.services.note_store import store as note_store


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
    with SafeSession.allow_reads("integrity:parent_ids"):
        rows = db.connection().execute(
            f"SELECT id, parent_id, prev_id, next_id FROM {NOTES_TABLE}"
        ).fetchall()

    records_by_id = {row["id"]: row for row in rows}
    child_ids_by_parent: dict[str | None, list[str]] = defaultdict(list)
    for row in rows:
        child_ids_by_parent[row["parent_id"]].append(row["id"])

    for row in rows:
        parent_id = row["parent_id"]
        if parent_id is not None and parent_id not in records_by_id:
            _raise_linked_list_integrity_error(parent_id=parent_id, operation=operation)

        prev_id = row["prev_id"]
        if prev_id is not None:
            if prev_id not in records_by_id:
                _raise_linked_list_integrity_error(parent_id=parent_id, operation=operation)
            prev_row = records_by_id[prev_id]
            if (
                prev_row["parent_id"] != parent_id
                or prev_row["next_id"] != row["id"]
            ):
                _raise_linked_list_integrity_error(parent_id=parent_id, operation=operation)

        next_id = row["next_id"]
        if next_id is not None:
            if next_id not in records_by_id:
                _raise_linked_list_integrity_error(parent_id=parent_id, operation=operation)
            next_row = records_by_id[next_id]
            if (
                next_row["parent_id"] != parent_id
                or next_row["prev_id"] != row["id"]
            ):
                _raise_linked_list_integrity_error(parent_id=parent_id, operation=operation)

    for parent_id in child_ids_by_parent.keys():
        child_ids = child_ids_by_parent[parent_id]
        if not _linked_child_list_is_valid(
            child_ids=child_ids,
            records_by_id=records_by_id,
        ):
            _raise_linked_list_integrity_error(parent_id=parent_id, operation=operation)


def _linked_child_list_is_valid(*, child_ids: list[str], records_by_id) -> bool:
    if len(child_ids) == 0:
        return True

    heads = [note_id for note_id in child_ids if records_by_id[note_id]["prev_id"] is None]
    tails = [note_id for note_id in child_ids if records_by_id[note_id]["next_id"] is None]
    if len(heads) != 1 or len(tails) != 1:
        return False

    child_id_set = set(child_ids)
    seen: set[str] = set()
    current_id = heads[0]
    while True:
        if current_id in seen:
            return False
        if current_id not in child_id_set:
            return False
        seen.add(current_id)

        next_id = records_by_id[current_id]["next_id"]
        if next_id is None:
            break
        current_id = next_id

    return len(seen) == len(child_ids)


def _raise_linked_list_integrity_error(*, parent_id: str | None, operation: str) -> None:
    scope = parent_id
    if scope is None:
        scope = "root"
    raise RuntimeError(
        f"Linked list integrity check failed for parent '{scope}' during '{operation}'."
    )


def count_subtree(db: SafeSession, note_id: str) -> int:
    if note_store.loaded:
        if not note_store.has_note(note_id):
            raise ValueError(f"Note {note_id} not found")

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
