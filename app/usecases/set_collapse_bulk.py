from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

from app.services.store import store
from app.services.sync import generate_new_uuid
from app.services.undo_state import record_collapse
from app.usecases.base import QueryCommand
from app.usecases.collapse import apply_set_collapse


@dataclass
class CmdSetCollapseBulk(QueryCommand):
    note_ids: List[str]
    collapsed: bool
    client_id: str
    undo_context: str
    viewport: Dict[str, object]

    def describe(self) -> str:
        return f"CmdSetCollapseBulk(count={len(self.note_ids)}, collapsed={self.collapsed}, client={self.client_id})"

    def execute(self) -> Dict[str, object]:
        updated_count = 0

        for note_id in self.note_ids:
            before = bool(store.get(note_id).is_collapsed)
            if before is bool(self.collapsed):
                continue

            apply_set_collapse(note_id, bool(self.collapsed))

            after = bool(store.get(note_id).is_collapsed)
            if after is not bool(self.collapsed):
                print(f"FATAL: bulk collapse failed for {note_id}")
                os._exit(1)

            record_collapse(
                self.client_id,
                self.undo_context,
                note_id,
                before=before,
                after=after,
                viewport=self.viewport,
            )
            updated_count += 1

        status = "unchanged"
        if updated_count > 0:
            status = "updated"
        return {
            "status": status,
            "updatedCount": updated_count,
            "updateUUID": generate_new_uuid(),
        }
