from __future__ import annotations

from dataclasses import dataclass
from server_v2.endpoints.base import QueryCommand


@dataclass
class CmdExportHtml(QueryCommand):
    def describe(self) -> str:
        return "CmdExportHtml()"

    def execute(self):
        raise NotImplementedError("export html not implemented")

