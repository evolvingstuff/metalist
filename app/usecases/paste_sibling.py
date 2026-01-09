from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import uuid

from app.usecases.base import QueryCommand
from app.services.store import store, NodeRecord
from app.services.sync import get_clipboard, generate_new_uuid
from app.usecases.create_note import apply_insert_note
from app.usecases.delete_subtree import _collect_subtree_ids
from app.services.undo_state import record_paste


def _insert_cloned_subtree_at(
    snapshot: List[dict],
    dest_parent: Optional[str],
    dest_prev: Optional[str],
) -> str:
    if not isinstance(snapshot, list) or not snapshot:
        raise ValueError("Clipboard snapshot must be a non-empty list")
    for entry in snapshot:
        if not isinstance(entry, dict):
            raise ValueError("Clipboard snapshot entries must be objects")

    # Map old->new ids
    id_map: Dict[str, str] = {}
    # Track last inserted child per parent
    last_per_parent: Dict[Optional[str], Optional[str]] = {}
    last_per_parent[dest_parent] = dest_prev

    new_root_id: Optional[str] = None
    snapshot_ids: set[str] = set()
    for rec in snapshot:
        if "id" not in rec:
            raise ValueError("Clipboard snapshot missing required key: id")
        note_id = rec["id"]
        if not isinstance(note_id, str) or not note_id:
            raise ValueError("Clipboard snapshot id must be a non-empty string")
        snapshot_ids.add(note_id)

    for rec in snapshot:
        old_id = rec["id"]
        new_id = str(uuid.uuid4())
        id_map[old_id] = new_id

        if "parent_id" not in rec:
            raise ValueError("Clipboard snapshot missing required key: parent_id")
        old_parent = rec["parent_id"]
        if old_parent is None or old_parent not in snapshot_ids:
            new_parent = dest_parent
        elif old_parent in id_map:
            new_parent = id_map[old_parent]
        else:
            raise RuntimeError(
                f"Clipboard snapshot missing parent {old_parent} for node {old_id}"
            )

        prev_id = last_per_parent[new_parent]
        # Compute next from current store state
        if prev_id is None:
            children = store.children(new_parent)
            next_id = None
            if children:
                next_id = children[0]
        else:
            links = store._links.get(new_parent)  # type: ignore[attr-defined]
            if links is None:
                raise RuntimeError(f"Missing link scope for parent_id={new_parent}")
            prev_link = links.get(prev_id)
            if prev_link is None:
                raise RuntimeError(f"Missing prev_id={prev_id} in links for parent_id={new_parent}")
            next_id = prev_link.get('next')

        if "content" not in rec:
            raise ValueError("Clipboard snapshot missing required key: content")
        content = rec["content"]
        if not isinstance(content, str):
            raise ValueError("Clipboard snapshot content must be a string")

        if "tags" not in rec:
            raise ValueError("Clipboard snapshot missing required key: tags")
        tags = rec["tags"]
        if not isinstance(tags, str):
            raise ValueError("Clipboard snapshot tags must be a string")

        apply_insert_note(new_id, new_parent, prev_id, next_id, content=content, tags=tags)

        last_per_parent[new_parent] = new_id
        if new_root_id is None and new_parent == dest_parent:
            new_root_id = new_id

    if new_root_id is None:
        raise RuntimeError("Clipboard paste did not produce a new root id")
    return new_root_id


@dataclass
class CmdPasteSibling(QueryCommand):
    target_note_id: str
    client_id: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdPasteSibling(target={self.target_note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        snapshot = get_clipboard(self.client_id)
        if not snapshot:
            raise RuntimeError("Clipboard empty")

        target = store.get(self.target_note_id)
        siblings = store.children(target.parent_id)
        if target.id not in siblings:
            raise RuntimeError(
                "Integrity failure: paste target missing from siblings list: "
                f"note_id={target.id} parent_id={target.parent_id}"
            )
        prev_id = target.id
        new_root_id = _insert_cloned_subtree_at(snapshot, target.parent_id, prev_id)

        # Record for undo: as paste_subtree (undo deletes, redo restores)
        new_ids = _collect_subtree_ids(new_root_id)
        records: List[NodeRecord] = [store.get(nid) for nid in new_ids]
        record_paste(self.client_id, records, viewport=self.viewport)

        return {"status": "pasted", "id": new_root_id, "updateUUID": generate_new_uuid()}
