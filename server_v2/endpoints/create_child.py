from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import uuid

from server_v2.endpoints.base import QueryCommand
from server_v2.store import store
from server_v2.sync import generate_new_uuid
from server_v2.endpoints.create_note import apply_insert_note


@dataclass
class CmdCreateChild(QueryCommand):
    parent_note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdCreateChild(parent={self.parent_note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        parent = store.get(self.parent_note_id)
        children = store.children(parent.id)
        prev_id = None
        next_id = children[0] if children else None

        note_uuid = str(uuid.uuid4())
        content = ""
        apply_insert_note(note_uuid, parent.id, prev_id, next_id, content)

        from server_v2.undo_state import record_create
        rec = {
            "id": note_uuid,
            "parent_id": parent.id,
            "prev_id": prev_id,
            "next_id": next_id,
            "is_collapsed": False,
            "content": content,
            "created_at": None,
            "updated_at": None,
        }
        record_create(self.client_id, rec)

        update_uuid = generate_new_uuid()
        return {"id": note_uuid, "status": "created", "updateUUID": update_uuid}
