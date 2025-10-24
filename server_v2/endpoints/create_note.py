from __future__ import annotations

from dataclasses import dataclass

from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdCreateNote(QueryCommand):
    def describe(self) -> str:
        return "CmdCreateNote()"

    def execute(self):
        raise NotImplementedError("create note not implemented")

