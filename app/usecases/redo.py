from __future__ import annotations

from dataclasses import dataclass
from app.usecases.base import QueryCommand
from app.services.undo_state import redo as do_redo, maybe_reset_on_context
from app.services.sync import get_current_sync_uuid


@dataclass
class CmdRedo(QueryCommand):
    client_id: str
    search_context: str = ""

    def describe(self) -> str:
        return f"CmdRedo(client={self.client_id})"

    def execute(self):
        maybe_reset_on_context(self.client_id, self.search_context)
        ok = bool(do_redo(self.client_id))
        if ok:
            return {
                "status": "success",
                "message": "Redo successful",
                "updateUUID": get_current_sync_uuid(),
            }
        else:
            return {
                "status": "noop",
                "message": "No actions to redo",
                "updateUUID": get_current_sync_uuid(),
            }
