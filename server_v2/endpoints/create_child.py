from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdCreateChild(QueryCommand):
    def describe(self) -> str:
        return "CmdCreateChild()"

    def execute(self):
        raise NotImplementedError("create child not implemented")

