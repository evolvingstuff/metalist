from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdMove(QueryCommand):
    def describe(self) -> str:
        return "CmdMove()"

    def execute(self):
        raise NotImplementedError("move note not implemented")

