from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdExpand(QueryCommand):
    def describe(self) -> str:
        return "CmdExpand()"

    def execute(self):
        raise NotImplementedError("expand not implemented")

