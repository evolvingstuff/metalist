from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from server_v2.endpoints.base import QueryCommand
from server_v2.sync import acquire_note_lock, release_note_lock, get_current_sync_uuid


@dataclass
class CmdAcquireLock(QueryCommand):
    note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdAcquireLock(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, object]:
        success, _ = acquire_note_lock(self.note_id, self.client_id)
        if not success:
            return {"success": False, "conflict": True, "updateUUID": get_current_sync_uuid()}
        return {"success": True, "updateUUID": get_current_sync_uuid()}


@dataclass
class CmdReleaseLock(QueryCommand):
    note_id: str
    client_id: str

    def describe(self) -> str:
        return f"CmdReleaseLock(note={self.note_id}, client={self.client_id})"

    def execute(self) -> Dict[str, object]:
        release_note_lock(self.note_id, self.client_id)
        return {"success": True, "updateUUID": get_current_sync_uuid()}
