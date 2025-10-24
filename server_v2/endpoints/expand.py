from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import os

from server_v2.endpoints.base import QueryCommand
from server_v2.store import store
from server_v2.sync import generate_new_uuid
from server_v2.endpoints.collapse import apply_set_collapse


@dataclass
class CmdExpand(QueryCommand):
    note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdExpand(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, str]:
        before = bool(store.get(self.note_id).is_collapsed)
        if before is False:
            return {"status": "unchanged", "updateUUID": generate_new_uuid()}
        apply_set_collapse(self.note_id, False)
        after = bool(store.get(self.note_id).is_collapsed)
        if after is not False:
            print(f"FATAL: expand failed for {self.note_id}")
            os._exit(1)

        from server_v2.undo_state import record_collapse
        record_collapse(self.client_id, self.note_id, before=before, after=False)

        return {"status": "updated", "updateUUID": generate_new_uuid()}
