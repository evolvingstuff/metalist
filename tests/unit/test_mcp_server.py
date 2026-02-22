from __future__ import annotations

from app.mcp.read_service import ReadService
from app.mcp.server import handle_message


def test_handle_message_initialize() -> None:
    service = ReadService()
    response = handle_message(
        payload={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        },
        read_service=service,
    )
    assert response is not None
    assert response["id"] == 1
    assert "result" in response
    assert response["result"]["serverInfo"]["name"] == "metalist-mcp-readonly"


def test_handle_message_tools_list() -> None:
    service = ReadService()
    response = handle_message(
        payload={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
        read_service=service,
    )
    assert response is not None
    tools = response["result"]["tools"]
    names = [tool["name"] for tool in tools]
    assert "health_check" in names
    assert "count_notes" in names
    assert "search_notes" in names
    assert "search_note_ids" in names
    assert "search_notes_regex" in names
    assert "search_notes_regex_ids" in names
    assert "get_notes_batch" in names


def test_handle_message_notification_returns_none() -> None:
    service = ReadService()
    response = handle_message(
        payload={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        read_service=service,
    )
    assert response is None


def test_handle_message_invalid_request() -> None:
    service = ReadService()
    response = handle_message(
        payload={"jsonrpc": "2.0", "id": 9},
        read_service=service,
    )
    assert response is not None
    assert "error" in response
    assert response["error"]["code"] == -32600


def test_handle_message_tool_error_payload() -> None:
    service = ReadService()
    response = handle_message(
        payload={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "search_notes",
                "arguments": {
                    "query": "",
                    "required_tags": [],
                    "forbidden_tags": [],
                    "limit": 5,
                },
            },
        },
        read_service=service,
    )
    assert response is not None
    assert "result" in response
    assert response["result"]["isError"] is True
