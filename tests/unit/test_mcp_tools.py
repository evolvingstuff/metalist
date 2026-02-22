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


def test_search_notes_regex_requires_all_arguments() -> None:
    service = ReadService()

    response = call_tool(
        tool_name="search_notes_regex",
        arguments={
            "pattern": "dad",
            "flags": "i",
            "regex_engine": "python-re",
            "target": "both",
            "scope_note_ids": [],
            "limit": 10,
        },
        read_service=service,
    )
    assert response["ok"] is False
    assert "search_notes_regex requires" in response["error"]


def test_search_note_ids_requires_all_arguments() -> None:
    service = ReadService()

    response = call_tool(
        tool_name="search_note_ids",
        arguments={
            "query": "",
            "required_tags": [],
            "forbidden_tags": [],
            "limit": 10,
        },
        read_service=service,
    )
    assert response["ok"] is False
    assert "search_note_ids requires" in response["error"]


def test_search_notes_regex_ids_requires_all_arguments() -> None:
    service = ReadService()

    response = call_tool(
        tool_name="search_notes_regex_ids",
        arguments={
            "pattern": "dad",
            "flags": "i",
            "regex_engine": "python-re",
            "target": "both",
            "scope_note_ids": [],
            "limit": 10,
        },
        read_service=service,
    )
    assert response["ok"] is False
    assert "search_notes_regex_ids requires" in response["error"]


def test_get_notes_batch_requires_all_arguments() -> None:
    service = ReadService()

    response = call_tool(
        tool_name="get_notes_batch",
        arguments={
            "note_ids": [],
            "include_content_text": True,
            "include_context_text": True,
            "include_tags": True,
        },
        read_service=service,
    )
    assert response["ok"] is False
    assert "get_notes_batch requires" in response["error"]
