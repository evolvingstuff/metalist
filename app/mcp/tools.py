from __future__ import annotations

from typing import Dict, List

from app.services.note_store import store as note_store

from .policy import assert_tool_catalog_read_only
from .policy import list_allowed_tool_names
from .read_service import ReadService


_TOOLS: List[Dict[str, object]] = [
    {
        "name": "health_check",
        "description": "Report MCP server readiness and version.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "count_notes",
        "description": "Return a total count of all notes in the current hydrated vault.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_note",
        "description": (
            "Return one note with full descendant subtree and tag provenance "
            "(tag_terms, implied_tag_terms, effective_tag_terms)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string"},
            },
            "required": ["note_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_children",
        "description": "Return ordered children for parent_id; use null to list root notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_id": {"type": ["string", "null"]},
            },
            "required": ["parent_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_tags",
        "description": "List known tags by prefix with frequency counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prefix": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": ["prefix", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_notes",
        "description": (
            "Search notes with free query + explicit required/forbidden tag filters. "
            "Returns total_matches and returned_count for paging."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "required_tags": {"type": "array", "items": {"type": "string"}},
                "forbidden_tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1},
                "offset": {"type": "integer", "minimum": 0},
            },
            "required": ["query", "required_tags", "forbidden_tags", "limit", "offset"],
            "additionalProperties": False,
        },
    },
]

assert_tool_catalog_read_only(tuple(tool["name"] for tool in _TOOLS))


def list_tools() -> List[Dict[str, object]]:
    return list(_TOOLS)


def _tool_error(message: str) -> Dict[str, object]:
    return {
        "ok": False,
        "error": message,
    }


def _tool_ok(payload: Dict[str, object]) -> Dict[str, object]:
    return {
        "ok": True,
        "data": payload,
    }


def call_tool(
    *,
    tool_name: object,
    arguments: object,
    read_service: ReadService,
) -> Dict[str, object]:
    if not isinstance(tool_name, str) or tool_name == "":
        return _tool_error("tool name must be a non-empty string")
    allowed_names = list_allowed_tool_names()
    if tool_name not in allowed_names:
        return _tool_error(f"Tool not allowed by read-only policy: {tool_name}")

    if not isinstance(arguments, dict):
        return _tool_error("arguments must be an object")
    args = arguments

    if tool_name == "health_check":
        if len(args) != 0:
            return _tool_error("health_check takes no arguments")
        return _tool_ok(read_service.health_check())

    if tool_name == "count_notes":
        if len(args) != 0:
            return _tool_error("count_notes takes no arguments")
        if not note_store.loaded:
            return _tool_error("Vault locked or not hydrated")
        return _tool_ok(read_service.count_notes())

    if tool_name == "get_note":
        if "note_id" not in args or len(args) != 1:
            return _tool_error("get_note requires only note_id")
        note_id = args["note_id"]
        if not isinstance(note_id, str) or note_id == "":
            return _tool_error("note_id must be a non-empty string")
        if not note_store.loaded:
            return _tool_error("Vault locked or not hydrated")
        if not note_store.has_note(note_id):
            return _tool_error(f"Note not found: {note_id}")
        return _tool_ok(read_service.get_note(note_id=note_id))

    if tool_name == "list_children":
        if "parent_id" not in args or len(args) != 1:
            return _tool_error("list_children requires only parent_id")
        parent_id = args["parent_id"]
        if parent_id is not None and (not isinstance(parent_id, str) or parent_id == ""):
            return _tool_error("parent_id must be null or a non-empty string")
        if not note_store.loaded:
            return _tool_error("Vault locked or not hydrated")
        if isinstance(parent_id, str) and not note_store.has_note(parent_id):
            return _tool_error(f"Note not found: {parent_id}")
        return _tool_ok(read_service.list_children(parent_id=parent_id))

    if tool_name == "list_tags":
        required_keys = {"prefix", "limit"}
        if set(args.keys()) != required_keys:
            return _tool_error("list_tags requires prefix and limit")
        prefix = args["prefix"]
        limit = args["limit"]
        if not isinstance(prefix, str):
            return _tool_error("prefix must be a string")
        if not isinstance(limit, int) or limit <= 0:
            return _tool_error("limit must be a positive integer")
        if not note_store.loaded:
            return _tool_error("Vault locked or not hydrated")
        return _tool_ok(read_service.list_tags(prefix=prefix, limit=limit))

    if tool_name == "search_notes":
        required_keys = {"query", "required_tags", "forbidden_tags", "limit", "offset"}
        if set(args.keys()) != required_keys:
            return _tool_error(
                "search_notes requires query, required_tags, forbidden_tags, limit, and offset"
            )
        query = args["query"]
        required_tags = args["required_tags"]
        forbidden_tags = args["forbidden_tags"]
        limit = args["limit"]
        offset = args["offset"]
        if not isinstance(query, str):
            return _tool_error("query must be a string")
        if not isinstance(required_tags, list):
            return _tool_error("required_tags must be a list of strings")
        if not isinstance(forbidden_tags, list):
            return _tool_error("forbidden_tags must be a list of strings")
        if not isinstance(limit, int) or limit <= 0:
            return _tool_error("limit must be a positive integer")
        if not isinstance(offset, int) or offset < 0:
            return _tool_error("offset must be a non-negative integer")
        for value in required_tags:
            if not isinstance(value, str) or value == "":
                return _tool_error("required_tags entries must be non-empty strings")
        for value in forbidden_tags:
            if not isinstance(value, str) or value == "":
                return _tool_error("forbidden_tags entries must be non-empty strings")
        if not note_store.loaded:
            return _tool_error("Vault locked or not hydrated")
        return _tool_ok(
            read_service.search_notes(
                query=query,
                required_tags=required_tags,
                forbidden_tags=forbidden_tags,
                limit=limit,
                offset=offset,
            )
        )

    return _tool_error(f"Unsupported tool: {tool_name}")
