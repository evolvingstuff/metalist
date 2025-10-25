from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import uuid

from server_v2.endpoints.base import QueryCommand
from server_v2.store import store, NodeRecord
from server_v2.sync import get_clipboard, generate_new_uuid
from server_v2.endpoints.create_note import apply_insert_note
from server_v2.endpoints.paste_sibling import _insert_cloned_subtree_at
from server_v2.endpoints.delete_subtree import _collect_subtree_ids
from server_v2.undo_state import record_paste


@dataclass
class CmdPasteChild(QueryCommand):
    target_note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdPasteChild(target={self.target_note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        snapshot = get_clipboard(self.client_id)
        if not snapshot:
            raise RuntimeError("Clipboard empty")

        target = store.get(self.target_note_id)
        children = store.children(target.id)
        prev_id = None
        new_root_id = _insert_cloned_subtree_at(snapshot, target.id, prev_id)

        new_ids = _collect_subtree_ids(new_root_id)
        records: List[NodeRecord] = [store.get(nid) for nid in new_ids]
        record_paste(self.client_id, records)

        return {"status": "pasted", "id": new_root_id, "updateUUID": generate_new_uuid()}
