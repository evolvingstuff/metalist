from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

from app.usecases.base import QueryCommand
from app.services.store import store, NodeRecord
from app.services.sync import generate_new_uuid

from app.db.session import begin_writer
from app.db.notes_sql import update_links as db_update_links, delete_notes as db_delete_notes


def _collect_subtree_ids(root_id: str) -> List[str]:
    ids: List[str] = []
    stack: List[str] = [root_id]
    seen: set[str] = set()
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        ids.append(nid)
        for cid in store.children(nid):
            stack.append(cid)
    return ids


def _snapshot_subtree(root_id: str) -> List[NodeRecord]:
    out: List[NodeRecord] = []
    for nid in _collect_subtree_ids(root_id):
        rec = store.get(nid)
        out.append(NodeRecord(
            id=rec.id,
            parent_id=rec.parent_id,
            prev_id=rec.prev_id,
            next_id=rec.next_id,
            is_collapsed=rec.is_collapsed,
            content=rec.content,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
        ))
    return out


def apply_delete_subtree(note_id: str) -> None:
    # Validate existence and compute neighbors
    rec = store.get(note_id)
    parent_id = rec.parent_id
    siblings = store.children(parent_id)
    try:
        idx = siblings.index(note_id)
    except ValueError:
        idx = -1
    prev_id = siblings[idx - 1] if idx > 0 else None
    next_id = siblings[idx + 1] if idx >= 0 and idx + 1 < len(siblings) else None

    ids_to_delete = _collect_subtree_ids(note_id)

    with begin_writer() as connection:
        # Relink neighbors
        now = datetime.now(timezone.utc)
        if prev_id:
            db_update_links(connection, prev_id, next_id=next_id, updated_at=now)
        if next_id:
            db_update_links(connection, next_id, prev_id=prev_id, updated_at=now)
        # Delete subtree
        db_delete_notes(connection, ids_to_delete)

    # Update in-memory store after commit
    store.delete_subtree(note_id)


def apply_restore_records(records: List[NodeRecord]) -> None:
    # Reinsert records in preorder; rely on stored prev/next pointers
    from app.db.notes_sql import insert_note as db_insert_note
    from app.security.encryption import encrypt

    # Insert in DB
    with begin_writer() as connection:
        now = datetime.now(timezone.utc)
        for rec in records:
            ciphertext, nonce, tag = encrypt(rec.content or "")
            db_insert_note(
                connection,
                note_id=rec.id,
                content=ciphertext,
                encryption_nonce=nonce,
                encryption_tag=tag,
                parent_id=rec.parent_id,
                prev_id=rec.prev_id,
                next_id=rec.next_id,
                is_collapsed=rec.is_collapsed,
                created_at=rec.created_at or now,
                updated_at=now,
            )
            # Update neighbor links around this node
            if rec.prev_id:
                db_update_links(connection, rec.prev_id, next_id=rec.id, updated_at=now)
            if rec.next_id:
                db_update_links(connection, rec.next_id, prev_id=rec.id, updated_at=now)

    # Update in-memory store after commit
    store.restore_subtree(records)


@dataclass
class CmdDeleteSubtree(QueryCommand):
    note_id: str
    client_id: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdDeleteSubtree(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        # Snapshot before delete for undo
        snapshot = _snapshot_subtree(self.note_id)
        apply_delete_subtree(self.note_id)

        # Record for undo
        from app.services.undo_state import record_delete
        record_delete(self.client_id, snapshot, viewport=self.viewport)

        update_uuid = generate_new_uuid()
        return {"status": "success", "updateUUID": update_uuid}
