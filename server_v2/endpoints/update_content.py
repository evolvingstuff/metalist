from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdUpdateContent(QueryCommand):
    def describe(self) -> str:
        return "CmdUpdateContent()"

    def execute(self):
        raise NotImplementedError("update content not implemented")

