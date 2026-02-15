from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn


_DEFAULT_MCP_URL = "http://127.0.0.1:8000/api2/mcp"
_DEFAULT_OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
_DEFAULT_OLLAMA_MODEL = "llama3.1"
_DEFAULT_WEB_HOST = "127.0.0.1"
_DEFAULT_WEB_PORT = 8765
_DEFAULT_MAX_STEPS = 6
_DEFAULT_OLLAMA_AUTOSTART = True
_DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS = 20
_DEFAULT_OLLAMA_AUTOPULL = True
_DEFAULT_OLLAMA_PULL_TIMEOUT_SECONDS = 30

DEFAULT_MCP_URL = _DEFAULT_MCP_URL
DEFAULT_OLLAMA_CHAT_URL = _DEFAULT_OLLAMA_CHAT_URL
DEFAULT_OLLAMA_MODEL = _DEFAULT_OLLAMA_MODEL
DEFAULT_WEB_HOST = _DEFAULT_WEB_HOST
DEFAULT_WEB_PORT = _DEFAULT_WEB_PORT
DEFAULT_MAX_STEPS = _DEFAULT_MAX_STEPS
DEFAULT_OLLAMA_AUTOSTART = _DEFAULT_OLLAMA_AUTOSTART
DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS = _DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS
DEFAULT_OLLAMA_AUTOPULL = _DEFAULT_OLLAMA_AUTOPULL
DEFAULT_OLLAMA_PULL_TIMEOUT_SECONDS = _DEFAULT_OLLAMA_PULL_TIMEOUT_SECONDS

_OLLAMA_SIDECAR_PROCESS: subprocess.Popen | None = None


class HttpStatusError(RuntimeError):
    def __init__(self, *, url: str, status_code: int, detail: str):
        message = f"HTTP {status_code} from {url}"
        if detail != "":
            message = f"{message}: {detail}"
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.detail = detail


def _decode_error_detail(*, raw_error_payload: bytes) -> str:
    if len(raw_error_payload) == 0:
        return ""
    return raw_error_payload.decode("utf-8", errors="replace").strip()


def _post_json(*, url: str, payload: dict) -> dict | None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw_response = response.read()
    except OSError as error:
        if isinstance(error, urllib.error.HTTPError):
            error_payload = error.read()
            detail = _decode_error_detail(raw_error_payload=error_payload)
            raise HttpStatusError(url=url, status_code=error.code, detail=detail) from error
        raise

    if len(raw_response) == 0:
        return None

    decoded = raw_response.decode("utf-8")
    parsed = json.loads(decoded)
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected JSON object response, got {type(parsed)}")
    return parsed


def _get_json(*, url: str) -> dict:
    request = urllib.request.Request(
        url=url,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw_response = response.read()
    except OSError as error:
        if isinstance(error, urllib.error.HTTPError):
            error_payload = error.read()
            detail = _decode_error_detail(raw_error_payload=error_payload)
            raise HttpStatusError(url=url, status_code=error.code, detail=detail) from error
        raise

    decoded = raw_response.decode("utf-8")
    parsed = json.loads(decoded)
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected JSON object response, got {type(parsed)}")
    return parsed


def _print_payload(payload: dict | None) -> None:
    if payload is None:
        print("null")
        return
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _initialize(*, url: str) -> dict | None:
    return _post_json(
        url=url,
        payload={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        },
    )


def _tools_list(*, url: str, request_id: int) -> dict:
    response = _post_json(
        url=url,
        payload={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {},
        },
    )
    if response is None:
        raise RuntimeError("tools/list returned empty response")
    return response


def _tools_call(*, url: str, request_id: int, tool_name: str, arguments: dict) -> dict:
    response = _post_json(
        url=url,
        payload={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        },
    )
    if response is None:
        raise RuntimeError("tools/call returned empty response")
    return response


def _extract_tools_catalog(*, list_response: dict) -> List[dict]:
    if "result" not in list_response:
        raise RuntimeError("tools/list missing result")
    result = list_response["result"]
    if not isinstance(result, dict):
        raise TypeError("tools/list result must be an object")
    if "tools" not in result:
        raise RuntimeError("tools/list result missing tools")
    tools = result["tools"]
    if not isinstance(tools, list):
        raise TypeError("tools/list tools must be an array")

    normalized_tools: List[dict] = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise TypeError("Each tool descriptor must be an object")
        normalized_tools.append(tool)
    return normalized_tools


def _extract_tool_response(*, call_response: dict) -> dict:
    if "error" in call_response:
        error_payload = call_response["error"]
        if not isinstance(error_payload, dict):
            raise TypeError("JSON-RPC error payload must be an object")
        if "message" in error_payload:
            message = error_payload["message"]
            if not isinstance(message, str):
                raise TypeError("JSON-RPC error message must be a string")
            return {"ok": False, "error": message}
        return {"ok": False, "error": "Unknown JSON-RPC error"}

    if "result" not in call_response:
        raise RuntimeError("tools/call missing result")
    result = call_response["result"]
    if not isinstance(result, dict):
        raise TypeError("tools/call result must be an object")

    if "structuredContent" in result:
        structured_content = result["structuredContent"]
        if not isinstance(structured_content, dict):
            raise TypeError("structuredContent must be an object")

        if "ok" in structured_content:
            ok_value = structured_content["ok"]
            if not isinstance(ok_value, bool):
                raise TypeError("structuredContent.ok must be boolean")
            if ok_value:
                if "data" in structured_content:
                    data_payload = structured_content["data"]
                    if not isinstance(data_payload, dict):
                        raise TypeError("structuredContent.data must be an object")
                    return {"ok": True, "data": data_payload}
                return {"ok": True, "data": structured_content}

            if "error" in structured_content:
                error_message = structured_content["error"]
                if not isinstance(error_message, str):
                    raise TypeError("structuredContent.error must be a string")
                return {"ok": False, "error": error_message}
            return {"ok": False, "error": "Tool returned ok=false without error"}

        if "isError" in result:
            is_error = result["isError"]
            if not isinstance(is_error, bool):
                raise TypeError("result.isError must be boolean")
            if is_error:
                if "error" in structured_content:
                    error_message = structured_content["error"]
                    if not isinstance(error_message, str):
                        raise TypeError("structuredContent.error must be a string")
                    return {"ok": False, "error": error_message}
                return {"ok": False, "error": "Tool error"}

        return {"ok": True, "data": structured_content}

    if "content" in result:
        content = result["content"]
        if isinstance(content, list) and len(content) > 0:
            first_chunk = content[0]
            if isinstance(first_chunk, dict) and "text" in first_chunk:
                text = first_chunk["text"]
                if isinstance(text, str):
                    return {"ok": True, "data": {"text": text}}

    return {"ok": True, "data": result}


def _build_tool_summaries(*, tools_catalog: List[dict]) -> List[dict]:
    summaries: List[dict] = []
    for tool in tools_catalog:
        if "name" not in tool:
            raise RuntimeError("Tool descriptor missing name")
        if "description" not in tool:
            raise RuntimeError("Tool descriptor missing description")
        if "inputSchema" not in tool:
            raise RuntimeError("Tool descriptor missing inputSchema")

        name = tool["name"]
        description = tool["description"]
        input_schema = tool["inputSchema"]
        if not isinstance(name, str):
            raise TypeError("Tool name must be a string")
        if not isinstance(description, str):
            raise TypeError("Tool description must be a string")
        if not isinstance(input_schema, dict):
            raise TypeError("Tool inputSchema must be an object")

        summaries.append(
            {
                "name": name,
                "description": description,
                "inputSchema": input_schema,
            }
        )
    return summaries


def _build_agent_system_prompt(*, tool_summaries: List[dict]) -> str:
    tools_json = json.dumps(tool_summaries, ensure_ascii=False)
    return (
        "You are an agent for MetaList. "
        "You may call tools multiple times. "
        "Use tool inputSchema exactly; do not send extra keys. "
        "Never invent note ids. Use only note ids returned by tool responses. "
        "If user asks for note count, call count_notes. "
        "If a tool returns an argument error, correct arguments and retry. "
        "Available tools are: "
        + tools_json
        + " . Return ONLY JSON with one of these exact shapes: "
        + '{"action":"tool","tool_name":"<name>","arguments":{...},"reason":"<brief>"} '
        + 'OR {"action":"final","answer":"<response for user>"} .'
    )


def _ollama_chat_json(*, ollama_chat_url: str, model: str, messages: List[dict]) -> dict:
    ensure_ollama_running(
        ollama_chat_url=ollama_chat_url,
        autostart=_DEFAULT_OLLAMA_AUTOSTART,
        wait_timeout_seconds=_DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS,
    )
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": messages,
    }
    response = _post_json(url=ollama_chat_url, payload=payload)
    if response is None:
        raise RuntimeError("Ollama chat returned empty response")
    if "message" not in response:
        raise RuntimeError("Ollama chat response missing message")
    message = response["message"]
    if not isinstance(message, dict):
        raise TypeError("Ollama message payload must be an object")
    if "content" not in message:
        raise RuntimeError("Ollama message missing content")
    content = message["content"]
    if not isinstance(content, str):
        raise TypeError("Ollama message content must be a string")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise TypeError("Ollama JSON response must decode to an object")
    return parsed


def _derive_tags_url(*, ollama_chat_url: str) -> str:
    suffix = "/api/chat"
    if not ollama_chat_url.endswith(suffix):
        raise ValueError("ollama_chat_url must end with /api/chat")
    return ollama_chat_url[: -len(suffix)] + "/api/tags"


def _ollama_host_port(*, ollama_chat_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(ollama_chat_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("ollama_chat_url must use http or https")
    if parsed.hostname is None:
        raise ValueError("ollama_chat_url must include host")
    if parsed.port is not None:
        port = parsed.port
    else:
        if parsed.scheme == "https":
            port = 443
        else:
            port = 80
    return parsed.hostname, port


def _is_tcp_open(*, host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        status = sock.connect_ex((host, port))
        return status == 0


def _is_local_host(*, host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def ensure_ollama_running(
    *,
    ollama_chat_url: str,
    autostart: bool,
    wait_timeout_seconds: int,
) -> None:
    host, port = _ollama_host_port(ollama_chat_url=ollama_chat_url)
    if _is_tcp_open(host=host, port=port):
        return

    if not autostart:
        raise RuntimeError(
            f"Ollama is not reachable at {host}:{port}. Start it with `ollama serve`."
        )

    if not _is_local_host(host=host):
        raise RuntimeError(
            f"Ollama URL host {host!r} is not local and is unreachable at {host}:{port}."
        )

    global _OLLAMA_SIDECAR_PROCESS
    if _OLLAMA_SIDECAR_PROCESS is None or _OLLAMA_SIDECAR_PROCESS.poll() is not None:
        print("Starting Ollama automatically: ollama serve")
        _OLLAMA_SIDECAR_PROCESS = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    started_at = time.monotonic()
    while time.monotonic() - started_at < wait_timeout_seconds:
        if _is_tcp_open(host=host, port=port):
            return
        if _OLLAMA_SIDECAR_PROCESS is not None:
            exit_code = _OLLAMA_SIDECAR_PROCESS.poll()
            if exit_code is not None:
                stderr_output = ""
                if _OLLAMA_SIDECAR_PROCESS.stderr is not None:
                    stderr_output = _OLLAMA_SIDECAR_PROCESS.stderr.read().strip()
                detail = f"`ollama serve` exited early with code {exit_code}."
                if stderr_output != "":
                    detail = f"{detail} stderr: {stderr_output}"
                raise RuntimeError(detail)
        time.sleep(0.25)

    raise RuntimeError(
        f"Started `ollama serve` but {host}:{port} did not become reachable within "
        f"{wait_timeout_seconds}s."
    )


def _ollama_models(*, ollama_chat_url: str) -> List[str]:
    ensure_ollama_running(
        ollama_chat_url=ollama_chat_url,
        autostart=_DEFAULT_OLLAMA_AUTOSTART,
        wait_timeout_seconds=_DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS,
    )
    tags_url = _derive_tags_url(ollama_chat_url=ollama_chat_url)
    payload = _get_json(url=tags_url)
    if "models" not in payload:
        raise RuntimeError("Ollama tags response missing models")
    models = payload["models"]
    if not isinstance(models, list):
        raise TypeError("Ollama tags models must be an array")

    names: List[str] = []
    for model in models:
        if not isinstance(model, dict):
            raise TypeError("Ollama model descriptor must be an object")
        if "name" not in model:
            raise RuntimeError("Ollama model descriptor missing name")
        name = model["name"]
        if not isinstance(name, str):
            raise TypeError("Ollama model name must be a string")
        names.append(name)
    return names


def ensure_ollama_model_available(
    *,
    ollama_chat_url: str,
    model: str,
    autopull: bool,
) -> str:
    installed_models = _ollama_models(ollama_chat_url=ollama_chat_url)
    resolved_installed_model = _resolve_installed_model(
        installed_models=installed_models,
        requested_model=model,
    )
    if resolved_installed_model is not None:
        return resolved_installed_model

    installed_models_text = "<none>"
    if len(installed_models) > 0:
        installed_models_text = ", ".join(installed_models)
    if not autopull:
        raise RuntimeError(
            f"Ollama model {model!r} is not installed. Installed models: {installed_models_text}."
        )

    host, _ = _ollama_host_port(ollama_chat_url=ollama_chat_url)
    if not _is_local_host(host=host):
        raise RuntimeError(
            f"Ollama model {model!r} is not installed on host {host!r}. "
            f"Installed models: {installed_models_text}."
        )

    print(f"Pulling Ollama model automatically: {model}")
    pull_process = subprocess.Popen(
        ["ollama", "pull", model],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    pull_started_at = time.monotonic()
    while time.monotonic() - pull_started_at < _DEFAULT_OLLAMA_PULL_TIMEOUT_SECONDS:
        pull_exit_code = pull_process.poll()
        if pull_exit_code is not None:
            if pull_exit_code != 0:
                stderr_output = ""
                if pull_process.stderr is not None:
                    stderr_output = pull_process.stderr.read().strip()
                detail = f"`ollama pull {model}` failed with code {pull_exit_code}."
                if stderr_output != "":
                    detail = f"{detail} stderr: {stderr_output}"
                raise RuntimeError(detail)
            break
        time.sleep(0.25)

    pull_exit_code = pull_process.poll()
    if pull_exit_code is None:
        pull_process.kill()
        pull_process.wait()
        raise RuntimeError(
            f"`ollama pull {model}` did not complete within "
            f"{_DEFAULT_OLLAMA_PULL_TIMEOUT_SECONDS}s. "
            "The model download is likely still in progress; retry shortly."
        )

    refreshed_models = _ollama_models(ollama_chat_url=ollama_chat_url)
    resolved_after_pull = _resolve_installed_model(
        installed_models=refreshed_models,
        requested_model=model,
    )
    if resolved_after_pull is None:
        raise RuntimeError(
            f"`ollama pull {model}` completed but model is still missing from /api/tags."
        )
    return resolved_after_pull


def _resolve_installed_model(*, installed_models: List[str], requested_model: str) -> str | None:
    for installed_model in installed_models:
        if installed_model == requested_model:
            return installed_model

    if ":" not in requested_model:
        requested_prefix = requested_model + ":"
        for installed_model in installed_models:
            if installed_model.startswith(requested_prefix):
                return installed_model

    requested_base = requested_model
    if ":" in requested_model:
        requested_base = requested_model.split(":", 1)[0]
    for installed_model in installed_models:
        installed_base = installed_model
        if ":" in installed_model:
            installed_base = installed_model.split(":", 1)[0]
        if installed_base == requested_base:
            return installed_model

    return None


def _get_tool_schema(*, tool_summaries: List[dict], tool_name: str) -> dict | None:
    for summary in tool_summaries:
        if not isinstance(summary, dict):
            continue
        if summary.get("name") != tool_name:
            continue
        schema = summary.get("inputSchema")
        if isinstance(schema, dict):
            return schema
        return None
    return None


def _has_placeholder_value(*, value: object) -> bool:
    if isinstance(value, str):
        return "<" in value and ">" in value
    if isinstance(value, list):
        for entry in value:
            if _has_placeholder_value(value=entry):
                return True
        return False
    if isinstance(value, dict):
        for entry in value.values():
            if _has_placeholder_value(value=entry):
                return True
        return False
    return False


def _sanitize_tool_arguments(
    *,
    tool_name: str,
    arguments: dict,
    tool_summaries: List[dict],
) -> dict:
    schema = _get_tool_schema(tool_summaries=tool_summaries, tool_name=tool_name)
    if schema is None:
        return {
            "ok": True,
            "arguments": dict(arguments),
            "changed": False,
        }

    schema_properties = schema.get("properties")
    schema_required = schema.get("required")
    additional_properties = schema.get("additionalProperties")
    if schema_properties is not None and not isinstance(schema_properties, dict):
        return {
            "ok": False,
            "error": f"Tool schema for {tool_name} has invalid properties",
        }
    if schema_required is not None and not isinstance(schema_required, list):
        return {
            "ok": False,
            "error": f"Tool schema for {tool_name} has invalid required list",
        }

    normalized_arguments = dict(arguments)
    changed = False

    if additional_properties is False and isinstance(schema_properties, dict):
        normalized_arguments = {}
        for key in schema_properties:
            if key in arguments:
                normalized_arguments[key] = arguments[key]
        if len(normalized_arguments) != len(arguments):
            changed = True

    required_keys: List[str] = []
    if isinstance(schema_required, list):
        for entry in schema_required:
            if isinstance(entry, str):
                required_keys.append(entry)
    missing_required: List[str] = []
    for key in required_keys:
        if key not in normalized_arguments:
            missing_required.append(key)
    if len(missing_required) > 0:
        missing_display = ", ".join(missing_required)
        return {
            "ok": False,
            "error": f"Missing required arguments for {tool_name}: {missing_display}",
        }

    if _has_placeholder_value(value=normalized_arguments):
        return {
            "ok": False,
            "error": (
                f"Arguments for {tool_name} include placeholder values like <...>. "
                "Use only concrete values returned by previous tools."
            ),
        }

    return {
        "ok": True,
        "arguments": normalized_arguments,
        "changed": changed,
    }


def _run_agentic_request(
    *,
    user_message: str,
    mcp_url: str,
    ollama_chat_url: str,
    model: str,
    max_steps: int,
) -> dict:
    if max_steps <= 0:
        raise ValueError("max_steps must be > 0")

    tools_list_response = _tools_list(url=mcp_url, request_id=2)
    tools_catalog = _extract_tools_catalog(list_response=tools_list_response)
    tool_summaries = _build_tool_summaries(tools_catalog=tools_catalog)
    system_prompt = _build_agent_system_prompt(tool_summaries=tool_summaries)
    resolved_model = ensure_ollama_model_available(
        ollama_chat_url=ollama_chat_url,
        model=model,
        autopull=_DEFAULT_OLLAMA_AUTOPULL,
    )

    messages: List[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    steps: List[dict] = []
    request_id = 100

    for step_number in range(1, max_steps + 1):
        decision = _ollama_chat_json(
            ollama_chat_url=ollama_chat_url,
            model=resolved_model,
            messages=messages,
        )
        if "action" not in decision:
            raise RuntimeError("Agent response missing action")
        action = decision["action"]
        if not isinstance(action, str):
            raise TypeError("Agent action must be a string")

        if action == "final":
            if "answer" not in decision:
                raise RuntimeError("Final action missing answer")
            answer = decision["answer"]
            if not isinstance(answer, str):
                raise TypeError("Final answer must be a string")
            return {
                "ok": True,
                "answer": answer,
                "model": resolved_model,
                "steps": steps,
            }

        if action != "tool":
            raise RuntimeError(f"Unknown agent action: {action}")

        if "tool_name" not in decision:
            raise RuntimeError("Tool action missing tool_name")
        if "arguments" not in decision:
            raise RuntimeError("Tool action missing arguments")
        tool_name = decision["tool_name"]
        arguments = decision["arguments"]
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be a string")
        if not isinstance(arguments, dict):
            raise TypeError("arguments must be an object")

        sanitize_result = _sanitize_tool_arguments(
            tool_name=tool_name,
            arguments=arguments,
            tool_summaries=tool_summaries,
        )
        if sanitize_result["ok"] is not True:
            tool_response = {
                "ok": False,
                "error": sanitize_result["error"],
            }
            normalized_arguments = dict(arguments)
            arguments_changed = False
        else:
            normalized_arguments = sanitize_result["arguments"]
            arguments_changed = bool(sanitize_result["changed"])
            tool_call_response = _tools_call(
                url=mcp_url,
                request_id=request_id,
                tool_name=tool_name,
                arguments=normalized_arguments,
            )
            tool_response = _extract_tool_response(call_response=tool_call_response)

        step_record = {
            "step": step_number,
            "action": "tool",
            "tool_name": tool_name,
            "arguments": normalized_arguments,
            "tool_response": tool_response,
        }
        if arguments_changed:
            step_record["raw_arguments"] = arguments
        if "reason" in decision and isinstance(decision["reason"], str):
            step_record["reason"] = decision["reason"]
        steps.append(step_record)

        tool_feedback = {
            "tool_name": tool_name,
            "tool_response": tool_response,
        }
        messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
        messages.append({"role": "user", "content": "TOOL_RESULT " + json.dumps(tool_feedback, ensure_ascii=False)})

        request_id += 1

    return {
        "ok": False,
        "answer": "Reached max_steps without a final answer.",
        "model": resolved_model,
        "steps": steps,
    }


class AgentChatRequest(BaseModel):
    message: str
    model: str
    max_steps: int
    mcp_url: str
    ollama_chat_url: str


def _web_html(
    *,
    default_model: str,
    default_max_steps: int,
    default_mcp_url: str,
    default_ollama_chat_url: str,
) -> str:
    model_value = json.dumps(default_model)
    mcp_url_value = json.dumps(default_mcp_url)
    ollama_chat_url_value = json.dumps(default_ollama_chat_url)
    max_steps_value = str(default_max_steps)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MetaList MCP Agent</title>
  <style>
    :root {{
      --bg: #f7f6f2;
      --panel: #ffffff;
      --ink: #1f1f1f;
      --muted: #5f5f5f;
      --line: #ded9d0;
      --accent: #1f6feb;
    }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 20% 0%, #fff9e8 0%, var(--bg) 45%, #eceaf5 100%);
    }}
    .wrap {{
      max-width: 980px;
      margin: 28px auto;
      padding: 0 16px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.06);
    }}
    h1 {{
      margin: 0 0 12px 0;
      font-size: 24px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 10px;
    }}
    label {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    input, textarea, button {{
      width: 100%;
      box-sizing: border-box;
      border-radius: 10px;
      border: 1px solid var(--line);
      padding: 10px;
      font: inherit;
    }}
    textarea {{
      min-height: 110px;
      resize: vertical;
    }}
    .row {{
      display: flex;
      gap: 10px;
      margin-top: 10px;
    }}
    button {{
      background: var(--accent);
      color: white;
      border: 0;
      cursor: pointer;
      font-weight: 600;
    }}
    button.secondary {{
      background: #505968;
    }}
    pre {{
      white-space: pre-wrap;
      background: #111827;
      color: #d1e3ff;
      border-radius: 10px;
      padding: 12px;
      overflow: auto;
      max-height: 60vh;
    }}
    .muted {{
      font-size: 12px;
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>MetaList MCP Agent Console</h1>
      <p class="muted">This UI runs agentic loops with Ollama and can call MCP tools multiple times per request.</p>
      <div class="grid">
        <div>
          <label for="model">Ollama model</label>
          <input id="model" value={model_value} />
        </div>
        <div>
          <label for="max_steps">Max steps</label>
          <input id="max_steps" type="number" min="1" value="{max_steps_value}" />
        </div>
        <div>
          <label for="mcp_url">MCP URL</label>
          <input id="mcp_url" value={mcp_url_value} />
        </div>
        <div>
          <label for="ollama_chat_url">Ollama chat URL</label>
          <input id="ollama_chat_url" value={ollama_chat_url_value} />
        </div>
      </div>
      <label for="prompt">Request</label>
      <textarea id="prompt" placeholder="Ask something, e.g. summarize top project notes tagged work..."></textarea>
      <div class="row">
        <button id="run_btn">Run Agent</button>
        <button id="models_btn" class="secondary">Load Ollama Models</button>
      </div>
      <h3>Output</h3>
      <pre id="output">{{}}</pre>
    </div>
  </div>
  <script>
    const output = document.getElementById("output");
    const runBtn = document.getElementById("run_btn");
    const modelsBtn = document.getElementById("models_btn");
    const promptEl = document.getElementById("prompt");
    const modelEl = document.getElementById("model");
    const maxStepsEl = document.getElementById("max_steps");
    const mcpUrlEl = document.getElementById("mcp_url");
    const ollamaChatUrlEl = document.getElementById("ollama_chat_url");

    function print(obj) {{
      output.textContent = JSON.stringify(obj, null, 2);
    }}

    async function fetchWithTimeout(url, options, timeoutMs) {{
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort("request-timeout"), timeoutMs);
      try {{
        return await fetch(url, {{ ...options, signal: controller.signal }});
      }} finally {{
        clearTimeout(timeout);
      }}
    }}

    async function readErrorResponse(res) {{
      const text = await res.text();
      if (text === "") {{
        return `HTTP ${{res.status}}`;
      }}
      try {{
        const parsed = JSON.parse(text);
        return JSON.stringify(parsed, null, 2);
      }} catch (_) {{
        return text;
      }}
    }}

    runBtn.addEventListener("click", async () => {{
      runBtn.disabled = true;
      print({{ status: "running" }});
      try {{
        const payload = {{
          message: promptEl.value,
          model: modelEl.value,
          max_steps: Number(maxStepsEl.value),
          mcp_url: mcpUrlEl.value,
          ollama_chat_url: ollamaChatUrlEl.value,
        }};
        const res = await fetchWithTimeout("/api/chat", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload),
        }}, 45000);
        if (!res.ok) {{
          const errorBody = await readErrorResponse(res);
          print({{
            status: "error",
            where: "/api/chat",
            http_status: res.status,
            detail: errorBody
          }});
          return;
        }}
        const data = await res.json();
        print({{ status: "ok", result: data }});
      }} catch (err) {{
        let message = err instanceof Error ? err.message : String(err);
        if (message.includes("request-timeout")) {{
          message = "Request timed out after 45s. If model auto-pull is running, wait and retry.";
        }}
        print({{
          status: "error",
          where: "browser_fetch",
          detail: message
        }});
      }} finally {{
        runBtn.disabled = false;
      }}
    }});

    modelsBtn.addEventListener("click", async () => {{
      modelsBtn.disabled = true;
      print({{ status: "loading_models" }});
      try {{
        const url = "/api/models?ollama_chat_url=" + encodeURIComponent(ollamaChatUrlEl.value);
        const res = await fetchWithTimeout(url, {{}}, 20000);
        if (!res.ok) {{
          const errorBody = await readErrorResponse(res);
          print({{
            status: "error",
            where: "/api/models",
            http_status: res.status,
            detail: errorBody
          }});
          return;
        }}
        const data = await res.json();
        print({{ status: "ok", result: data }});
        if (Array.isArray(data.models) && data.models.length > 0) {{
          modelEl.value = data.models[0];
        }}
      }} catch (err) {{
        let message = err instanceof Error ? err.message : String(err);
        if (message.includes("request-timeout")) {{
          message = "Load models timed out after 20s.";
        }}
        print({{
          status: "error",
          where: "browser_fetch",
          detail: message
        }});
      }} finally {{
        modelsBtn.disabled = false;
      }}
    }});
  </script>
</body>
</html>"""


def create_web_app(
    *,
    default_model: str,
    default_max_steps: int,
    default_mcp_url: str,
    default_ollama_chat_url: str,
) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(Exception)
    async def unhandled_error(_request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"{type(exc).__name__}: {exc}",
            },
        )

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _web_html(
            default_model=default_model,
            default_max_steps=default_max_steps,
            default_mcp_url=default_mcp_url,
            default_ollama_chat_url=default_ollama_chat_url,
        )

    @app.get("/api/models")
    def models(ollama_chat_url: str) -> dict:
        models_list = _ollama_models(ollama_chat_url=ollama_chat_url)
        return {
            "models": models_list,
            "count": len(models_list),
        }

    @app.post("/api/chat")
    def chat(payload: AgentChatRequest) -> dict:
        if payload.message.strip() == "":
            raise HTTPException(status_code=400, detail="message must not be empty")
        if payload.max_steps <= 0:
            raise HTTPException(status_code=400, detail="max_steps must be > 0")
        result = _run_agentic_request(
            user_message=payload.message,
            mcp_url=payload.mcp_url,
            ollama_chat_url=payload.ollama_chat_url,
            model=payload.model,
            max_steps=payload.max_steps,
        )
        return result

    return app


def _run_web(
    *,
    host: str,
    port: int,
    mcp_url: str,
    ollama_chat_url: str,
    model: str,
    max_steps: int,
) -> None:
    app = create_web_app(
        default_model=model,
        default_max_steps=max_steps,
        default_mcp_url=mcp_url,
        default_ollama_chat_url=ollama_chat_url,
    )
    link = f"http://{host}:{port}"
    print(f"Open web app: {link}")
    uvicorn.run(app, host=host, port=port, reload=False, workers=1)


def main() -> None:
    argv = list(sys.argv[1:])
    if len(argv) > 0 and argv[0] in {"initialize", "tools/list", "tools/call"}:
        argv = ["cli", *argv]

    parser = argparse.ArgumentParser(description="MetaList MCP client + web agent UI")
    subparsers = parser.add_subparsers(dest="mode")
    subparsers.required = True

    cli_parser = subparsers.add_parser("cli", help="Call MCP directly")
    cli_parser.add_argument("command", choices=("initialize", "tools/list", "tools/call"))
    cli_parser.add_argument("tool_name", nargs="?")
    cli_parser.add_argument("arguments_json", nargs="?")
    cli_parser.add_argument("--url")

    web_parser = subparsers.add_parser("web", help="Run web UI on a separate port")
    web_parser.add_argument("--host")
    web_parser.add_argument("--port", type=int)
    web_parser.add_argument("--mcp-url")
    web_parser.add_argument("--ollama-chat-url")
    web_parser.add_argument("--model")
    web_parser.add_argument("--max-steps", type=int)

    args = parser.parse_args(argv)

    if args.mode == "cli":
        if args.url is None:
            url = _DEFAULT_MCP_URL
        else:
            url = args.url

        if args.command == "initialize":
            init_response = _initialize(url=url)
            _print_payload(init_response)
            return

        init_response = _initialize(url=url)
        _print_payload(init_response)

        if args.command == "tools/list":
            response = _tools_list(url=url, request_id=2)
            _print_payload(response)
            return

        if args.tool_name is None:
            raise ValueError("tools/call requires tool_name")
        if args.arguments_json is None:
            raise ValueError("tools/call requires arguments_json")

        arguments = json.loads(args.arguments_json)
        if not isinstance(arguments, dict):
            raise TypeError("arguments_json must decode to a JSON object")

        response = _tools_call(
            url=url,
            request_id=2,
            tool_name=args.tool_name,
            arguments=arguments,
        )
        _print_payload(response)
        return

    if args.host is None:
        host = _DEFAULT_WEB_HOST
    else:
        host = args.host

    if args.port is None:
        port = _DEFAULT_WEB_PORT
    else:
        port = args.port

    if args.mcp_url is None:
        mcp_url = _DEFAULT_MCP_URL
    else:
        mcp_url = args.mcp_url

    if args.ollama_chat_url is None:
        ollama_chat_url = _DEFAULT_OLLAMA_CHAT_URL
    else:
        ollama_chat_url = args.ollama_chat_url

    if args.model is None:
        model = _DEFAULT_OLLAMA_MODEL
    else:
        model = args.model

    if args.max_steps is None:
        max_steps = _DEFAULT_MAX_STEPS
    else:
        max_steps = args.max_steps

    _run_web(
        host=host,
        port=port,
        mcp_url=mcp_url,
        ollama_chat_url=ollama_chat_url,
        model=model,
        max_steps=max_steps,
    )


if __name__ == "__main__":
    main()
