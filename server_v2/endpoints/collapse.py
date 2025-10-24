from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdCollapse(QueryCommand):
    def describe(self) -> str:
        return "CmdCollapse()"

    def execute(self):
        raise NotImplementedError("collapse not implemented")

