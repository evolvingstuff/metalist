from __future__ import annotations

from app.mcp.policy import list_allowed_tool_names
from app.mcp.read_service import ReadService
import app.mcp.tools as tools_module
from app.mcp.tools import call_tool
from app.mcp.tools import list_tools


def test_tool_catalog_is_strictly_read_only() -> None:
    names = [tool["name"] for tool in list_tools()]
    assert names == list(list_allowed_tool_names())

    blocked_prefixes = (
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
    for name in names:
        for blocked_prefix in blocked_prefixes:
            assert not name.startswith(blocked_prefix)


def test_search_notes_requires_all_arguments() -> None:
    service = ReadService()

    response = call_tool(
        tool_name="search_notes",
        arguments={
            "query": "",
            "required_tags": [],
            "forbidden_tags": [],
            "limit": 10,
        },
        read_service=service,
    )
    assert response["ok"] is False
    assert "search_notes requires" in response["error"]


def test_count_notes_requires_no_arguments(monkeypatch) -> None:
    service = ReadService()

    class _FakeStore:
        loaded = True

    monkeypatch.setattr(tools_module, "note_store", _FakeStore())
    monkeypatch.setattr(service, "count_notes", lambda: {"total_notes": 42})

    response = call_tool(
        tool_name="count_notes",
        arguments={},
        read_service=service,
    )
    assert response["ok"] is True
    assert response["data"]["total_notes"] == 42
