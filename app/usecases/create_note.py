from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, Optional
import uuid

from app.usecases.base import QueryCommand
from app.services.undo_state import record_create
from app.usecases.search_comment_autofill import compute_initial_tags_for_new_note
from app.services.store import store
from app.services.sync import generate_new_uuid

from app.db.session import begin_writer
from app.db.notes_sql import insert_note as db_insert_note
from app.db.notes_sql import update_links_preserving_updated_at as db_update_links_preserving_updated_at
from app.security.encryption import encrypt
from app.security.note_html import sanitize_note_html


def apply_insert_note(
    note_id: str,
    parent_id: Optional[str],
    prev_id: Optional[str],
    next_id: Optional[str],
    token: str,
    *,
    content: str,
    tags: str,
) -> None:
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    sanitized_content = sanitize_note_html(content)
    ciphertext, nonce, tag = encrypt(sanitized_content, token)
    tags_ciphertext, tags_nonce, tags_tag = encrypt(tags, token)
    now = datetime.now(timezone.utc)
    with begin_writer() as connection:
        db_insert_note(
            connection,
            note_id=note_id,
            content=ciphertext,
            encryption_nonce=nonce,
            encryption_tag=tag,
            tags=tags_ciphertext,
            tags_encryption_nonce=tags_nonce,
            tags_encryption_tag=tags_tag,
            parent_id=parent_id,
            prev_id=prev_id,
            next_id=next_id,
            is_collapsed=False,
            created_at=now,
            updated_at=now,
        )
        if prev_id:
            db_update_links_preserving_updated_at(connection, prev_id, next_id=note_id)
        if next_id:
            db_update_links_preserving_updated_at(connection, next_id, prev_id=note_id)

    store.insert_after(
        SimpleNamespace(
            id=note_id,
            content=sanitized_content,
            tags=tags,
            is_collapsed=False,
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
    token: str
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdCreateNote(client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        siblings = store.children(None)
        next_id = None
        prev_id = None
        if self.first_visible_note_id and self.first_visible_note_id in siblings:
            idx = siblings.index(self.first_visible_note_id)
            next_id = self.first_visible_note_id
            if idx > 0:
                prev_id = siblings[idx - 1]
            else:
                prev_id = None
        else:
            next_id = None
            if siblings:
                next_id = siblings[0]
            prev_id = None


        note_uuid = str(uuid.uuid4())
        content = ""
        tags = compute_initial_tags_for_new_note(
            parent_id=None,
            search_query=self.search_query,
        )

        apply_insert_note(
            note_uuid,
            None,
            prev_id,
            next_id,
            self.token,
            content=content,
            tags=tags,
        )

        # Record for undo (delete on undo)
        rec = {
            "id": note_uuid,
            "parent_id": None,
            "prev_id": prev_id,
            "next_id": next_id,
            "is_collapsed": False,
            "content": content,
            "tags": tags,
            "created_at": None,
            "updated_at": None,
        }
        record_create(self.client_id, self.undo_context, rec, viewport=self.viewport)

        update_uuid = generate_new_uuid()
        return {"id": note_uuid, "status": "created", "updateUUID": update_uuid}
