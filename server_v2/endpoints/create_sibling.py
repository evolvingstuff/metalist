from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdCreateSibling(QueryCommand):
    def describe(self) -> str:
        return "CmdCreateSibling()"

    def execute(self):
        raise NotImplementedError("create sibling not implemented")

