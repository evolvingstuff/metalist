from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdPasteChild(QueryCommand):
    def describe(self) -> str:
        return "CmdPasteChild()"

    def execute(self):
        raise NotImplementedError("paste child not implemented")

