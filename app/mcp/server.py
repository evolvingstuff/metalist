from __future__ import annotations

import json
import sys
from typing import Dict

from app.config import VERSION

from .read_service import ReadService
from .tools import call_tool
from .tools import list_tools

_JSONRPC_VERSION = "2.0"
_MCP_PROTOCOL_VERSION = "2024-11-05"


def _write_message(payload: Dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False)
    sys.stdout.write(encoded + "\n")
    sys.stdout.flush()


def _response(*, request_id: object, result: Dict[str, object]) -> Dict[str, object]:
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "result": result,
    }


def _error_response(*, request_id: object, code: int, message: str) -> Dict[str, object]:
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _initialize_result() -> Dict[str, object]:
    return {
        "protocolVersion": _MCP_PROTOCOL_VERSION,
        "capabilities": {
            "tools": {},
        },
        "serverInfo": {
            "name": "metalist-mcp-readonly",
            "version": VERSION,
        },
    }


def _tool_result_payload(result: Dict[str, object]) -> Dict[str, object]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False),
            }
        ],
        "structuredContent": result,
    }


def _tool_error_payload(message: str) -> Dict[str, object]:
    return {
        "content": [
            {
                "type": "text",
                "text": message,
            }
        ],
        "isError": True,
        "structuredContent": {
            "ok": False,
            "error": message,
        },
    }


def _dispatch_request(
    *,
    request_id: object,
    method: object,
    params: object,
    read_service: ReadService,
) -> Dict[str, object]:
    if not isinstance(method, str) or method == "":
        return _error_response(request_id=request_id, code=-32600, message="Invalid method")

    if method == "initialize":
        if params is not None and not isinstance(params, dict):
            return _error_response(request_id=request_id, code=-32602, message="initialize params must be an object")
        return _response(request_id=request_id, result=_initialize_result())

    if method == "ping":
        if params is not None and not isinstance(params, dict):
            return _error_response(request_id=request_id, code=-32602, message="ping params must be an object")
        return _response(request_id=request_id, result={})

    if method == "tools/list":
        if params is not None and not isinstance(params, dict):
            return _error_response(request_id=request_id, code=-32602, message="tools/list params must be an object")
        return _response(request_id=request_id, result={"tools": list_tools()})

    if method == "tools/call":
        if not isinstance(params, dict):
            return _error_response(request_id=request_id, code=-32602, message="tools/call params must be an object")
        if "name" not in params:
            return _error_response(request_id=request_id, code=-32602, message="tools/call requires name")
        if "arguments" not in params:
            return _error_response(request_id=request_id, code=-32602, message="tools/call requires arguments")

        tool_output = call_tool(
            tool_name=params["name"],
            arguments=params["arguments"],
            read_service=read_service,
        )
        if "ok" not in tool_output:
            return _error_response(
                request_id=request_id,
                code=-32603,
                message="Tool returned invalid envelope",
            )
        ok_value = tool_output["ok"]
        if not isinstance(ok_value, bool):
            return _error_response(
                request_id=request_id,
                code=-32603,
                message="Tool returned invalid ok flag",
            )
        if ok_value:
            if "data" not in tool_output:
                return _error_response(
                    request_id=request_id,
                    code=-32603,
                    message="Tool returned ok=true without data",
                )
            payload = tool_output["data"]
            if not isinstance(payload, dict):
                return _error_response(
                    request_id=request_id,
                    code=-32603,
                    message="Tool returned non-object data payload",
                )
            return _response(request_id=request_id, result=_tool_result_payload(payload))

        if "error" not in tool_output:
            return _error_response(
                request_id=request_id,
                code=-32603,
                message="Tool returned ok=false without error",
            )
        error_value = tool_output["error"]
        if not isinstance(error_value, str) or error_value == "":
            return _error_response(
                request_id=request_id,
                code=-32603,
                message="Tool returned invalid error payload",
            )
        return _response(request_id=request_id, result=_tool_error_payload(error_value))

    return _error_response(request_id=request_id, code=-32601, message=f"Method not found: {method}")


def _dispatch_notification(*, method: object, params: object) -> None:
    if not isinstance(method, str) or method == "":
        return
    if method == "notifications/initialized":
        return
    if method == "notifications/cancelled":
        return
    if params is None:
        return
    if not isinstance(params, dict):
        return


def handle_message(
    *,
    payload: object,
    read_service: ReadService,
) -> Dict[str, object] | None:
    if not isinstance(payload, dict):
        return _error_response(request_id=None, code=-32600, message="Invalid Request")

    if "method" not in payload:
        return _error_response(request_id=None, code=-32600, message="Invalid Request")
    method = payload["method"]

    if "params" in payload:
        params = payload["params"]
    else:
        params = None

    if "id" not in payload:
        _dispatch_notification(method=method, params=params)
        return None

    request_id = payload["id"]
    return _dispatch_request(
        request_id=request_id,
        method=method,
        params=params,
        read_service=read_service,
    )


def serve_stdio() -> None:
    read_service = ReadService()
    while True:
        line = sys.stdin.readline()
        if line == "":
            return

        stripped = line.strip()
        if stripped == "":
            continue

        payload = json.loads(stripped)

        response = handle_message(
            payload=payload,
            read_service=read_service,
        )
        if response is None:
            continue
        _write_message(response)
