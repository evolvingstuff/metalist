"""Runtime authorization for agent tools."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.tools import ToolPermission
from app.services.agent.tools import ToolSpec


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    permission: str
    reason: str


class AgentPermissionPolicy:
    def authorize(self, *, spec: ToolSpec) -> PermissionDecision:
        if not isinstance(spec, ToolSpec):
            raise TypeError("spec must be a ToolSpec")
        if spec.mutates:
            raise PermissionError(f"Mutating agent tool is not authorized: {spec.name}")
        if spec.permission is not ToolPermission.READ:
            raise PermissionError(f"Unsupported agent tool permission: {spec.permission}")
        return PermissionDecision(
            allowed=True,
            permission=spec.permission.value,
            reason="Read-only PKMS tools run automatically",
        )
