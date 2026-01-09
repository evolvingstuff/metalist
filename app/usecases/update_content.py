from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.sync import generate_new_uuid

from app.db.session import begin_writer
from app.db.notes_sql import update_note_fields as db_update_note_fields
from app.security.encryption import encrypt


def apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
    """Apply a content+tags update to DB and in-memory store in a single atomic commit."""
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    if not isinstance(tags, str):
        raise TypeError("tags must be a string")

    # Validate existence without DB reads
    if not store.contains(note_id):
        raise KeyError(f"Note not found: {note_id}")

    # Encrypt (or pass-through if encryption unavailable)
    ciphertext, nonce, tag = encrypt(content, token)
    tags_ciphertext, tags_nonce, tags_tag = encrypt(tags, token)
    now = datetime.now(timezone.utc)

    # Single SQL transaction
    with begin_writer() as connection:
        db_update_note_fields(
            connection,
            note_id,
            content=ciphertext,
            encryption_nonce=nonce,
            encryption_tag=tag,
            tags=tags_ciphertext,
            tags_encryption_nonce=tags_nonce,
            tags_encryption_tag=tags_tag,
            updated_at=now,
        )

    # Update in-memory store only after commit
    store.update_content_and_tags(note_id, content, tags, updated_at=now)


@dataclass
class CmdUpdateContent(QueryCommand):
    note_id: str
    content: str
    tags: str
    token: str
    client_id: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdUpdateContent(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        # Capture previous plaintext for undo recording
        record = store.get(self.note_id)
        prev = record.content
        prev_tags = record.tags
        apply_update_content(self.note_id, self.content, self.tags, self.token)

        # Record in undo stack
        from app.services.undo_state import record_update
        record_update(
            self.client_id,
            self.note_id,
            before=prev,
            after=self.content,
            before_tags=prev_tags,
            after_tags=self.tags,
            viewport=self.viewport,
        )

        update_uuid = generate_new_uuid()
        return {"status": "success", "updateUUID": update_uuid}
