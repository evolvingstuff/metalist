from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdCreateDrop(QueryCommand):
    def describe(self) -> str:
        return "CmdCreateDrop()"

    def execute(self):
        raise NotImplementedError("create drop not implemented")

