from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional
import uuid

from app.endpoints.base import QueryCommand
from app.services.store import store, NodeRecord
from app.services.sync import generate_new_uuid

from app.db.engine import begin_writer
from app.db.notes_sql import insert_note as db_insert_note, update_links as db_update_links
from app.utils.encryption import encrypt


def apply_insert_note(note_id: str, parent_id: Optional[str], prev_id: Optional[str], next_id: Optional[str], content: str = "") -> None:
    ciphertext, nonce, tag = encrypt(content)
    now = datetime.now(timezone.utc)
    with begin_writer() as connection:
        db_insert_note(
            connection,
            note_id=note_id,
            content=ciphertext,
            encryption_nonce=nonce,
            encryption_tag=tag,
            parent_id=parent_id,
            prev_id=prev_id,
            next_id=next_id,
            is_collapsed=False,
            created_at=now,
            updated_at=now,
        )
        if prev_id:
            db_update_links(connection, prev_id, next_id=note_id, updated_at=now)
        if next_id:
            db_update_links(connection, next_id, prev_id=note_id, updated_at=now)

    store.insert_after(
        NodeRecord(
            id=note_id,
            parent_id=parent_id,
            prev_id=None,
            next_id=None,
            is_collapsed=False,
            content=content,
            created_at=now,
            updated_at=now,
        ),
        parent_id=parent_id,
        prev_id=prev_id,
    )


@dataclass
class CmdCreateNote(QueryCommand):
    first_visible_note_id: Optional[str]
    search_query: Optional[str]
    client_id: str

    def describe(self) -> str:
        return f"CmdCreateNote(client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        siblings = store.children(None)
        next_id = None
        prev_id = None
        if self.first_visible_note_id and self.first_visible_note_id in siblings:
            idx = siblings.index(self.first_visible_note_id)
            next_id = self.first_visible_note_id
            prev_id = siblings[idx - 1] if idx > 0 else None
        else:
            next_id = siblings[0] if siblings else None
            prev_id = None

        note_uuid = str(uuid.uuid4())
        content = ""
        if self.search_query and not siblings:
            trimmed = self.search_query.strip()
            if trimmed:
                content = f"<div> </div><div><br></div><div>/* text search: \"{trimmed}\" */</div>"

        apply_insert_note(note_uuid, None, prev_id, next_id, content)

        # Record for undo (delete on undo)
        from app.services.undo_state import record_create
        rec = {
            "id": note_uuid,
            "parent_id": None,
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
