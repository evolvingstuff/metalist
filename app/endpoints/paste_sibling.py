from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import uuid

from app.endpoints.base import QueryCommand
from app.services.store import store, NodeRecord
from app.services.sync import get_clipboard, generate_new_uuid
from app.endpoints.create_note import apply_insert_note
from app.endpoints.delete_subtree import _collect_subtree_ids
from app.services.undo_state import record_paste


def _insert_cloned_subtree_at(
    snapshot: List[dict],
    dest_parent: Optional[str],
    dest_prev: Optional[str],
) -> str:
    # Map old->new ids
    id_map: Dict[str, str] = {}
    # Track last inserted child per parent
    last_per_parent: Dict[Optional[str], Optional[str]] = {}
    last_per_parent[dest_parent] = dest_prev

    new_root_id: Optional[str] = None
    snapshot_ids = {rec.get("id") for rec in snapshot}

    for rec in snapshot:
        old_id = rec["id"]
        new_id = str(uuid.uuid4())
        id_map[old_id] = new_id

        old_parent = rec.get("parent_id")
        if old_parent is None or old_parent not in snapshot_ids:
            new_parent = dest_parent
        elif old_parent in id_map:
            new_parent = id_map[old_parent]
        else:
            raise RuntimeError(
                f"Clipboard snapshot missing parent {old_parent} for node {old_id}"
            )

        prev_id = last_per_parent.get(new_parent)
        # Compute next from current store state
        if prev_id is None:
            next_id = (store.children(new_parent)[0] if store.children(new_parent) else None)
        else:
            links = store._links.get(new_parent) or {}  # type: ignore[attr-defined]
            next_id = links.get(prev_id, {}).get('next')

        apply_insert_note(new_id, new_parent, prev_id, next_id, rec.get("content") or "")

        last_per_parent[new_parent] = new_id
        if new_root_id is None and new_parent == dest_parent:
            new_root_id = new_id

    return new_root_id or ""


@dataclass
class CmdPasteSibling(QueryCommand):
    target_note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdPasteSibling(target={self.target_note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        snapshot = get_clipboard(self.client_id)
        if not snapshot:
            raise RuntimeError("Clipboard empty")

        target = store.get(self.target_note_id)
        siblings = store.children(target.parent_id)
        idx = siblings.index(target.id) if target.id in siblings else -1
        prev_id = target.id if idx >= 0 else None
        new_root_id = _insert_cloned_subtree_at(snapshot, target.parent_id, prev_id)

        # Record for undo: as paste_subtree (undo deletes, redo restores)
        new_ids = _collect_subtree_ids(new_root_id)
        records: List[NodeRecord] = [store.get(nid) for nid in new_ids]
        record_paste(self.client_id, records)

        return {"status": "pasted", "id": new_root_id, "updateUUID": generate_new_uuid()}
