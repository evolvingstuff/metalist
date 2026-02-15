from __future__ import annotations


class MCPToolError(RuntimeError):
    """Expected tool-level error surfaced to MCP clients."""


class InvalidArgumentsError(MCPToolError):
    """Tool arguments failed schema or type checks."""


class VaultNotReadyError(MCPToolError):
    """Note data is unavailable because the vault is locked/unhydrated."""


class NoteNotFoundError(MCPToolError):
    """Requested note ID does not exist in the in-memory store."""

