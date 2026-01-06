from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.sync import generate_new_uuid

from app.db.session import begin_writer
from app.db.notes_sql import update_note_content as db_update_note_content
from app.security.encryption import encrypt


def apply_update_content(note_id: str, content: str) -> None:
    """Apply a content update to DB and in-memory store in a single atomic commit."""
    if not isinstance(content, str):
        raise TypeError("content must be a string")

    # Validate existence without DB reads
    try:
        _ = store.get(note_id)
    except KeyError as exc:
        raise KeyError(f"Note not found: {note_id}") from exc

    # Encrypt (or pass-through if encryption unavailable)
    ciphertext, nonce, tag = encrypt(content)
    now = datetime.now(timezone.utc)

    # Single SQL transaction
    with begin_writer() as connection:
        db_update_note_content(
            connection,
            note_id,
            content=ciphertext,
            encryption_nonce=nonce,
            encryption_tag=tag,
            updated_at=now,
        )

    # Update in-memory store only after commit
    store.update_content(note_id, content, updated_at=now)


@dataclass
class CmdUpdateContent(QueryCommand):
    note_id: str
    content: str
    client_id: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdUpdateContent(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        # Capture previous plaintext for undo recording
        prev = store.get(self.note_id).content
        apply_update_content(self.note_id, self.content)

        # Record in undo stack
        try:
            from app.services.undo_state import record_update
            record_update(
                self.client_id,
                self.note_id,
                before=prev,
                after=self.content,
                viewport=self.viewport,
            )
        except Exception:
            # Fail fast on internal errors; if undo tracking fails, surface explicitly
            raise

        update_uuid = generate_new_uuid()
        return {"status": "success", "updateUUID": update_uuid}
