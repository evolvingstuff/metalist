from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdRedo(QueryCommand):
    def describe(self) -> str:
        return "CmdRedo()"

    def execute(self):
        raise NotImplementedError("redo not implemented")

