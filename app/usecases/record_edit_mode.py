from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.services.sync import get_current_sync_uuid
from app.services.undo_state import record_edit_mode
from app.usecases.base import QueryCommand


@dataclass
class CmdRecordEditMode(QueryCommand):
    client_id: str
    undo_context: str
    before_editing_note_id: object
    after_editing_note_id: object
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdRecordEditMode(client={self.client_id})"

    def execute(self) -> Dict[str, object]:
        if not isinstance(self.undo_context, str) or self.undo_context == "":
            raise TypeError("undo_context must be a non-empty string")

        before_editing_note_id = self.before_editing_note_id
        if before_editing_note_id is not None and not isinstance(before_editing_note_id, str):
            raise TypeError("before_editing_note_id must be a string or null")
        if isinstance(before_editing_note_id, str) and before_editing_note_id == "":
            raise ValueError("before_editing_note_id must be a non-empty string or null")

        after_editing_note_id = self.after_editing_note_id
        if after_editing_note_id is not None and not isinstance(after_editing_note_id, str):
            raise TypeError("after_editing_note_id must be a string or null")
        if isinstance(after_editing_note_id, str) and after_editing_note_id == "":
            raise ValueError("after_editing_note_id must be a non-empty string or null")

        record_edit_mode(
            self.client_id,
            undo_context=self.undo_context,
            before_editing_note_id=before_editing_note_id,
            after_editing_note_id=after_editing_note_id,
            viewport=self.viewport,
        )
        return {"status": "recorded", "updateUUID": get_current_sync_uuid()}
