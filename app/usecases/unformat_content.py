from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.services.html_unformatting import unformat_note_content_html
from app.services.store import store
from app.services.sync import generate_new_uuid
from app.usecases.base import QueryCommand
from app.usecases.update_content import apply_update_content


@dataclass
class CmdUnformatContent(QueryCommand):
    note_id: str
    token: str
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdUnformatContent(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        record = store.get(self.note_id)
        if not isinstance(record.content, str):
            raise TypeError("note content must be a string")
        if not isinstance(record.tags, str):
            raise TypeError("note tags must be a string")

        updated_content = unformat_note_content_html(record.content)
        if updated_content == record.content:
            return {"status": "noop", "updateUUID": generate_new_uuid()}

        apply_update_content(self.note_id, updated_content, record.tags, self.token)

        from app.services.undo_state import record_update

        record_update(
            self.client_id,
            self.undo_context,
            self.note_id,
            before=record.content,
            after=updated_content,
            before_tags=record.tags,
            after_tags=record.tags,
            viewport=self.viewport,
        )

        return {"status": "updated", "updateUUID": generate_new_uuid()}
