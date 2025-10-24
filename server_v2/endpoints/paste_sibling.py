from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdPasteSibling(QueryCommand):
    def describe(self) -> str:
        return "CmdPasteSibling()"

    def execute(self):
        raise NotImplementedError("paste sibling not implemented")

