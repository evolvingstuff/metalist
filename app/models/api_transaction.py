from __future__ import annotations

import uuid
from typing import Dict

from app.db.notes_sql import fetch_all_for_cache
from app.services.content_cache import get_cached_content
from app.services.note_store import store as note_store
from app.undo_redo import Command, SnapshotRecord
from app.models.database import SafeSession


def _record_to_state(record) -> SnapshotRecord:
    return SnapshotRecord(
        id=record.id,
        content=record.content,
        parent_id=record.parent_id,
        prev_id=record.prev_id,
        next_id=record.next_id,
        is_collapsed=getattr(record, "is_collapsed", False),
        created_at=getattr(record, "created_at", None),
        updated_at=getattr(record, "updated_at", None),
    )


def _row_to_state(row: dict) -> SnapshotRecord:
    cached = get_cached_content(row["id"])
    if cached is None:
        raise RuntimeError(
            f"Cache missing plaintext for note {row['id']} during undo snapshot"
        )
    return SnapshotRecord(
        id=row["id"],
        content=cached,
        parent_id=row["parent_id"],
        prev_id=row["prev_id"],
        next_id=row["next_id"],
        is_collapsed=bool(row.get("is_collapsed", False)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _capture_snapshot(db: SafeSession) -> Dict[str, SnapshotRecord]:
    if note_store.loaded:
        snapshot = {}
        for record in note_store.snapshot().values():
            snapshot[record.id] = _record_to_state(record)
        return snapshot

    with SafeSession.allow_reads("undo:store_snapshot"):
        rows = fetch_all_for_cache(db.connection())

    return {row["id"]: _row_to_state(row) for row in rows}


def _diff_snapshots(
    before: Dict[str, SnapshotRecord],
    after: Dict[str, SnapshotRecord],
) -> tuple[Dict[str, SnapshotRecord], Dict[str, SnapshotRecord]]:
    state_before: Dict[str, SnapshotRecord] = {}
    state_after: Dict[str, SnapshotRecord] = {}

    before_ids = set(before.keys())
    after_ids = set(after.keys())

    for removed_id in before_ids - after_ids:
        state_before[removed_id] = before[removed_id]

    for added_id in after_ids - before_ids:
        state_after[added_id] = after[added_id]

    for shared_id in before_ids & after_ids:
        if before[shared_id].__dict__ != after[shared_id].__dict__:
            state_before[shared_id] = before[shared_id]
            state_after[shared_id] = after[shared_id]

    return state_before, state_after


class ApiTransaction:
    def __init__(self, db: SafeSession, transaction_manager, client_id: str | None):
        self.uuid = str(uuid.uuid4())
        self.db = db
        self.transaction_manager = transaction_manager
        self.client_id = client_id
        self._before_snapshot = _capture_snapshot(db)

    def finalize_transaction(self, action: str) -> bool:
        if not self.client_id:
            raise RuntimeError(
                f"🚨 FATAL: Transaction {self.uuid} finalized without client_id!"
            )

        after_snapshot = _capture_snapshot(self.db)
        state_before, state_after = _diff_snapshots(
            self._before_snapshot, after_snapshot
        )

        if not state_before and not state_after:
            return False

        command = Command(state_before, state_after, action)
        self.transaction_manager.add_command_to_stack(command, self.client_id)
        return True
