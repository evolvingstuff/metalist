from __future__ import annotations

from dataclasses import dataclass
from app.usecases.base import QueryCommand
from app.services.undo_state import undo as do_undo, maybe_reset_on_context
from app.services.sync import get_current_sync_uuid


@dataclass
class CmdUndo(QueryCommand):
    client_id: str
    search_context: str = ""

    def describe(self) -> str:
        return f"CmdUndo(client={self.client_id})"

    def execute(self):
        maybe_reset_on_context(self.client_id, self.search_context)
        scroll_restore = do_undo(self.client_id)
        if scroll_restore is not None:
            return {
                "status": "success",
                "message": "Undo successful",
                "updateUUID": get_current_sync_uuid(),
                "scrollRestore": scroll_restore,
            }
        else:
            return {
                "status": "noop",
                "message": "No actions to undo",
                "updateUUID": get_current_sync_uuid(),
            }
