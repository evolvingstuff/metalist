from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdDeleteSubtree(QueryCommand):
    def describe(self) -> str:
        return "CmdDeleteSubtree()"

    def execute(self):
        raise NotImplementedError("delete subtree not implemented")

