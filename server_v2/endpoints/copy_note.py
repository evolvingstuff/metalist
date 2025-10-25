from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from server_v2.endpoints.base import QueryCommand
from server_v2.store import store, NodeRecord
from server_v2.sync import set_clipboard, generate_new_uuid


def snapshot_subtree_preorder(root_id: str) -> List[NodeRecord]:
    result: List[NodeRecord] = []
    stack: List[str] = [root_id]
    while stack:
        nid = stack.pop()
        rec = store.get(nid)
        result.append(rec)
        children = list(reversed(store.children(nid)))
        for cid in children:
            stack.append(cid)
    return result


@dataclass
class CmdCopyNote(QueryCommand):
    note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdCopyNote(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        records = snapshot_subtree_preorder(self.note_id)
        # Convert to serializable dicts
        payload = [
            {
                "id": r.id,
                "parent_id": r.parent_id,
                "prev_id": r.prev_id,
                "next_id": r.next_id,
                "is_collapsed": bool(r.is_collapsed),
                "content": r.content,
            }
            for r in records
        ]
        set_clipboard(self.client_id, payload)
        return {"status": "copied", "updateUUID": generate_new_uuid()}
