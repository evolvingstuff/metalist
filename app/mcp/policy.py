from __future__ import annotations

from typing import Iterable, Tuple


READ_ONLY_TOOL_NAMES: Tuple[str, ...] = (
    "health_check",
    "get_active_search_context",
    "count_notes",
    "get_note",
    "get_notes_batch",
    "list_children",
    "list_tags",
    "search_notes",
    "search_note_ids",
    "search_notes_regex",
    "search_notes_regex_ids",
)

_BLOCKED_TOOL_PREFIXES: Tuple[str, ...] = (
    "create",
    "update",
    "delete",
    "append",
    "propose",
    "apply",
    "move",
    "set",
    "write",
    "patch",
)


def list_allowed_tool_names() -> Tuple[str, ...]:
    return READ_ONLY_TOOL_NAMES


def assert_read_only_tool_name(tool_name: str) -> None:
    if not isinstance(tool_name, str) or tool_name == "":
        raise TypeError("tool_name must be a non-empty string")

    if tool_name not in READ_ONLY_TOOL_NAMES:
        raise KeyError(f"Tool not allowed by read-only policy: {tool_name}")

    for blocked_prefix in _BLOCKED_TOOL_PREFIXES:
        if tool_name.startswith(blocked_prefix):
            raise RuntimeError(f"Policy violation: write-like tool exposed: {tool_name}")


def assert_tool_catalog_read_only(tool_names: Iterable[str]) -> None:
    if tool_names is None:
        raise TypeError("tool_names must be provided")

    for tool_name in tool_names:
        assert_read_only_tool_name(tool_name)
