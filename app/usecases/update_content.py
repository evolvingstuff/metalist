from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.sync import generate_new_uuid

from app.db.session import begin_writer
from app.db.notes_sql import update_note_fields as db_update_note_fields
from app.db.notes_sql import update_note_fields_preserving_updated_at as db_update_note_fields_preserving_updated_at
from app.security.encryption import encrypt
from app.security.note_html import sanitize_note_html


def apply_update_content(note_id: str, content: str, tags: str, token: str) -> None:
    """Apply a content+tags update to DB and in-memory store in a single atomic commit."""
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    if not isinstance(tags, str):
        raise TypeError("tags must be a string")
    sanitized_content = sanitize_note_html(content)

    # Validate existence without DB reads
    if not store.contains(note_id):
        raise KeyError(f"Note not found: {note_id}")

    record = store.get(note_id)
    content_changed = record.content != sanitized_content
    tags_changed = record.tags != tags
    if not content_changed and not tags_changed:
        return

    tags_ciphertext, tags_nonce, tags_tag = encrypt(tags, token)
    if content_changed:
        ciphertext, nonce, tag = encrypt(sanitized_content, token)
        updated_at = datetime.now(timezone.utc)
    else:
        updated_at = record.updated_at
        if updated_at is None:
            raise RuntimeError(f"Cannot preserve missing updated_at for tag-only update: {note_id}")

    # Single SQL transaction
    with begin_writer() as connection:
        if content_changed:
            db_update_note_fields(
                connection,
                note_id,
                content=ciphertext,
                encryption_nonce=nonce,
                encryption_tag=tag,
                tags=tags_ciphertext,
                tags_encryption_nonce=tags_nonce,
                tags_encryption_tag=tags_tag,
                updated_at=updated_at,
            )
        else:
            db_update_note_fields_preserving_updated_at(
                connection,
                note_id,
                tags=tags_ciphertext,
                tags_encryption_nonce=tags_nonce,
                tags_encryption_tag=tags_tag,
            )

    # Update in-memory store only after commit
    store.update_content_and_tags(note_id, sanitized_content, tags, updated_at=updated_at)


@dataclass
class CmdUpdateContent(QueryCommand):
    note_id: str
    content: str
    tags: str
    token: str
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdUpdateContent(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        # Capture previous plaintext for undo recording
        record = store.get(self.note_id)
        prev = record.content
        prev_tags = record.tags
        sanitized_content = sanitize_note_html(self.content)
        apply_update_content(self.note_id, sanitized_content, self.tags, self.token)

        # Record in undo stack
        from app.services.undo_state import record_update
        record_update(
            self.client_id,
            self.undo_context,
            self.note_id,
            before=prev,
            after=sanitized_content,
            before_tags=prev_tags,
            after_tags=self.tags,
            viewport=self.viewport,
        )

        update_uuid = generate_new_uuid()
        return {"status": "success", "updateUUID": update_uuid}
