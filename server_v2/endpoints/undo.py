from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdUndo(QueryCommand):
    def describe(self) -> str:
        return "CmdUndo()"

    def execute(self):
        raise NotImplementedError("undo not implemented")

