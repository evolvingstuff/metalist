from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.endpoints.base import QueryCommand
from app.services.sync import get_current_sync_uuid


@dataclass
class CmdCheckUpdates(QueryCommand):
    client_id: str
    last_update_uuid: str

    def describe(self) -> str:
        return f"CmdCheckUpdates(client={self.client_id})"

    def execute(self) -> Dict[str, object]:
        current = get_current_sync_uuid()
        needs = bool(self.last_update_uuid) and self.last_update_uuid != current
        return {"needsUpdate": needs, "currentUpdateUUID": current}
