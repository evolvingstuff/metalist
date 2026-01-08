from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import uuid

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.usecases.create_note import apply_insert_note


@dataclass
class CmdCreateSibling(QueryCommand):
    reference_note_id: str
    search_query: Optional[str]
    client_id: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdCreateSibling(ref={self.reference_note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        ref = store.get(self.reference_note_id)
        parent_id = ref.parent_id
        siblings = store.children(parent_id)
        if ref.id not in siblings:
            raise RuntimeError(
                "Integrity failure: reference note missing from siblings list: "
                f"note_id={ref.id} parent_id={parent_id}"
            )
        idx = siblings.index(ref.id)
        prev_id = ref.id
        next_id = siblings[idx + 1] if idx + 1 < len(siblings) else None

        note_uuid = str(uuid.uuid4())
        content = ""
        # Optional search hint only if creating under root during search
        if self.search_query and parent_id is None:
            trimmed = self.search_query.strip()
            if trimmed:
                content = f"<div> </div><div><br></div><div>/* text search: \"{trimmed}\" */</div>"

        apply_insert_note(note_uuid, parent_id, prev_id, next_id, content=content)

        from app.services.undo_state import record_create
        rec = {
            "id": note_uuid,
            "parent_id": parent_id,
            "prev_id": prev_id,
            "next_id": next_id,
            "is_collapsed": False,
            "content": content,
            "tags": "",
            "created_at": None,
            "updated_at": None,
        }
        record_create(self.client_id, rec, viewport=self.viewport)

        update_uuid = generate_new_uuid()
        return {"id": note_uuid, "status": "created", "updateUUID": update_uuid}
