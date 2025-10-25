from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict
import os

from app.usecases.base import QueryCommand
from app.services.store import store
from app.services.sync import generate_new_uuid

from app.db.session import begin_writer
from app.db.notes_sql import update_links as db_update_links


def apply_set_collapse(note_id: str, collapsed: bool) -> None:
    now = datetime.now(timezone.utc)
    with begin_writer() as connection:
        db_update_links(connection, note_id, is_collapsed=bool(collapsed), updated_at=now)
    store.set_collapsed(note_id, bool(collapsed))


@dataclass
class CmdCollapse(QueryCommand):
    note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdCollapse(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        before = bool(store.get(self.note_id).is_collapsed)
        if before is True:
            # unchanged
            return {"status": "unchanged", "updateUUID": generate_new_uuid()}
        apply_set_collapse(self.note_id, True)
        after = bool(store.get(self.note_id).is_collapsed)
        if after is not True:
            print(f"FATAL: collapse failed for {self.note_id}")
            os._exit(1)

        # record undo
        from app.services.undo_state import record_collapse
        record_collapse(self.client_id, self.note_id, before=before, after=True)

        return {"status": "updated", "updateUUID": generate_new_uuid()}
