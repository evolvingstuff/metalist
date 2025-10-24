from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdCopyNote(QueryCommand):
    def describe(self) -> str:
        return "CmdCopyNote()"

    def execute(self):
        raise NotImplementedError("copy note not implemented")

