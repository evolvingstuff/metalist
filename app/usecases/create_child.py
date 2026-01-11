from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import uuid

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.usecases.create_note import apply_insert_note


@dataclass
class CmdCreateChild(QueryCommand):
    parent_note_id: str
    token: str
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdCreateChild(parent={self.parent_note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        parent = store.get(self.parent_note_id)
        children = store.children(parent.id)
        prev_id = None
        next_id = None
        if children:
            next_id = children[0]

        note_uuid = str(uuid.uuid4())
        content = ""
        apply_insert_note(
            note_uuid,
            parent.id,
            prev_id,
            next_id,
            self.token,
            content=content,
            tags="",
        )

        from app.services.undo_state import record_create
        rec = {
            "id": note_uuid,
            "parent_id": parent.id,
            "prev_id": prev_id,
            "next_id": next_id,
            "is_collapsed": False,
            "content": content,
            "tags": "",
            "created_at": None,
            "updated_at": None,
        }
        record_create(self.client_id, self.undo_context, rec, viewport=self.viewport)

        update_uuid = generate_new_uuid()
        return {"id": note_uuid, "status": "created", "updateUUID": update_uuid}
