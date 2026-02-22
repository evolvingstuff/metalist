from __future__ import annotations

import argparse
import difflib
import html
import json
import math
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, List

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from app.services.search_query import parse_search_query


_DEFAULT_MCP_URL = "http://127.0.0.1:8000/api2/mcp"
_DEFAULT_OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
_DEFAULT_OLLAMA_MODEL = "qwen2.5:7b-instruct"
_DEFAULT_WEB_HOST = "127.0.0.1"
_DEFAULT_WEB_PORT = 8765
_DEFAULT_MAX_STEPS = 6
_DEFAULT_OLLAMA_AUTOSTART = True
_DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS = 20
_DEFAULT_OLLAMA_AUTOPULL = True
_DEFAULT_OLLAMA_PULL_TIMEOUT_SECONDS = 30
_MAX_INVALID_DECISION_REPAIRS = 2
_OLLAMA_CHAT_TIMEOUT_SECONDS = 180
_DEFAULT_PLANNER_SEED_TAG_LIMIT = 50
_DEFAULT_PLANNER_TAG_COUNT_MODE = "raw"
_ALLOWED_PLANNER_TAG_COUNT_MODES = frozenset({"effective", "raw"})
_PLANNER_TAG_CATALOG_LIMIT = 100000
_DEFAULT_SEARCH_CONTEXT_QUERY = ""
_DEFAULT_MAX_EXPRESSIONS = 20
_DEFAULT_HYDRATE_TOP_K = 80
_DEFAULT_REGEX_ENGINE = "python-re"
_ALLOWED_REGEX_ENGINES = frozenset({"python-re", "re2"})
_MAX_EXPRESSION_SEARCH_RESULTS = 100000
_MAX_REWRITE_STEP_RESULT_LIMIT = 400
_STEP_NOTE_ID_SAMPLE_LIMIT = 50
_TAG_ATOM_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_EXPRESSION_PLAN_TARGET_CAP = 8
_EXPRESSION_PROBE_FIRST = 4
_EXPRESSION_PROBE_SECOND = 8
_SYNTHESIS_MAX_NOTES = 40
_ITERATION_EVIDENCE_MAX_NOTES = 24
_SYNTHESIS_MAX_CONTENT_EXCERPT_CHARS = 900
_SYNTHESIS_MAX_CONTEXT_EXCERPT_CHARS = 1400
_SYNTHESIS_SMALL_CANDIDATE_THRESHOLD = 12
_SYNTHESIS_SMALL_CANDIDATE_CONTENT_MAX_CHARS = 5000
_SYNTHESIS_SMALL_CANDIDATE_CONTEXT_MAX_CHARS = 12000
_REGEX_MATCH_PREVIEW_LIMIT = 24

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
DEFAULT_PLANNER_SEED_TAG_LIMIT = _DEFAULT_PLANNER_SEED_TAG_LIMIT
DEFAULT_PLANNER_TAG_COUNT_MODE = _DEFAULT_PLANNER_TAG_COUNT_MODE
DEFAULT_SEARCH_CONTEXT_QUERY = _DEFAULT_SEARCH_CONTEXT_QUERY
DEFAULT_MAX_EXPRESSIONS = _DEFAULT_MAX_EXPRESSIONS
DEFAULT_HYDRATE_TOP_K = _DEFAULT_HYDRATE_TOP_K
DEFAULT_REGEX_ENGINE = _DEFAULT_REGEX_ENGINE

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


def _post_json(*, url: str, payload: dict, timeout_seconds: int | None = None) -> dict | None:
    if timeout_seconds is None:
        timeout_seconds = 60
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
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


def _compact_text_for_context(*, text: str, max_chars: int) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text must be a string, got {type(text)}")
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    # Avoid feeding giant inline image blobs back into the model context.
    without_data_uris = re.sub(
        r"data:image/[A-Za-z0-9.+-]+;base64,[^\"'\s>]+",
        "[image-data-uri-omitted]",
        text,
    )
    collapsed = re.sub(r"\s+", " ", without_data_uris).strip()
    if len(collapsed) <= max_chars:
        return collapsed

    marker = " ... "
    if len(marker) >= max_chars:
        return collapsed[:max_chars]

    # Preserve both head and tail so evidence near the end is not always lost.
    available = max_chars - len(marker)
    head_chars = max(available // 2, 1)
    tail_chars = max(available - head_chars, 1)
    if head_chars + tail_chars > len(collapsed):
        return collapsed

    return collapsed[:head_chars] + marker + collapsed[-tail_chars:]


def _strip_html_to_text(*, text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text must be a string, got {type(text)}")
    decoded = html.unescape(text)
    without_script_style = re.sub(
        r"(?is)<(script|style)\b[^>]*>.*?</\1>",
        " ",
        decoded,
    )
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_script_style)
    return re.sub(r"\s+", " ", without_tags).strip()


def _extract_term_snippets(*, plain_text: str, terms: List[str], max_snippets: int) -> List[str]:
    if not isinstance(plain_text, str):
        raise TypeError("plain_text must be a string")
    if max_snippets <= 0:
        raise ValueError("max_snippets must be > 0")

    normalized_terms: List[str] = []
    seen_terms = set()
    for term in terms:
        if not isinstance(term, str):
            continue
        normalized = term.casefold().strip()
        if normalized == "":
            continue
        if normalized in seen_terms:
            continue
        seen_terms.add(normalized)
        normalized_terms.append(normalized)

    if len(normalized_terms) == 0:
        return []

    folded_text = plain_text.casefold()
    snippets: List[str] = []
    seen_snippets = set()
    window_chars = 140

    for term in normalized_terms:
        start_index = 0
        while True:
            found_index = folded_text.find(term, start_index)
            if found_index < 0:
                break
            left = max(found_index - window_chars, 0)
            right = min(found_index + len(term) + window_chars, len(plain_text))
            snippet = plain_text[left:right].strip()
            if left > 0:
                snippet = "... " + snippet
            if right < len(plain_text):
                snippet = snippet + " ..."
            snippet = _compact_text_for_context(text=snippet, max_chars=360)
            if snippet not in seen_snippets and snippet != "":
                snippets.append(snippet)
                seen_snippets.add(snippet)
                if len(snippets) >= max_snippets:
                    return snippets
            start_index = found_index + len(term)

    return snippets


def _summarize_get_note_for_model(*, tool_response: dict, query_terms: List[str]) -> object:
    if not isinstance(tool_response, dict):
        return _compact_for_model(value=tool_response)
    if "ok" not in tool_response:
        return _compact_for_model(value=tool_response)
    ok_value = tool_response["ok"]
    if not isinstance(ok_value, bool):
        return _compact_for_model(value=tool_response)
    if ok_value is not True:
        return _compact_for_model(value=tool_response)
    if "data" not in tool_response:
        return _compact_for_model(value=tool_response)
    data = tool_response["data"]
    if not isinstance(data, dict):
        return _compact_for_model(value=tool_response)
    if "note" not in data:
        return _compact_for_model(value=tool_response)
    root_note = data["note"]
    if not isinstance(root_note, dict):
        return _compact_for_model(value=tool_response)

    term_match_counts: Dict[str, int] = {}
    for term in query_terms:
        if isinstance(term, str):
            normalized = term.casefold().strip()
            if normalized != "":
                term_match_counts[normalized] = 0

    node_summaries: List[dict] = []
    stack: List[tuple[dict, int]] = [(data, 0)]
    while len(stack) > 0:
        node, depth = stack.pop(0)
        if not isinstance(node, dict):
            continue
        if "note" not in node:
            continue
        note = node["note"]
        if not isinstance(note, dict):
            continue
        if "id" in note:
            note_id = note["id"]
        else:
            note_id = None
        if not isinstance(note_id, str) or note_id == "":
            continue
        if "content" in note:
            raw_content = note["content"]
        else:
            raw_content = None
        if not isinstance(raw_content, str):
            raw_content = ""
        plain_content = _strip_html_to_text(text=raw_content)
        folded_plain = plain_content.casefold()
        for term in term_match_counts:
            term_match_counts[term] += folded_plain.count(term)
        snippets = _extract_term_snippets(
            plain_text=plain_content,
            terms=query_terms,
            max_snippets=3,
        )

        if "tags" in node:
            tags = node["tags"]
        else:
            tags = None
        if not isinstance(tags, dict):
            tags = {}
        if "tag_terms" in tags:
            tag_terms = tags["tag_terms"]
        else:
            tag_terms = None
        if not isinstance(tag_terms, list):
            tag_terms = []
        if "effective_tag_terms" in tags:
            effective_tag_terms = tags["effective_tag_terms"]
        else:
            effective_tag_terms = None
        if not isinstance(effective_tag_terms, list):
            effective_tag_terms = []

        if "parent_id" in note:
            parent_id = note["parent_id"]
        else:
            parent_id = None
        node_summaries.append(
            {
                "note_id": note_id,
                "parent_id": parent_id,
                "depth": depth,
                "tag_terms": tag_terms[:12],
                "effective_tag_terms": effective_tag_terms[:16],
                "content_excerpt": _compact_text_for_context(text=plain_content, max_chars=1200),
                "term_snippets": snippets,
                "term_snippet_count": len(snippets),
            }
        )

        if "children" in node:
            children = node["children"]
        else:
            children = None
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    stack.append((child, depth + 1))

    node_summaries.sort(
        key=lambda item: (
            -item["term_snippet_count"],
            item["depth"],
            item["note_id"],
        )
    )

    return {
        "ok": True,
        "data": {
            "root_note_id": root_note["id"] if "id" in root_note else None,
            "total_nodes": len(node_summaries),
            "query_terms": list(term_match_counts.keys()),
            "term_match_counts": term_match_counts,
            "node_summaries": node_summaries[:8],
        },
    }


def _compact_json_payload(
    *,
    value: object,
    max_depth: int,
    max_list_items: int,
    max_dict_items: int,
    max_string_chars: int,
) -> object:
    if isinstance(value, dict):
        if max_depth <= 0:
            return {
                "_max_depth_reached": True,
                "_truncated_keys": len(value),
            }
        compact: Dict[str, object] = {}
        keys = list(value.keys())
        for key in keys[:max_dict_items]:
            if not isinstance(key, str):
                normalized_key = str(key)
            else:
                normalized_key = key
            compact[normalized_key] = _compact_json_payload(
                value=value[key],
                max_depth=max_depth - 1,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
                max_string_chars=max_string_chars,
            )
        if len(keys) > max_dict_items:
            compact["_truncated_keys"] = len(keys) - max_dict_items
        return compact

    if isinstance(value, list):
        if max_depth <= 0:
            return [
                {
                    "_max_depth_reached": True,
                    "_truncated_items": len(value),
                }
            ]
        compact_items: List[object] = []
        for item in value[:max_list_items]:
            compact_items.append(
                _compact_json_payload(
                    value=item,
                    max_depth=max_depth - 1,
                    max_list_items=max_list_items,
                    max_dict_items=max_dict_items,
                    max_string_chars=max_string_chars,
                )
            )
        if len(value) > max_list_items:
            compact_items.append({"_truncated_items": len(value) - max_list_items})
        return compact_items

    if isinstance(value, str):
        return _compact_text_for_context(text=value, max_chars=max_string_chars)

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return _compact_text_for_context(text=repr(value), max_chars=max_string_chars)


def _compact_for_model(*, value: object) -> object:
    return _compact_json_payload(
        value=value,
        max_depth=5,
        max_list_items=8,
        max_dict_items=20,
        max_string_chars=260,
    )


def _compact_for_output(*, value: object) -> object:
    return _compact_json_payload(
        value=value,
        max_depth=6,
        max_list_items=25,
        max_dict_items=40,
        max_string_chars=420,
    )


def _invalid_decision_feedback_message(*, error_text: str) -> str:
    return (
        "FORMAT_ERROR: "
        + error_text
        + " Return only one JSON object with exactly one action: "
        + '{"action":"tool","tool_name":"<name>","arguments":{...},"reason":"<brief>"} '
        + 'OR {"action":"final","answer":"<response for user>"} .'
    )


def _answer_needs_synthesis_pass(*, answer: str) -> bool:
    if not isinstance(answer, str):
        raise TypeError("answer must be a string")
    normalized = answer.casefold()
    if "note id:" in normalized:
        return True
    if "matching notes" in normalized:
        return True
    if "here are" in normalized:
        return True
    if re.search(r"(?m)^\s*\d+\.\s", answer) is not None:
        return True
    return False


def _collect_synthesis_evidence(*, steps: List[dict]) -> dict:
    if not isinstance(steps, list):
        raise TypeError("steps must be an array")

    search_hits: List[dict] = []
    hydrated_notes: List[dict] = []
    seen_search_ids = set()
    seen_hydrated_ids = set()

    for step in steps:
        if not isinstance(step, dict):
            continue
        if "action" not in step:
            continue
        action = step["action"]
        if action != "tool":
            continue
        if "tool_name" not in step:
            continue
        tool_name = step["tool_name"]
        if not isinstance(tool_name, str):
            continue
        if "tool_response" not in step:
            continue
        tool_response = step["tool_response"]
        if not isinstance(tool_response, dict):
            continue
        if "ok" not in tool_response:
            continue
        ok_value = tool_response["ok"]
        if ok_value is not True:
            continue
        if "data" not in tool_response:
            continue
        data = tool_response["data"]
        if not isinstance(data, dict):
            continue

        if tool_name == "search_notes":
            if "results" not in data:
                continue
            results = data["results"]
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                if "note_id" not in result:
                    continue
                note_id = result["note_id"]
                if not isinstance(note_id, str) or note_id == "":
                    continue
                if note_id in seen_search_ids:
                    continue
                seen_search_ids.add(note_id)

                preview_text = ""
                if "preview_text" in result and isinstance(result["preview_text"], str):
                    preview_text = result["preview_text"]
                context_text = ""
                if "context_text" in result and isinstance(result["context_text"], str):
                    context_text = result["context_text"]
                tag_terms: List[str] = []
                if "tag_terms" in result and isinstance(result["tag_terms"], list):
                    tag_terms = [term for term in result["tag_terms"] if isinstance(term, str)]
                effective_tag_terms: List[str] = []
                if "effective_tag_terms" in result and isinstance(result["effective_tag_terms"], list):
                    effective_tag_terms = [term for term in result["effective_tag_terms"] if isinstance(term, str)]

                search_hits.append(
                    {
                        "note_id": note_id,
                        "preview_text": preview_text,
                        "context_text": _compact_text_for_context(text=context_text, max_chars=800) if context_text != "" else "",
                        "tag_terms": tag_terms[:12],
                        "effective_tag_terms": effective_tag_terms[:16],
                    }
                )
                if len(search_hits) >= 16:
                    break
            continue

        if tool_name == "get_note":
            if "note" not in data:
                continue
            note = data["note"]
            if not isinstance(note, dict):
                continue
            if "id" not in note:
                continue
            note_id = note["id"]
            if not isinstance(note_id, str) or note_id == "":
                continue
            if note_id in seen_hydrated_ids:
                continue
            seen_hydrated_ids.add(note_id)

            content_text = ""
            if "content_text" in note and isinstance(note["content_text"], str):
                content_text = note["content_text"]
            elif "content" in note and isinstance(note["content"], str):
                content_text = _strip_html_to_text(text=note["content"])
            context_text = ""
            if "context_text" in data and isinstance(data["context_text"], str):
                context_text = data["context_text"]

            ancestor_chain: List[dict] = []
            if "ancestors" in data and isinstance(data["ancestors"], list):
                for ancestor in data["ancestors"]:
                    if not isinstance(ancestor, dict):
                        continue
                    if "note" not in ancestor:
                        continue
                    ancestor_note = ancestor["note"]
                    if not isinstance(ancestor_note, dict):
                        continue
                    if "id" not in ancestor_note:
                        continue
                    ancestor_id = ancestor_note["id"]
                    if not isinstance(ancestor_id, str) or ancestor_id == "":
                        continue
                    ancestor_text = ""
                    if "content_text" in ancestor_note and isinstance(ancestor_note["content_text"], str):
                        ancestor_text = ancestor_note["content_text"]
                    elif "content" in ancestor_note and isinstance(ancestor_note["content"], str):
                        ancestor_text = _strip_html_to_text(text=ancestor_note["content"])
                    ancestor_chain.append(
                        {
                            "note_id": ancestor_id,
                            "content_text": _compact_text_for_context(text=ancestor_text, max_chars=500),
                        }
                    )

            hydrated_notes.append(
                {
                    "note_id": note_id,
                    "content_text": _compact_text_for_context(text=content_text, max_chars=900),
                    "context_text": _compact_text_for_context(text=context_text, max_chars=1200) if context_text != "" else "",
                    "ancestors": ancestor_chain[:8],
                }
            )
            continue

    return {
        "search_hits": search_hits,
        "hydrated_notes": hydrated_notes,
    }


def _run_synthesis_pass(
    *,
    user_message: str,
    draft_answer: str,
    steps: List[dict],
    ollama_chat_url: str,
    model: str,
) -> str:
    evidence = _collect_synthesis_evidence(steps=steps)
    synthesis_system_prompt = (
        "You are a synthesis pass for MetaList3 retrieval results. "
        "Given the user question, a draft answer, and structured evidence, "
        "produce one concise best-supported answer. "
        "Do not dump candidate lists. "
        "If evidence is insufficient or conflicting, state that briefly and ask one concise clarification. "
        "Return ONLY JSON: {\"action\":\"final\",\"answer\":\"...\"}."
    )
    synthesis_user_payload = {
        "question": user_message,
        "draft_answer": draft_answer,
        "evidence": _compact_for_model(value=evidence),
    }
    decision = _ollama_chat_json(
        ollama_chat_url=ollama_chat_url,
        model=model,
        messages=[
            {"role": "system", "content": synthesis_system_prompt},
            {"role": "user", "content": json.dumps(synthesis_user_payload, ensure_ascii=False)},
        ],
    )

    if not isinstance(decision, dict):
        return draft_answer
    if "action" not in decision:
        return draft_answer
    action = decision["action"]
    if action != "final":
        return draft_answer
    if "answer" not in decision:
        return draft_answer
    answer = decision["answer"]
    if not isinstance(answer, str):
        return draft_answer
    if answer.strip() == "":
        return draft_answer
    return answer


def _build_agent_system_prompt(
    *,
    tool_summaries: List[dict],
    planning_context: dict | None,
) -> str:
    tools_json = json.dumps(tool_summaries, ensure_ascii=False)
    planning_block = ""
    if isinstance(planning_context, dict):
        planning_block = (
            " Retrieval planning context for this specific request (generated before tool-use): "
            + json.dumps(_compact_for_model(value=planning_context), ensure_ascii=False)
            + " Treat this as guidance, not certainty. "
        )
    return (
        "You are an agent for MetaList3 (ML3), a personal knowledge management system (PKMS). "
        "Use tools iteratively and reason from evidence, not guesses. "
        "Domain model: notes are hierarchical (parent/child). "
        "Root-level notes have a stable order; items nearer the top are often more recent/important, "
        "but this is only a weak tie-breaker and not a hard rule. "
        "Each note has content and tags. "
        "Tag semantics: raw_tag_string is the raw stored tag text on the note; "
        "tag_terms are explicit normalized tags on that note; "
        "tags can be inherited downward from ancestors; "
        "implied_tag_terms are ontology-inferred tags from explicit+inherited tags; "
        "effective_tag_terms are the full semantic tag coverage used for matching. "
        "search_notes query syntax is strict: "
        "unquoted tokens are required tag terms; "
        "prefix '-' excludes a tag term; "
        "quoted terms (e.g. \"estate plan\") are required text phrases; "
        "prefix '-\"...\"' excludes a text phrase. "
        "There is no OR operator. "
        "Retrieval semantics: search is conjunction-oriented and strict, with no OR operator. "
        "A single free-text query may miss relevant notes; use multiple search_notes calls when needed and combine evidence across results. "
        "search_notes argument rule: required_tags and forbidden_tags are appended into query semantics, "
        "so prefer encoding tag constraints directly in query and keep required_tags/forbidden_tags empty unless you intentionally need split fields. "
        "When concepts are likely tags, prefer precise tag-term tokens over broad natural-language phrases. "
        "For alternatives/synonyms, run multiple searches and compare/intersect note_ids under the hood. "
        "Do not repeat semantically equivalent search_notes calls (e.g. reordered tokens with same meaning). "
        "Do not rely on first hit ordering; evaluate candidates by direct evidence in content and tag context. "
        "If previews are insufficient, call get_note and inspect full note content/subtree before finalizing. "
        "If multiple plausible candidates remain, do an internal comparison pass and return one concrete best-supported answer instead of a candidate dump. "
        "Avoid list_children(parent_id=null) for fact lookup because it returns only a windowed top-level slice; "
        "use it primarily for hierarchy/navigation requests. "
        "Never invent note ids; only use ids returned by tools. "
        "Use tool inputSchema exactly; do not send extra keys. "
        "If a tool returns an argument error, fix and retry. "
        "If evidence is truly ambiguous, ask a concise clarifying question. "
        "Respond with concise final answers grounded in retrieved evidence. "
        + planning_block
        + "You DO have access to the user's notes via tools in this session. "
        "Never claim you lack access to personal data; instead, use tools. "
        "For any question about the user's notes, you must call at least one tool "
        "before producing a final answer (unless the user explicitly asks for a non-note explanation). "
        "The FIRST response in the loop must be an action='tool' call. "
        "Do not answer, summarize, or ask clarifying questions before at least one tool call. "
        + "MetaList text search note: query matching is literal/conjunctive; natural-language strings like "
        "'dad birthday' often miss relevant notes unless that literal phrase exists. "
        "Prefer tag-driven retrieval and multiple focused searches. "
        "Never return an empty JSON object. If you cannot comply, return "
        '{"action":"error","error":"<brief reason>"} . '
        "Available tools are: "
        + tools_json
        + " . Return ONLY JSON with one of these exact shapes: "
        + '{"action":"tool","tool_name":"<name>","arguments":{...},"reason":"<brief>"} '
        + 'OR {"action":"final","answer":"<response for user>"} .'
    )


def _coerce_string_list(*, value: object, max_items: int) -> List[str]:
    if max_items <= 0:
        raise ValueError("max_items must be > 0")
    if not isinstance(value, list):
        return []

    normalized: List[str] = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text == "":
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= max_items:
            break
    return normalized


def _normalize_tag_term(*, value: str) -> str:
    lowered = value.casefold()
    collapsed = re.sub(r"\s+", "-", lowered).strip("-")
    cleaned = re.sub(r"[^a-z0-9@._-]+", "", collapsed)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned


def _tokenize_tag_term(*, value: str) -> List[str]:
    normalized = _normalize_tag_term(value=value)
    if normalized == "":
        return []
    tokens = [token for token in re.split(r"[-_.]+", normalized) if token != ""]
    return tokens


def _singularize_tag_term(*, value: str) -> str:
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith(("ches", "shes", "xes", "zes", "sses", "oes")) and len(value) > 4:
        return value[:-2]
    if value.endswith("s") and len(value) > 3 and not value.endswith("ss"):
        return value[:-1]
    return value


def _match_hypothesized_tags_to_catalog(*, hypothesized_tags: List[str], tag_entries: List[dict]) -> dict:
    if not isinstance(hypothesized_tags, list):
        raise TypeError("hypothesized_tags must be an array")
    if not isinstance(tag_entries, list):
        raise TypeError("tag_entries must be an array")

    catalog: List[dict] = []
    by_key: Dict[str, dict] = {}
    for entry in tag_entries:
        if not isinstance(entry, dict):
            continue
        tag = entry.get("tag")
        count = entry.get("count")
        if not isinstance(tag, str) or tag == "":
            continue
        if not isinstance(count, int) or count <= 0:
            continue
        key = _normalize_tag_term(value=tag)
        if key == "":
            continue
        record = {
            "tag": tag,
            "count": count,
            "key": key,
            "tokens": set(_tokenize_tag_term(value=key)),
        }
        catalog.append(record)
        previous = by_key.get(key)
        if previous is None or previous["count"] < count:
            by_key[key] = record

    exact_matches: List[dict] = []
    fuzzy_matches: List[dict] = []
    unmatched: List[str] = []

    for guess in hypothesized_tags:
        if not isinstance(guess, str):
            continue
        guess_key = _normalize_tag_term(value=guess)
        if guess_key == "":
            continue

        exact = by_key.get(guess_key)
        has_exact = exact is not None
        if exact is not None:
            exact_matches.append(
                {
                    "hypothesis": guess_key,
                    "catalog_tag": exact["tag"],
                    "count": exact["count"],
                }
            )

        guess_token_list = _tokenize_tag_term(value=guess_key)
        guess_tokens = set(guess_token_list)
        guess_token_count = len(guess_tokens)
        guess_singular = _singularize_tag_term(value=guess_key)
        candidates: List[dict] = []
        for candidate in catalog:
            candidate_key = candidate["key"]
            if candidate_key == guess_key:
                continue
            candidate_tokens = candidate["tokens"]
            candidate_token_count = len(candidate_tokens)
            # Directional fuzzy rule: allow normalization/shrinking, not expansion.
            # Example blocked: topic -> topic-modeling.
            is_prefix_extension = candidate_key.startswith(f"{guess_key}-")
            is_token_expansion = (
                guess_token_count > 0
                and candidate_token_count > guess_token_count
                and guess_tokens.issubset(candidate_tokens)
            )
            if is_prefix_extension or is_token_expansion:
                continue
            score = 0.0
            match_type = ""

            min_length = min(len(guess_key), len(candidate_key))
            if (
                min_length >= 3
                and guess_key.startswith(candidate_key)
                and guess_key.startswith(f"{candidate_key}-")
            ):
                score = 0.92
                match_type = "prefix"

            candidate_singular = _singularize_tag_term(value=candidate_key)
            if guess_singular == candidate_singular and len(candidate_singular) >= 4:
                if 0.97 > score:
                    score = 0.97
                    match_type = "morphological"

            if len(guess_tokens) > 0:
                overlap = guess_tokens.intersection(candidate_tokens)
                if len(overlap) > 0:
                    overlap_count = len(overlap)
                    # Guardrail: for multi-token tags, one shared token is too
                    # weak and causes noisy jumps (e.g., social-sciences ->
                    # social-media). Require stronger overlap.
                    if (
                        len(guess_tokens) >= 2
                        and len(candidate["tokens"]) >= 2
                        and overlap_count < 2
                    ):
                        overlap = set()
                if len(overlap) > 0:
                    guess_coverage = len(overlap) / len(guess_tokens)
                    if len(candidate_tokens) == 0:
                        raise TypeError("candidate tokens must not be empty")
                    candidate_coverage = len(overlap) / len(candidate_tokens)
                    longest_overlap = max(len(token) for token in overlap)
                    # Require meaningful bidirectional overlap to avoid noisy
                    # one-token collisions like "field" -> "field-of-glory".
                    if (
                        guess_coverage >= 0.5
                        and candidate_coverage >= 0.5
                        and longest_overlap >= 4
                    ):
                        token_score = 0.80 + min(0.12, 0.06 * len(overlap))
                        if token_score > score:
                            score = token_score
                            match_type = "token-overlap"

            similarity = difflib.SequenceMatcher(a=guess_key, b=candidate_key).ratio()
            if (
                similarity >= 0.86
                and abs(len(guess_key) - len(candidate_key)) <= 3
                and guess_key[0] == candidate_key[0]
                and similarity > score
            ):
                score = similarity
                match_type = "string-similarity"

            if score < 0.80:
                continue

            # If we already have an exact hit, keep fuzzy companions very strict
            # to avoid broad noisy fan-out while still catching close variants
            # like singular/plural.
            if has_exact:
                is_morphological = match_type == "morphological"
                is_close_similarity = match_type == "string-similarity" and score >= 0.92
                if not (is_morphological or is_close_similarity):
                    continue

            candidates.append(
                {
                    "hypothesis": guess_key,
                    "catalog_tag": candidate["tag"],
                    "count": candidate["count"],
                    "score": round(score, 3),
                    "match_type": match_type,
                }
            )

        candidates.sort(
            key=lambda item: (
                -item["score"],
                -item["count"],
                item["catalog_tag"].casefold(),
            )
        )
        top_candidates = candidates[:4]
        if len(top_candidates) == 0:
            if not has_exact:
                unmatched.append(guess_key)
            continue
        fuzzy_matches.extend(top_candidates)

    resolved_tags: List[str] = []
    seen_resolved = set()
    for match in exact_matches:
        catalog_tag = match["catalog_tag"]
        key = catalog_tag.casefold()
        if key in seen_resolved:
            continue
        seen_resolved.add(key)
        resolved_tags.append(catalog_tag)
    for match in fuzzy_matches:
        catalog_tag = match["catalog_tag"]
        key = catalog_tag.casefold()
        if key in seen_resolved:
            continue
        seen_resolved.add(key)
        resolved_tags.append(catalog_tag)

    return {
        "catalog_tag_count": len(catalog),
        "hypothesized_tag_count": len(hypothesized_tags),
        "exact_matches": exact_matches,
        "fuzzy_matches": fuzzy_matches,
        "resolved_tags": resolved_tags,
        "unmatched_hypothesized_tags": unmatched,
    }


def _normalize_query_hypothesis(*, payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Planner output must be a JSON object")
    if "reasoning" not in payload or "hypothesized_tags" not in payload:
        raise ValueError("Planner output missing required fields")

    reasoning_value = payload.get("reasoning")
    if not isinstance(reasoning_value, str) or reasoning_value.strip() == "":
        raise ValueError("Planner reasoning must be a non-empty string")
    reasoning = reasoning_value.strip()

    raw_hypothesized_tags = _coerce_string_list(value=payload.get("hypothesized_tags"), max_items=32)
    if len(raw_hypothesized_tags) == 0:
        raise ValueError("Planner hypothesized_tags must include at least one entry")

    normalized_tags: List[str] = []
    seen_tags = set()
    for tag in raw_hypothesized_tags:
        lowered = tag.casefold()
        collapsed = re.sub(r"\s+", "-", lowered).strip("-")
        cleaned = re.sub(r"[^a-z0-9@._-]+", "", collapsed)
        cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
        if len(cleaned) < 2:
            continue
        if cleaned in seen_tags:
            continue
        seen_tags.add(cleaned)
        normalized_tags.append(cleaned)
        if len(normalized_tags) >= 24:
            break
    if len(normalized_tags) == 0:
        raise ValueError("Planner hypothesized_tags must include at least one usable entry")

    return {
        "reasoning": reasoning,
        "hypothesized_tags": normalized_tags,
    }


def _build_planner_seed_tags_prompt_message(*, seed_tag_entries: List[dict], mode: str) -> str:
    if not isinstance(seed_tag_entries, list):
        raise TypeError("seed_tag_entries must be an array")
    hints: List[dict] = []
    for entry in seed_tag_entries:
        if not isinstance(entry, dict):
            continue
        tag = entry.get("tag")
        count = entry.get("count")
        if not isinstance(tag, str) or tag == "":
            continue
        if not isinstance(count, int) or count <= 0:
            continue
        hints.append({"tag": tag, "count": count})
    if len(hints) == 0:
        return ""

    return (
        "Deterministic context from tools (not model-generated): top existing tags in this vault by frequency. "
        "These are popularity-biased and may be unrelated to this specific query. "
        "Do NOT treat them as a candidate answer list. "
        "Use them only as weak vocabulary hints after generating query-driven hypotheses. "
        "If a seed tag is not semantically aligned to the user query, ignore it. "
        "Seed-tag count mode: "
        + mode
        + ". Top tags JSON: "
        + json.dumps(hints, ensure_ascii=False)
    )


def _build_query_hypothesis_messages(
    *,
    user_message: str,
    seed_tag_entries: List[dict],
    seed_tag_count_mode: str,
) -> List[dict]:
    planning_system_prompt = (
        "You are a retrieval planner for MetaList3 (ML3), a hierarchical PKMS where notes have tags, "
        "inferred tags, and inherited tags from ancestors. "
        "Your task is ONLY to hypothesize likely tags that might exist for the user question before any tool calls. "
        "Do not assume you know the real tag vocabulary. "
        "Constraints: keep outputs concise and broadly useful (not overfit to one fixed question pattern). "
        "Work in three passes: "
        "Pass 1: generate query-only anchors and close lexical variants (singular/plural, simple stems, near-synonyms), "
        "without using seed context. "
        "Pass 2: add 2-6 broader container/context tags that would commonly co-occur in notes with those anchors. "
        "Pass 3: if seed context exists, optionally swap only a few terms to aligned in-vault vocabulary. "
        "At least 70% of tags must be Pass 1 anchor tags. "
        "At least 8 hypothesized tags must come from query-derived anchors/variants, even if seed context is present. "
        "Never choose a tag only because it appears in the seed list. "
        "If seed tags are mostly unrelated, ignore them and keep query-driven guesses. "
        "Do not infer hidden personal interests or niche subdomains unless explicitly signaled by the query text. "
        "Prefer concrete retrieval nouns (entities, events, documents, media, activities) over abstract fields. "
        "When the query asks about patterns/habits/topics, prioritize retrieval-signal tags that help locate evidence "
        "(artifact type, source/channel, format, workflow context, and time framing) before broad subject taxonomies. "
        "Do not output long generic discipline lists unless those disciplines are explicitly present in the query text. "
        "Target 16-24 hypothesized tags; default to about 20 when possible. "
        "Do not return fewer than 12 unless the query is too short to support more grounded variants. "
        "Return ONLY JSON with this exact shape: "
        '{"reasoning":"<1-3 sentences>","hypothesized_tags":["..."]}. '
        "hypothesized_tags should be lowercase tag-like terms (kebab-case where useful), 2+ chars each."
    )
    messages: List[dict] = [
        {"role": "system", "content": planning_system_prompt},
    ]
    seed_tags_message = _build_planner_seed_tags_prompt_message(
        seed_tag_entries=seed_tag_entries,
        mode=seed_tag_count_mode,
    )
    if seed_tags_message != "":
        messages.append({"role": "system", "content": seed_tags_message})
    messages.append({"role": "user", "content": user_message})
    return messages


def _extract_tag_entries_from_list_tags(*, parsed_list_tags: dict) -> List[dict]:
    if not isinstance(parsed_list_tags, dict):
        return []
    if "ok" not in parsed_list_tags:
        return []
    ok_value = parsed_list_tags["ok"]
    if ok_value is not True:
        return []
    if "data" not in parsed_list_tags:
        return []
    data = parsed_list_tags["data"]
    if not isinstance(data, dict):
        return []
    if "tags" not in data:
        return []
    tags = data["tags"]
    if not isinstance(tags, list):
        return []

    entries: List[dict] = []
    for tag_entry in tags:
        if not isinstance(tag_entry, dict):
            continue
        tag = tag_entry.get("tag")
        count = tag_entry.get("count")
        if not isinstance(tag, str) or tag == "":
            continue
        if not isinstance(count, int) or count <= 0:
            continue
        entries.append(
            {
                "tag": tag,
                "count": count,
            }
        )
    return entries


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
    response = _post_json(
        url=ollama_chat_url,
        payload=payload,
        timeout_seconds=_OLLAMA_CHAT_TIMEOUT_SECONDS,
    )
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


def _ollama_chat_json_with_raw(
    *,
    ollama_chat_url: str,
    model: str,
    messages: List[dict],
) -> tuple[dict, str]:
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
    response = _post_json(
        url=ollama_chat_url,
        payload=payload,
        timeout_seconds=_OLLAMA_CHAT_TIMEOUT_SECONDS,
    )
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
    return parsed, content


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
        if "name" not in summary:
            continue
        if summary["name"] != tool_name:
            continue
        if "inputSchema" not in summary:
            return None
        schema = summary["inputSchema"]
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


def _normalize_search_notes_tag_list(*, values: object, field_name: str) -> dict:
    if not isinstance(values, list):
        return {
            "ok": False,
            "error": f"{field_name} must be a list of non-empty strings.",
        }

    normalized: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            return {
                "ok": False,
                "error": f"{field_name} entries must be non-empty strings.",
            }
        tag = value.strip()
        if tag == "":
            return {
                "ok": False,
                "error": f"{field_name} entries must be non-empty strings.",
            }
        if tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return {
        "ok": True,
        "values": normalized,
    }


def _canonicalize_search_notes_arguments(*, arguments: dict) -> dict:
    if "query" not in arguments:
        return {
            "ok": False,
            "error": "search_notes requires query.",
        }
    query_value = arguments["query"]
    if not isinstance(query_value, str):
        return {
            "ok": False,
            "error": "search_notes query must be a string.",
        }

    required_raw = arguments["required_tags"] if "required_tags" in arguments else []
    forbidden_raw = arguments["forbidden_tags"] if "forbidden_tags" in arguments else []
    normalized_required_result = _normalize_search_notes_tag_list(
        values=required_raw,
        field_name="required_tags",
    )
    if normalized_required_result["ok"] is not True:
        return normalized_required_result
    normalized_forbidden_result = _normalize_search_notes_tag_list(
        values=forbidden_raw,
        field_name="forbidden_tags",
    )
    if normalized_forbidden_result["ok"] is not True:
        return normalized_forbidden_result

    normalized_required = normalized_required_result["values"]
    normalized_forbidden = normalized_forbidden_result["values"]
    if not isinstance(normalized_required, list):
        raise TypeError("normalized_required must be an array")
    if not isinstance(normalized_forbidden, list):
        raise TypeError("normalized_forbidden must be an array")

    overlap = set(normalized_required).intersection(normalized_forbidden)
    if len(overlap) > 0:
        overlap_display = ", ".join(sorted(overlap, key=str.casefold))
        return {
            "ok": False,
            "error": f"search_notes has overlapping required/forbidden tags: {overlap_display}",
        }

    normalized_query = re.sub(r"\s+", " ", query_value).strip()
    query_parts: List[str] = []
    if normalized_query != "":
        query_parts.append(normalized_query)
    query_parts.extend(normalized_required)
    query_parts.extend(f"-{tag}" for tag in normalized_forbidden)
    canonical_query = " ".join(query_parts).strip()

    try:
        parse_search_query(canonical_query)
    except ValueError as error:
        return {
            "ok": False,
            "error": f"Invalid search_notes query: {error}",
        }

    normalized_arguments = dict(arguments)
    normalized_arguments["query"] = canonical_query
    normalized_arguments["required_tags"] = []
    normalized_arguments["forbidden_tags"] = []

    return {
        "ok": True,
        "arguments": normalized_arguments,
        "changed": normalized_arguments != arguments,
    }


def _search_notes_semantic_signature(*, arguments: dict) -> str:
    if "query" not in arguments:
        raise RuntimeError("search_notes arguments missing query")
    query = arguments["query"]
    if not isinstance(query, str):
        raise TypeError("search_notes query must be a string")

    parsed = parse_search_query(query)

    limit = arguments["limit"] if "limit" in arguments else None
    offset = arguments["offset"] if "offset" in arguments else None
    if limit is not None and not isinstance(limit, int):
        limit = None
    if offset is not None and not isinstance(offset, int):
        offset = None

    signature_payload = {
        "required_tags": sorted(tag.casefold() for tag in parsed.required_tags),
        "forbidden_tags": sorted(tag.casefold() for tag in parsed.forbidden_tags),
        "required_text": sorted(parsed.required_text),
        "forbidden_text": sorted(parsed.forbidden_text),
        "limit": limit,
        "offset": offset,
    }
    return json.dumps(signature_payload, sort_keys=True, ensure_ascii=False)


def _search_notes_regex_semantic_signature(*, arguments: dict) -> str:
    pattern = arguments.get("pattern")
    flags = arguments.get("flags")
    regex_engine = arguments.get("regex_engine")
    target = arguments.get("target")
    limit = arguments.get("limit")
    offset = arguments.get("offset")
    if not isinstance(pattern, str):
        pattern = ""
    if not isinstance(flags, str):
        flags = ""
    if not isinstance(regex_engine, str):
        regex_engine = ""
    if not isinstance(target, str):
        target = ""
    if not isinstance(limit, int):
        limit = None
    if not isinstance(offset, int):
        offset = None

    scope_note_ids = arguments.get("scope_note_ids")
    scope_note_ids_count = 0
    if isinstance(scope_note_ids, list):
        scope_note_ids_count = len(scope_note_ids)
    scope_query = arguments.get("scope_query")
    if not isinstance(scope_query, str):
        scope_query = ""

    signature_payload = {
        "pattern": pattern,
        "flags": flags,
        "regex_engine": regex_engine.casefold(),
        "target": target.casefold(),
        "scope_note_ids_count": scope_note_ids_count,
        "scope_query": re.sub(r"\s+", " ", scope_query).strip().casefold(),
        "limit": limit,
        "offset": offset,
    }
    return json.dumps(signature_payload, sort_keys=True, ensure_ascii=False)


def _rewrite_tool_call_semantic_signature(*, tool_name: str, arguments: dict) -> str:
    if not isinstance(tool_name, str):
        raise TypeError("tool_name must be a string")
    if not isinstance(arguments, dict):
        raise TypeError("arguments must be an object")
    if tool_name == "search_notes":
        return "search_notes:" + _search_notes_semantic_signature(arguments=arguments)
    if tool_name == "search_notes_regex":
        return "search_notes_regex:" + _search_notes_regex_semantic_signature(
            arguments=arguments
        )
    return tool_name + ":" + json.dumps(arguments, sort_keys=True, ensure_ascii=False)


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

    schema_properties = None
    if "properties" in schema:
        schema_properties = schema["properties"]
    schema_required = None
    if "required" in schema:
        schema_required = schema["required"]
    additional_properties = None
    if "additionalProperties" in schema:
        additional_properties = schema["additionalProperties"]
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

    if tool_name == "search_notes":
        canonical_result = _canonicalize_search_notes_arguments(arguments=normalized_arguments)
        if canonical_result["ok"] is not True:
            return canonical_result
        normalized_arguments = canonical_result["arguments"]
        if bool(canonical_result["changed"]):
            changed = True

    return {
        "ok": True,
        "arguments": normalized_arguments,
        "changed": changed,
    }


def _is_tool_available(*, tool_summaries: List[dict], tool_name: str) -> bool:
    for summary in tool_summaries:
        if not isinstance(summary, dict):
            continue
        if "name" not in summary:
            continue
        if summary["name"] == tool_name:
            return True
    return False


def _query_terms_for_tags(*, user_message: str) -> List[str]:
    stop_terms = {
        "a",
        "an",
        "and",
        "do",
        "for",
        "i",
        "in",
        "is",
        "my",
        "of",
        "please",
        "tell",
        "the",
        "to",
        "what",
        "when",
    }
    terms: List[str] = []
    seen = set()
    words = re.findall(r"[a-zA-Z0-9'’]+", user_message.casefold())
    for raw_word in words:
        word = raw_word.strip("'")
        word = word.strip("’")
        if word.endswith("'s"):
            word = word[:-2]
        if word.endswith("’s"):
            word = word[:-2]
        if word == "":
            continue
        if word in stop_terms:
            continue
        if word in seen:
            continue
        seen.add(word)
        terms.append(word)
    return terms


def _build_compact_search_query(*, user_message: str) -> str:
    terms = _query_terms_for_tags(user_message=user_message)
    if len(terms) > 0:
        return " ".join(terms[:6])
    normalized = re.sub(r"\s+", " ", user_message).strip()
    return normalized


def _build_tag_discovery_terms(*, user_message: str) -> List[str]:
    discovered: List[str] = []
    for term in _query_terms_for_tags(user_message=user_message):
        if len(term) < 2:
            continue
        discovered.append(term)
        if len(discovered) >= 4:
            break
    return discovered


def _extract_note_ids_and_entries_from_search_response(*, parsed_search: dict) -> dict:
    note_ids = set()
    entries_by_id: Dict[str, dict] = {}
    if "data" not in parsed_search:
        return {
            "note_ids": note_ids,
            "entries_by_id": entries_by_id,
        }
    data = parsed_search["data"]
    if not isinstance(data, dict):
        return {
            "note_ids": note_ids,
            "entries_by_id": entries_by_id,
        }
    if "results" not in data:
        return {
            "note_ids": note_ids,
            "entries_by_id": entries_by_id,
        }
    results = data["results"]
    if not isinstance(results, list):
        return {
            "note_ids": note_ids,
            "entries_by_id": entries_by_id,
        }
    for entry in results:
        if not isinstance(entry, dict):
            continue
        if "note_id" not in entry:
            continue
        note_id = entry["note_id"]
        if not isinstance(note_id, str) or note_id == "":
            continue
        note_ids.add(note_id)
        if note_id not in entries_by_id:
            entries_by_id[note_id] = entry
    return {
        "note_ids": note_ids,
        "entries_by_id": entries_by_id,
    }


def _extract_tag_candidates_from_list_tags_response(*, parsed_list_tags: dict, prefix: str) -> List[dict]:
    candidates: List[dict] = []
    if "data" not in parsed_list_tags:
        return candidates
    data = parsed_list_tags["data"]
    if not isinstance(data, dict):
        return candidates
    if "tags" not in data:
        return candidates
    tags = data["tags"]
    if not isinstance(tags, list):
        return candidates

    prefix_casefold = prefix.casefold()
    for entry in tags:
        if not isinstance(entry, dict):
            continue
        if "tag" not in entry:
            continue
        if "count" not in entry:
            continue
        tag = entry["tag"]
        count = entry["count"]
        if not isinstance(tag, str) or tag == "":
            continue
        if not isinstance(count, int) or count <= 0:
            continue
        if not tag.casefold().startswith(prefix_casefold):
            continue
        candidates.append(
            {
                "tag": tag,
                "count": count,
                "exact": tag.casefold() == prefix_casefold,
            }
        )

    candidates.sort(
        key=lambda item: (
            0 if item["exact"] else 1,
            item["count"],
            item["tag"].casefold(),
        )
    )
    return candidates[:5]


def _plan_two_tag_combinations(*, discovered_terms: List[dict]) -> List[dict]:
    combos: List[dict] = []
    seen = set()
    for left_index in range(len(discovered_terms)):
        left_entry = discovered_terms[left_index]
        left_term = left_entry["term"]
        left_candidates = left_entry["candidates"]
        if not isinstance(left_term, str):
            raise TypeError("left term must be a string")
        if not isinstance(left_candidates, list):
            raise TypeError("left candidates must be an array")
        for right_index in range(left_index + 1, len(discovered_terms)):
            right_entry = discovered_terms[right_index]
            right_term = right_entry["term"]
            right_candidates = right_entry["candidates"]
            if not isinstance(right_term, str):
                raise TypeError("right term must be a string")
            if not isinstance(right_candidates, list):
                raise TypeError("right candidates must be an array")
            for left_candidate in left_candidates[:3]:
                if not isinstance(left_candidate, dict):
                    raise TypeError("left candidate must be an object")
                left_tag = left_candidate["tag"]
                left_count = left_candidate["count"]
                left_exact = left_candidate["exact"]
                if not isinstance(left_tag, str) or left_tag == "":
                    continue
                if not isinstance(left_count, int) or left_count <= 0:
                    continue
                if not isinstance(left_exact, bool):
                    continue
                for right_candidate in right_candidates[:3]:
                    if not isinstance(right_candidate, dict):
                        raise TypeError("right candidate must be an object")
                    right_tag = right_candidate["tag"]
                    right_count = right_candidate["count"]
                    right_exact = right_candidate["exact"]
                    if not isinstance(right_tag, str) or right_tag == "":
                        continue
                    if not isinstance(right_count, int) or right_count <= 0:
                        continue
                    if not isinstance(right_exact, bool):
                        continue
                    if left_tag == right_tag:
                        continue
                    dedupe_key = tuple(sorted([left_tag, right_tag], key=str.casefold))
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    combos.append(
                        {
                            "required_tags": [left_tag, right_tag],
                            "source_terms": [left_term, right_term],
                            "estimated_overlap": left_count * right_count,
                            "exact_prefix_hits": int(left_exact) + int(right_exact),
                        }
                    )
    combos.sort(
        key=lambda item: (
            -item["exact_prefix_hits"],
            item["estimated_overlap"],
            item["required_tags"][0].casefold(),
            item["required_tags"][1].casefold(),
        )
    )
    return combos[:12]


def _bootstrap_intersection_steps(
    *,
    user_message: str,
    mcp_url: str,
    request_id: int,
) -> dict:
    terms = _build_tag_discovery_terms(user_message=user_message)
    if len(terms) < 2:
        return {
            "steps": [],
            "tool_feedback_messages": [],
            "next_request_id": request_id,
            "intersection_count": 0,
        }

    steps: List[dict] = []
    feedback_messages: List[dict] = []
    discovered_terms: List[dict] = []
    note_entries_by_id: Dict[str, dict] = {}
    matched_ids = set()
    note_hit_counts: Dict[str, int] = {}
    combo_summaries: List[dict] = []
    next_request_id = request_id

    for term in terms:
        list_tags_args = {
            "prefix": term,
            "limit": 12,
            "mode": "effective",
        }
        list_tags_response = _tools_call(
            url=mcp_url,
            request_id=next_request_id,
            tool_name="list_tags",
            arguments=list_tags_args,
        )
        next_request_id += 1
        parsed_list_tags = _extract_tool_response(call_response=list_tags_response)
        output_response = _compact_for_output(value=parsed_list_tags)
        model_response = _compact_for_model(value=parsed_list_tags)
        steps.append(
            {
                "action": "tool",
                "tool_name": "list_tags",
                "arguments": list_tags_args,
                "tool_response": output_response,
                "reason": "discover candidate tags for query term",
            }
        )
        feedback_messages.append(
            {
                "tool_name": "list_tags",
                "tool_response": model_response,
                "bootstrap": True,
                "term": term,
            }
        )
        candidates = _extract_tag_candidates_from_list_tags_response(
            parsed_list_tags=parsed_list_tags,
            prefix=term,
        )
        discovered_terms.append(
            {
                "term": term,
                "candidates": candidates,
            }
        )

    planned_combos = _plan_two_tag_combinations(discovered_terms=discovered_terms)

    for combo in planned_combos:
        required_tags = combo["required_tags"]
        if not isinstance(required_tags, list):
            raise TypeError("required_tags must be an array")
        search_args = {
            "query": "",
            "required_tags": required_tags,
            "forbidden_tags": [],
            "limit": 24,
            "offset": 0,
        }
        search_response = _tools_call(
            url=mcp_url,
            request_id=next_request_id,
            tool_name="search_notes",
            arguments=search_args,
        )
        next_request_id += 1
        parsed_search = _extract_tool_response(call_response=search_response)
        search_meta = _extract_note_ids_and_entries_from_search_response(parsed_search=parsed_search)
        note_ids = search_meta["note_ids"]
        entries_by_id = search_meta["entries_by_id"]
        if not isinstance(note_ids, set):
            raise TypeError("search_meta.note_ids must be a set")
        if not isinstance(entries_by_id, dict):
            raise TypeError("search_meta.entries_by_id must be an object")
        matched_ids.update(note_ids)
        for note_id in note_ids:
            if note_id not in note_hit_counts:
                note_hit_counts[note_id] = 0
            note_hit_counts[note_id] += 1
        for note_id, entry in entries_by_id.items():
            if note_id not in note_entries_by_id:
                note_entries_by_id[note_id] = entry

        output_response = _compact_for_output(value=parsed_search)
        model_response = _compact_for_model(value=parsed_search)
        steps.append(
            {
                "action": "tool",
                "tool_name": "search_notes",
                "arguments": search_args,
                "tool_response": output_response,
                "reason": "two-tag intersection candidate search",
            }
        )
        feedback_messages.append(
            {
                "tool_name": "search_notes",
                "tool_response": model_response,
                "bootstrap": True,
                "combo": required_tags,
            }
        )
        combo_summaries.append(
            {
                "required_tags": required_tags,
                "source_terms": combo["source_terms"],
                "estimated_overlap": combo["estimated_overlap"],
                "exact_prefix_hits": combo["exact_prefix_hits"],
                "matches": len(note_ids),
            }
        )
        if len(matched_ids) >= 12:
            break

    candidate_ids = sorted(
        matched_ids,
        key=lambda note_id: (
            -note_hit_counts[note_id],
            note_id,
        ),
    )
    ranked_candidates: List[dict] = []
    for note_id in candidate_ids[:12]:
        if note_id not in note_entries_by_id:
            continue
        ranked_entry = dict(note_entries_by_id[note_id])
        ranked_entry["combo_hit_count"] = note_hit_counts[note_id]
        ranked_candidates.append(ranked_entry)

    hydrated_notes: List[dict] = []
    for entry in ranked_candidates[:6]:
        if not isinstance(entry, dict):
            raise TypeError("ranked candidate entry must be an object")
        if "note_id" not in entry:
            raise TypeError("ranked candidate missing note_id")
        note_id = entry["note_id"]
        if not isinstance(note_id, str) or note_id == "":
            continue
        get_note_args = {
            "note_id": note_id,
        }
        get_note_response = _tools_call(
            url=mcp_url,
            request_id=next_request_id,
            tool_name="get_note",
            arguments=get_note_args,
        )
        next_request_id += 1
        parsed_get_note = _extract_tool_response(call_response=get_note_response)
        output_response = _compact_for_output(value=parsed_get_note)
        model_response = _summarize_get_note_for_model(
            tool_response=parsed_get_note,
            query_terms=terms,
        )
        steps.append(
            {
                "action": "tool",
                "tool_name": "get_note",
                "arguments": get_note_args,
                "tool_response": output_response,
                "reason": "inspect full note content for shortlisted intersection candidate",
            }
        )
        feedback_messages.append(
            {
                "tool_name": "get_note",
                "tool_response": model_response,
                "bootstrap": True,
            }
        )
        hydrated_notes.append(
            {
                "note_id": note_id,
                "combo_hit_count": entry["combo_hit_count"],
            }
        )

    summary = {
        "discovered_terms": _compact_for_output(value=discovered_terms),
        "planned_combo_count": len(planned_combos),
        "executed_combos": _compact_for_output(value=combo_summaries),
        "intersection_count": len(matched_ids),
        "intersection_note_ids": candidate_ids[:20],
        "intersection_candidates_ranked": _compact_for_output(value=ranked_candidates),
        "hydrated_note_ids": _compact_for_output(value=hydrated_notes),
    }
    steps.append(
        {
            "action": "bootstrap_intersection",
            "tool_response": {
                "ok": True,
                "data": _compact_for_output(value=summary),
            },
            "reason": "adaptive two-tag strategy from discovered tags and counts",
        }
    )
    feedback_messages.append(
        {
            "tool_name": "semantic_intersection",
            "tool_response": {
                "ok": True,
                "data": _compact_for_model(value=summary),
            },
            "bootstrap": True,
        }
    )

    return {
        "steps": steps,
        "tool_feedback_messages": feedback_messages,
        "next_request_id": next_request_id,
        "intersection_count": len(matched_ids),
    }


def _extract_agent_error_text(*, decision: dict) -> str:
    candidate_keys = ["answer", "error", "detail", "message", "reason"]
    for key in candidate_keys:
        if key not in decision:
            continue
        value = decision[key]
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
    return "Agent returned action='error' without details."


def _bootstrap_search_step(
    *,
    user_message: str,
    mcp_url: str,
    request_id: int,
) -> dict:
    compact_query = _build_compact_search_query(user_message=user_message)
    search_args = {
        "query": compact_query,
        "required_tags": [],
        "forbidden_tags": [],
        "limit": 12,
        "offset": 0,
    }
    search_response = _tools_call(
        url=mcp_url,
        request_id=request_id,
        tool_name="search_notes",
        arguments=search_args,
    )
    parsed_search = _extract_tool_response(call_response=search_response)
    output_response = _compact_for_output(value=parsed_search)
    model_response = _compact_for_model(value=parsed_search)
    step = {
        "action": "tool",
        "tool_name": "search_notes",
        "arguments": search_args,
        "tool_response": output_response,
        "reason": "bootstrap retrieval: gather relevant candidates before reasoning",
    }
    if compact_query != user_message:
        step["query_rewritten_from"] = user_message
    tool_feedback = {
        "tool_name": "search_notes",
        "tool_response": model_response,
        "bootstrap": True,
    }
    return {
        "step": step,
        "tool_feedback": tool_feedback,
        "next_request_id": request_id + 1,
    }


def _ordered_note_ids_from_search_tool(*, tool_response: dict) -> List[str]:
    if not isinstance(tool_response, dict):
        raise TypeError("tool_response must be an object")
    if tool_response.get("ok") is not True:
        return []
    data = tool_response.get("data")
    if not isinstance(data, dict):
        return []
    return _extract_note_ids_from_tool_data(data=data)


def _extract_ordered_note_ids_from_tool_results(*, tool_response: dict) -> List[str]:
    if not isinstance(tool_response, dict):
        raise TypeError("tool_response must be an object")
    if tool_response.get("ok") is not True:
        return []
    data = tool_response.get("data")
    if not isinstance(data, dict):
        return []
    return _extract_note_ids_from_tool_data(data=data)


def _extract_note_ids_from_tool_data(*, data: dict) -> List[str]:
    if not isinstance(data, dict):
        raise TypeError("data must be an object")

    ordered: List[str] = []
    seen = set()

    note_ids = data.get("note_ids")
    if isinstance(note_ids, list):
        for note_id in note_ids:
            if not isinstance(note_id, str) or note_id == "":
                continue
            if note_id in seen:
                continue
            seen.add(note_id)
            ordered.append(note_id)
        return ordered

    results = data.get("results")
    if not isinstance(results, list):
        return ordered

    for entry in results:
        if not isinstance(entry, dict):
            continue
        note_id = entry.get("note_id")
        if not isinstance(note_id, str) or note_id == "":
            continue
        if note_id in seen:
            continue
        seen.add(note_id)
        ordered.append(note_id)
    return ordered


def _summarize_rewrite_tool_response(*, tool_response: dict, note_id_sample_limit: int) -> dict:
    if not isinstance(tool_response, dict):
        raise TypeError("tool_response must be an object")
    if not isinstance(note_id_sample_limit, int) or note_id_sample_limit <= 0:
        raise ValueError("note_id_sample_limit must be a positive integer")
    if tool_response.get("ok") is not True:
        return tool_response

    data = tool_response.get("data")
    if not isinstance(data, dict):
        return tool_response

    summary_data: Dict[str, object] = {}
    passthrough_keys = [
        "query",
        "required_tags",
        "forbidden_tags",
        "resolved_query",
        "pattern",
        "flags",
        "regex_engine",
        "target",
        "scope_count",
        "limit",
        "offset",
        "total_matches",
        "returned_count",
        "total_requested",
        "not_found_ids",
    ]
    for key in passthrough_keys:
        if key in data:
            summary_data[key] = data[key]

    notes = data.get("notes")
    if isinstance(notes, list):
        note_entries: List[dict] = []
        for note in notes:
            if not isinstance(note, dict):
                continue
            entry: Dict[str, object] = {}
            content_text = note.get("content_text")
            if isinstance(content_text, str) and content_text.strip() != "":
                entry["content_excerpt"] = _clip_text_for_synthesis(
                    text=content_text,
                    max_chars=220,
                )
            context_text = note.get("context_text")
            if isinstance(context_text, str) and context_text.strip() != "":
                entry["context_excerpt"] = _clip_text_for_synthesis(
                    text=context_text,
                    max_chars=320,
                )
            if len(entry) == 0:
                continue
            note_entries.append(entry)
        summary_data["notes_total"] = len(note_entries)
        summary_data["notes_sample"] = note_entries[:note_id_sample_limit]

    results = data.get("results")
    if isinstance(results, list):
        regex_match_samples: List[dict] = []
        max_samples = max(4, min(note_id_sample_limit * 2, 24))
        for entry in results:
            if not isinstance(entry, dict):
                continue
            matches = entry.get("matches")
            if not isinstance(matches, list):
                continue
            for match in matches:
                if not isinstance(match, dict):
                    continue
                snippet = match.get("snippet")
                if not isinstance(snippet, str) or snippet.strip() == "":
                    continue
                field = match.get("field")
                if not isinstance(field, str):
                    field = "unknown"
                collapsed_snippet = re.sub(r"\s+", " ", snippet).strip()
                regex_match_samples.append(
                    {
                        "field": field,
                        "snippet": _clip_text_for_synthesis(
                            text=collapsed_snippet,
                            max_chars=220,
                        ),
                    }
                )
                if len(regex_match_samples) >= max_samples:
                    break
            if len(regex_match_samples) >= max_samples:
                break
        if len(regex_match_samples) > 0:
            summary_data["regex_match_samples"] = regex_match_samples

    return {
        "ok": True,
        "data": summary_data,
    }


def _strip_note_ids_for_display(*, value: object) -> object:
    if isinstance(value, dict):
        output: Dict[str, object] = {}
        for key, child in value.items():
            if key in {
                "note_id",
                "parent_id",
                "ancestor_note_ids",
                "note_ids",
                "note_ids_sample",
            }:
                continue
            output[key] = _strip_note_ids_for_display(value=child)
        return output
    if isinstance(value, list):
        return [_strip_note_ids_for_display(value=item) for item in value]
    return value


def _normalize_tag_atom(*, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("tag atom value must be a string")
    normalized = value.strip().casefold()
    if normalized.startswith("tag:"):
        normalized = normalized[4:]
    if normalized == "":
        raise ValueError("tag atom value must be non-empty")
    if _TAG_ATOM_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            "tag atom value must match ^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
        )
    return normalized


def _normalize_expression_plan(
    *,
    payload: object,
    max_expressions: int,
    min_expressions: int = 0,
    source_message: str | None = None,
) -> dict:
    if min_expressions < 0:
        raise ValueError("min_expressions must be >= 0")
    if min_expressions > max_expressions:
        raise ValueError("min_expressions must be <= max_expressions")
    if not isinstance(payload, dict):
        raise ValueError("Expression planner output must be a JSON object")

    reasoning_value = payload.get("reasoning")
    if not isinstance(reasoning_value, str):
        reasoning = "Model omitted reasoning."
    else:
        reasoning = reasoning_value.strip()
        if reasoning == "":
            reasoning = "Model omitted reasoning."

    raw_expressions = payload.get("expressions")
    if not isinstance(raw_expressions, list):
        raise ValueError("Expression planner must include expressions array")

    expressions: List[dict] = []
    seen = set()
    enforce_ascii_only = False
    if isinstance(source_message, str):
        enforce_ascii_only = source_message.isascii()
    for raw_expression in raw_expressions:
        if not isinstance(raw_expression, dict):
            continue
        raw_type = raw_expression.get("type")
        if not isinstance(raw_type, str):
            continue
        normalized_type = raw_type.casefold().strip()
        if normalized_type not in {"phrase", "regex", "near", "tag"}:
            continue

        normalized_expression: dict
        dedupe_key: tuple
        if normalized_type == "phrase":
            value = raw_expression.get("value")
            if not isinstance(value, str):
                continue
            normalized_value = re.sub(r"\s+", " ", value).strip()
            if normalized_value == "":
                continue
            if enforce_ascii_only and not normalized_value.isascii():
                continue
            normalized_expression = {
                "type": "phrase",
                "value": normalized_value,
            }
            dedupe_key = ("phrase", normalized_value.casefold())
        elif normalized_type == "regex":
            pattern = raw_expression.get("pattern")
            if not isinstance(pattern, str) or pattern.strip() == "":
                continue
            if enforce_ascii_only and not pattern.isascii():
                continue
            flags_value = raw_expression.get("flags", "")
            if not isinstance(flags_value, str):
                continue
            normalized_flags = ""
            seen_flags = set()
            for flag_char in flags_value:
                if flag_char not in {"i", "m", "s"}:
                    continue
                if flag_char in seen_flags:
                    continue
                seen_flags.add(flag_char)
                normalized_flags += flag_char
            normalized_flags = "".join(flag for flag in "ims" if flag in normalized_flags)
            normalized_expression = {
                "type": "regex",
                "pattern": pattern,
                "flags": normalized_flags,
            }
            dedupe_key = ("regex", pattern, normalized_flags)
        elif normalized_type == "near":
            left_value = raw_expression.get("left")
            right_value = raw_expression.get("right")
            window_chars = raw_expression.get("window_chars")
            if not isinstance(left_value, str) or not isinstance(right_value, str):
                continue
            left_normalized = re.sub(r"\s+", " ", left_value).strip()
            right_normalized = re.sub(r"\s+", " ", right_value).strip()
            if left_normalized == "" or right_normalized == "":
                continue
            if left_normalized.casefold() == right_normalized.casefold():
                continue
            if not isinstance(window_chars, int):
                continue
            if window_chars < 20 or window_chars > 2000:
                continue
            if enforce_ascii_only and (
                (not left_normalized.isascii()) or (not right_normalized.isascii())
            ):
                continue
            normalized_expression = {
                "type": "near",
                "left": left_normalized,
                "right": right_normalized,
                "window_chars": window_chars,
            }
            ordered_pair = sorted(
                [left_normalized.casefold(), right_normalized.casefold()]
            )
            dedupe_key = ("near", ordered_pair[0], ordered_pair[1], window_chars)
        else:
            tag_value = raw_expression.get("value")
            if enforce_ascii_only and isinstance(tag_value, str) and not tag_value.isascii():
                continue
            try:
                normalized_tag = _normalize_tag_atom(value=tag_value)
            except ValueError:
                continue
            normalized_expression = {
                "type": "tag",
                "value": normalized_tag,
            }
            dedupe_key = ("tag", normalized_tag)

        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        expressions.append(normalized_expression)
        if len(expressions) >= max_expressions:
            break

    if len(expressions) < min_expressions:
        raise ValueError(
            "Expression planner returned "
            + str(len(expressions))
            + " usable expressions; need at least "
            + str(min_expressions)
        )
    _validate_expression_plan_query_alignment(
        expressions=expressions,
        source_message=source_message,
    )
    return {
        "reasoning": reasoning,
        "expressions": expressions,
    }


def _regex_has_numeric_shape(*, pattern: str) -> bool:
    if not isinstance(pattern, str):
        raise TypeError("pattern must be a string")
    if re.search(r"\\d", pattern) is not None:
        return True
    if re.search(r"\[0-9\]", pattern) is not None:
        return True
    if re.search(r"\{[0-9]+(?:,[0-9]*)?\}", pattern) is not None:
        return True
    return False


def _regex_has_alpha_literals(*, pattern: str) -> bool:
    if not isinstance(pattern, str):
        raise TypeError("pattern must be a string")
    without_escaped = re.sub(r"\\[A-Za-z]", "", pattern)
    without_classes = re.sub(r"\[[^\]]*\]", "", without_escaped)
    return re.search(r"[A-Za-z]", without_classes) is not None


def _regex_has_bridge_wildcard(*, pattern: str) -> bool:
    if not isinstance(pattern, str):
        raise TypeError("pattern must be a string")
    if ".*" in pattern:
        return True
    if re.search(r"\.\{[0-9]+(?:,[0-9]*)?\}", pattern) is not None:
        return True
    return False


def _phrase_token_count(*, value: str) -> int:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return len(re.findall(r"[A-Za-z0-9]+", value))


def _expression_execution_tier(*, expression: dict) -> int:
    if not isinstance(expression, dict):
        raise TypeError("expression must be an object")
    expression_type = expression.get("type")
    if not isinstance(expression_type, str):
        return 2
    if expression_type == "near":
        return 1
    if expression_type == "phrase":
        value = expression.get("value")
        if not isinstance(value, str):
            return 2
        token_count = _phrase_token_count(value=value)
        if token_count >= 2:
            return 0
        return 2
    if expression_type == "regex":
        pattern = expression.get("pattern")
        if not isinstance(pattern, str):
            return 2
        has_numeric_shape = _regex_has_numeric_shape(pattern=pattern)
        has_alpha_literals = _regex_has_alpha_literals(pattern=pattern)
        has_bridge_wildcard = _regex_has_bridge_wildcard(pattern=pattern)
        if has_numeric_shape and not has_alpha_literals:
            return 0
        if has_bridge_wildcard and has_alpha_literals:
            return 2
        return 1
    if expression_type == "tag":
        return 1
    return 2

def _compile_near_regex_pattern(*, left: str, right: str, window_chars: int) -> str:
    if not isinstance(left, str):
        raise TypeError("left must be a string")
    if not isinstance(right, str):
        raise TypeError("right must be a string")
    if not isinstance(window_chars, int):
        raise TypeError("window_chars must be an integer")
    if window_chars < 1:
        raise ValueError("window_chars must be > 0")

    def _phrase_to_regex_tokens(phrase: str) -> str:
        escaped = re.escape(phrase)
        return re.sub(r"\\\s+", r"\\s+", escaped)

    left_pattern = _phrase_to_regex_tokens(left)
    right_pattern = _phrase_to_regex_tokens(right)
    window = str(window_chars)
    return (
        "(?:"
        + left_pattern
        + ".{0,"
        + window
        + "}"
        + right_pattern
        + "|"
        + right_pattern
        + ".{0,"
        + window
        + "}"
        + left_pattern
        + ")"
    )


def _compile_rewrite_expression_call(
    *,
    expression: dict,
    per_expression_limit: int,
    normalized_regex_engine: str,
    universe_note_ids: List[str] | None,
) -> dict:
    if not isinstance(expression, dict):
        raise TypeError("expression must be an object")
    expression_type = expression.get("type")
    if not isinstance(expression_type, str):
        raise TypeError("expression.type must be a string")

    if expression_type == "phrase":
        phrase_value = expression.get("value")
        if not isinstance(phrase_value, str):
            raise TypeError("phrase expression value must be a string")
        escaped = phrase_value.replace("\\", "\\\\").replace('"', '\\"')
        query = f"\"{escaped}\""
        tool_name = "search_notes"
        tool_args = {
            "query": query,
            "required_tags": [],
            "forbidden_tags": [],
            "limit": per_expression_limit,
            "offset": 0,
        }
        display_args = {
            "query": query,
            "required_tags": [],
            "forbidden_tags": [],
            "limit": per_expression_limit,
            "offset": 0,
        }
        label = f'phrase:"{phrase_value}"'
        return {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "display_args": display_args,
            "label": label,
        }

    if expression_type == "tag":
        tag_value = expression.get("value")
        if not isinstance(tag_value, str):
            raise TypeError("tag expression value must be a string")
        tool_name = "search_notes"
        tool_args = {
            "query": tag_value,
            "required_tags": [],
            "forbidden_tags": [],
            "limit": per_expression_limit,
            "offset": 0,
        }
        display_args = {
            "query": tag_value,
            "required_tags": [],
            "forbidden_tags": [],
            "limit": per_expression_limit,
            "offset": 0,
        }
        label = f"tag:{tag_value}"
        return {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "display_args": display_args,
            "label": label,
        }

    if expression_type == "regex":
        pattern = expression.get("pattern")
        flags = expression.get("flags")
        if not isinstance(pattern, str):
            raise TypeError("regex expression pattern must be a string")
        if not isinstance(flags, str):
            raise TypeError("regex expression flags must be a string")
        tool_name = "search_notes_regex"
        tool_args = {
            "pattern": pattern,
            "flags": flags,
            "regex_engine": normalized_regex_engine,
            "target": "both",
            "scope_note_ids": universe_note_ids if universe_note_ids is not None else [],
            "limit": per_expression_limit,
            "offset": 0,
        }
        display_args = {
            "pattern": pattern,
            "flags": flags,
            "regex_engine": normalized_regex_engine,
            "target": "both",
            "scope_note_ids_count": len(universe_note_ids) if universe_note_ids is not None else 0,
            "limit": per_expression_limit,
            "offset": 0,
        }
        label = f"regex:/{pattern}/{flags}"
        return {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "display_args": display_args,
            "label": label,
        }

    if expression_type == "near":
        left = expression.get("left")
        right = expression.get("right")
        window_chars = expression.get("window_chars")
        if not isinstance(left, str):
            raise TypeError("near expression left must be a string")
        if not isinstance(right, str):
            raise TypeError("near expression right must be a string")
        if not isinstance(window_chars, int):
            raise TypeError("near expression window_chars must be an integer")
        pattern = _compile_near_regex_pattern(
            left=left,
            right=right,
            window_chars=window_chars,
        )
        flags = "is"
        tool_name = "search_notes_regex"
        tool_args = {
            "pattern": pattern,
            "flags": flags,
            "regex_engine": normalized_regex_engine,
            "target": "both",
            "scope_note_ids": universe_note_ids if universe_note_ids is not None else [],
            "limit": per_expression_limit,
            "offset": 0,
        }
        display_args = {
            "left": left,
            "right": right,
            "window_chars": window_chars,
            "compiled_pattern": pattern,
            "flags": flags,
            "regex_engine": normalized_regex_engine,
            "target": "both",
            "scope_note_ids_count": len(universe_note_ids) if universe_note_ids is not None else 0,
            "limit": per_expression_limit,
            "offset": 0,
        }
        label = 'near:"' + left + '"~"' + right + '"@' + str(window_chars)
        return {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "display_args": display_args,
            "label": label,
        }

    raise TypeError(f"Unsupported expression type: {expression_type}")


def _validate_expression_plan_query_alignment(
    *,
    expressions: List[dict],
    source_message: str | None,
) -> None:
    if not isinstance(expressions, list):
        raise TypeError("expressions must be a list")
    if source_message is not None and not isinstance(source_message, str):
        raise TypeError("source_message must be a string or None")


def _normalize_expression_plan_best_effort(
    *,
    payload: object,
    max_expressions: int,
    source_message: str | None = None,
) -> dict:
    try:
        return _normalize_expression_plan(
            payload=payload,
            max_expressions=max_expressions,
            source_message=source_message,
        )
    except ValueError:
        return {
            "reasoning": "",
            "expressions": [],
        }


def _compute_expression_plan_target_count(*, max_expressions: int) -> int:
    if max_expressions <= 0:
        raise ValueError("max_expressions must be > 0")
    return min(max_expressions, _EXPRESSION_PLAN_TARGET_CAP)


def _compute_expression_probe_points(*, planned_expression_count: int) -> List[int]:
    if planned_expression_count <= 0:
        raise ValueError("planned_expression_count must be > 0")
    probe_points: List[int] = []
    for point in (_EXPRESSION_PROBE_FIRST, _EXPRESSION_PROBE_SECOND, planned_expression_count):
        normalized_point = min(max(point, 1), planned_expression_count)
        if normalized_point in probe_points:
            continue
        probe_points.append(normalized_point)
    return probe_points


def _build_rewrite_expression_plan_messages(
    *,
    user_message: str,
    search_context_query: str,
    max_expressions: int,
    elapsed_ms: float = 0.0,
    iteration_index: int = 1,
    executed_query_history: List[dict] | None = None,
    prior_evidence_notes: List[dict] | None = None,
) -> List[dict]:
    if executed_query_history is None:
        executed_query_history = []
    if prior_evidence_notes is None:
        prior_evidence_notes = []
    system_prompt = "\n".join(
        [
            "You are a MetaList retrieval planner for one loop iteration.",
            "Choose the next retrieval expressions to execute.",
            "",
            "Execution model:",
            "- The loop may run multiple iterations.",
            "- Your returned expressions are executed in the same order you provide.",
            "- Keep only the best next queries for this iteration.",
            "- You may return an empty expressions list when no new query is useful.",
            "",
            "Data model:",
            "- Notes are hierarchical (parent/child trees).",
            "- Retrieval can search content_text and context_text (ancestor + current note text).",
            "- Prior results and query history are provided in the user payload.",
            "",
            "Allowed expression types only: phrase, regex, near, tag.",
            "Use tag only when the user intent is explicitly tag-like.",
            "Do not repeat any query already present in executed_query_history.",
            "Use the same language/script as the user query unless the user query itself is multilingual.",
            "",
            "Return ONLY JSON with exact shape:",
            '{"reasoning":"<1-3 sentences>","expressions":[{"type":"phrase","value":"..."},{"type":"regex","pattern":"...","flags":"ims"},{"type":"near","left":"...","right":"...","window_chars":200},{"type":"tag","value":"tag-name"}]}',
            "Maximum expressions per iteration: " + str(max_expressions) + ".",
        ]
    )
    user_payload = {
        "question": user_message,
        "iteration_index": iteration_index,
        "elapsed_ms_so_far": elapsed_ms,
        "active_search_context_query": search_context_query,
        "executed_query_history": executed_query_history,
        "prior_evidence_notes": prior_evidence_notes,
    }
    user_prompt = "Iteration context:\n" + json.dumps(
        user_payload,
        ensure_ascii=False,
        indent=2,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_rewrite_expression_plan_repair_messages(
    *,
    user_message: str,
    search_context_query: str,
    original_plan: dict,
    validation_error: str,
    max_expressions: int,
    target_expressions: int,
) -> List[dict]:
    system_prompt = "\n".join(
        [
            "You are repairing a MetaList retrieval plan that failed validation or was too weak.",
            "Keep valid high-signal expressions from the prior plan and improve coverage.",
            "",
            "Rules:",
            "- Use expression types only: phrase, regex, near, tag.",
            "- Keep expressions ordered best-first (high signal first, broader later).",
            "- Prefer simple realistic anchors over complex brittle patterns.",
            "- Regex is optional; add when it improves structured-format recall.",
            "- near is optional; add when multi-anchor proximity is useful.",
            "- Use the same language/script as the query.",
            "",
            "Output contract:",
            '- Return ONLY JSON with this exact shape: {"reasoning":"<1-3 sentences>","expressions":[{"type":"phrase","value":"..."},{"type":"regex","pattern":"...","flags":"ims"},{"type":"near","left":"...","right":"...","window_chars":200},{"type":"tag","value":"tag-name"}]}.',
            "- Produce up to "
            + str(target_expressions)
            + " expressions for this pass (maximum "
            + str(max_expressions)
            + ").",
        ]
    )
    scoped_hint = search_context_query if search_context_query.strip() != "" else ""
    user_prompt_payload = {
        "user_question": user_message,
        "active_search_context_query": scoped_hint,
        "prior_plan": original_plan,
        "validation_error": validation_error,
        "repair_instructions": "Keep valid anchors and add missing variants until constraints are met.",
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_prompt_payload, ensure_ascii=False)},
    ]


def _build_rewrite_synthesis_messages(
    *,
    user_message: str,
    search_context_query: str,
    expression_plan: dict,
    expression_stats: List[dict],
    evidence_notes: List[dict] | None = None,
    hydrated_notes: List[dict] | None = None,
) -> List[dict]:
    if evidence_notes is None:
        evidence_notes = hydrated_notes if hydrated_notes is not None else []
    system_prompt = (
        "You are answering from retrieved MetaList evidence only. "
        "MetaList schema reminder: notes are hierarchical and context may include ancestor text. "
        "All evidence provided here comes from the user's own notes in this run, so do not refuse based on lack of access. "
        "Never answer with capability disclaimers like 'I do not have access' when evidence is provided. "
        "Some retrieved notes may be lexical false positives; ignore evidence that does not directly address the question. "
        "Prioritize notes with stronger expression overlap and direct value-bearing evidence. "
        "If evidence is insufficient, say so explicitly. "
        "Do not invent facts. "
        "Return JSON: {\"answer\":\"...\"}."
    )
    payload = {
        "question": user_message,
        "active_search_context_query": search_context_query,
        "expression_plan": expression_plan,
        "expression_stats": expression_stats,
        "evidence_notes": evidence_notes,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        {
            "role": "user",
            "content": (
                "Authoritative question (repeat): "
                + user_message
                + "\nReturn only JSON with an `answer` string."
            ),
        },
    ]


def _expression_signature(*, expression: dict) -> str:
    if not isinstance(expression, dict):
        raise TypeError("expression must be an object")
    expression_type = expression.get("type")
    if not isinstance(expression_type, str):
        return "unknown"
    normalized_type = expression_type.casefold()
    if normalized_type == "phrase":
        value = expression.get("value")
        if not isinstance(value, str):
            return "phrase:"
        return "phrase:" + value.casefold().strip()
    if normalized_type == "tag":
        value = expression.get("value")
        if not isinstance(value, str):
            return "tag:"
        return "tag:" + value.casefold().strip()
    if normalized_type == "regex":
        pattern = expression.get("pattern")
        flags = expression.get("flags")
        if not isinstance(pattern, str):
            pattern = ""
        if not isinstance(flags, str):
            flags = ""
        return "regex:/" + pattern + "/" + flags
    if normalized_type == "near":
        left = expression.get("left")
        right = expression.get("right")
        window_chars = expression.get("window_chars")
        if not isinstance(left, str):
            left = ""
        if not isinstance(right, str):
            right = ""
        if not isinstance(window_chars, int):
            window_chars = 0
        return (
            "near:"
            + left.casefold().strip()
            + "~"
            + right.casefold().strip()
            + "@"
            + str(window_chars)
        )
    return normalized_type


def _scoped_result_entries_from_tool_response(
    *,
    tool_response: dict,
    universe_mode: str,
    universe_note_ids: List[str] | None,
    universe_note_id_set: set[str] | None,
) -> List[dict]:
    if not isinstance(tool_response, dict):
        raise TypeError("tool_response must be an object")
    if universe_mode not in {"global", "scoped"}:
        raise ValueError("universe_mode must be one of: global, scoped")
    if tool_response.get("ok") is not True:
        return []
    data = tool_response.get("data")
    if not isinstance(data, dict):
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []

    ordered_results: List[dict] = []
    by_note_id: Dict[str, dict] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        note_id = row.get("note_id")
        if not isinstance(note_id, str) or note_id == "":
            continue
        if note_id in by_note_id:
            continue
        by_note_id[note_id] = row
        ordered_results.append(row)

    if universe_mode == "global":
        return ordered_results

    if universe_note_ids is None or universe_note_id_set is None:
        raise RuntimeError("scoped universe requires note id set")

    scoped_results: List[dict] = []
    for note_id in universe_note_ids:
        if note_id not in universe_note_id_set:
            continue
        entry = by_note_id.get(note_id)
        if entry is None:
            continue
        scoped_results.append(entry)
    return scoped_results


def _sanitize_expression_stats_for_model(*, expression_stats: List[dict]) -> List[dict]:
    if not isinstance(expression_stats, list):
        raise TypeError("expression_stats must be a list")
    sanitized: List[dict] = []
    for row in expression_stats:
        if not isinstance(row, dict):
            continue
        clean_row: Dict[str, object] = {}
        for key in (
            "expression_index",
            "original_expression_index",
            "execution_tier",
            "expression_label",
            "execution_ms",
            "raw_match_count",
            "scoped_match_count",
            "universe_mode",
        ):
            if key in row:
                clean_row[key] = row[key]
        expression_payload = row.get("expression")
        if isinstance(expression_payload, dict):
            clean_row["expression"] = expression_payload
        regex_samples = row.get("regex_match_samples")
        if isinstance(regex_samples, list):
            clean_samples: List[dict] = []
            for sample in regex_samples[:8]:
                if not isinstance(sample, dict):
                    continue
                field = sample.get("field")
                snippet = sample.get("snippet")
                if not isinstance(field, str):
                    field = "unknown"
                if not isinstance(snippet, str) or snippet.strip() == "":
                    continue
                clean_samples.append(
                    {
                        "field": field,
                        "snippet": snippet,
                    }
                )
            if len(clean_samples) > 0:
                clean_row["regex_match_samples"] = clean_samples
        if len(clean_row) > 0:
            sanitized.append(clean_row)
    return sanitized


def _prepare_model_evidence_notes(
    *,
    note_entries: List[dict],
    user_message: str,
    max_notes: int,
) -> List[dict]:
    if not isinstance(note_entries, list):
        raise TypeError("note_entries must be a list")
    if max_notes <= 0:
        raise ValueError("max_notes must be > 0")

    query_terms = _query_terms_for_tags(user_message=user_message)[:10]
    prepared: List[dict] = []
    for note in note_entries[:max_notes]:
        if not isinstance(note, dict):
            continue
        content_text = note.get("content_text")
        if not isinstance(content_text, str):
            content_text = ""
        context_text = note.get("context_text")
        if not isinstance(context_text, str):
            context_text = ""
        preview_text = note.get("preview_text")
        if not isinstance(preview_text, str):
            preview_text = ""
        source_text = context_text if context_text != "" else content_text
        term_snippets: List[str] = []
        if source_text != "" and len(query_terms) > 0:
            term_snippets = _extract_term_snippets(
                plain_text=source_text,
                terms=query_terms,
                max_snippets=4,
            )

        regex_snippets: List[str] = []
        matches = note.get("matches")
        if isinstance(matches, list):
            for match in matches[:8]:
                if not isinstance(match, dict):
                    continue
                snippet = match.get("snippet")
                if not isinstance(snippet, str) or snippet.strip() == "":
                    continue
                collapsed = re.sub(r"\s+", " ", snippet).strip()
                regex_snippets.append(
                    _clip_text_for_synthesis(text=collapsed, max_chars=240)
                )

        tag_terms = note.get("tag_terms")
        effective_tag_terms = note.get("effective_tag_terms")
        matched_expressions = note.get("matched_expressions")
        if not isinstance(matched_expressions, list):
            matched_expressions = []
        cleaned_matched_expressions = [
            expression
            for expression in matched_expressions
            if isinstance(expression, str) and expression != ""
        ][:16]

        prepared_note: Dict[str, object] = {
            "hit_count": note.get("hit_count"),
            "matched_expressions": cleaned_matched_expressions,
            "preview_text": _clip_text_for_synthesis(
                text=preview_text,
                max_chars=260,
            ) if preview_text != "" else "",
            "content_excerpt": _clip_text_for_synthesis(
                text=content_text,
                max_chars=_SYNTHESIS_MAX_CONTENT_EXCERPT_CHARS,
            ),
            "context_excerpt": _clip_text_for_synthesis(
                text=context_text,
                max_chars=_SYNTHESIS_MAX_CONTEXT_EXCERPT_CHARS,
            ) if context_text != "" else "",
            "term_snippets": term_snippets,
            "regex_snippets": regex_snippets,
            "ancestor_context_included": context_text != "" and context_text != content_text,
        }
        if isinstance(tag_terms, list):
            prepared_note["tag_terms"] = [
                term for term in tag_terms[:20] if isinstance(term, str) and term != ""
            ]
        if isinstance(effective_tag_terms, list):
            prepared_note["effective_tag_terms"] = [
                term
                for term in effective_tag_terms[:24]
                if isinstance(term, str) and term != ""
            ]
        prepared.append(prepared_note)
    return prepared


def _order_candidate_note_ids_by_note_order(
    *,
    ranked_note_ids: List[str],
    note_evidence_by_id: Dict[str, dict],
) -> List[str]:
    if not isinstance(ranked_note_ids, list):
        raise TypeError("ranked_note_ids must be a list")
    if not isinstance(note_evidence_by_id, dict):
        raise TypeError("note_evidence_by_id must be an object")

    sortable_rows: List[tuple[int, int, str]] = []
    for fallback_index, note_id in enumerate(ranked_note_ids):
        if not isinstance(note_id, str) or note_id == "":
            continue
        entry = note_evidence_by_id.get(note_id)
        if not isinstance(entry, dict):
            continue
        note_order_index = entry.get("note_order_index")
        if not isinstance(note_order_index, int) or note_order_index < 0:
            note_order_index = 10**9
        sortable_rows.append((note_order_index, fallback_index, note_id))

    sortable_rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[2] for row in sortable_rows]


def _candidate_sample_without_ids(
    *,
    ordered_note_ids: List[str],
    note_evidence_by_id: Dict[str, dict],
    note_hit_counts: Dict[str, int],
    note_hit_expressions: Dict[str, List[str]],
    max_items: int,
) -> List[dict]:
    if max_items <= 0:
        raise ValueError("max_items must be > 0")
    sample: List[dict] = []
    for note_id in ordered_note_ids:
        if len(sample) >= max_items:
            break
        entry = note_evidence_by_id.get(note_id)
        if not isinstance(entry, dict):
            continue
        preview_text = entry.get("preview_text")
        context_text = entry.get("context_text")
        if not isinstance(preview_text, str):
            preview_text = ""
        if not isinstance(context_text, str):
            context_text = ""
        sample.append(
            {
                "hit_count": note_hit_counts.get(note_id, 0),
                "matched_expression_count": len(note_hit_expressions.get(note_id, [])),
                "preview_excerpt": _clip_text_for_synthesis(
                    text=preview_text if preview_text != "" else context_text,
                    max_chars=180,
                ),
            }
        )
    return sample


def _build_rewrite_iteration_messages(
    *,
    user_message: str,
    search_context_query: str,
    elapsed_ms: float,
    expression_history: List[dict],
    executed_query_history: List[dict],
    latest_expression: str,
    latest_expression_stats: dict,
    carried_evidence_notes: List[dict],
    latest_result_notes: List[dict],
) -> List[dict]:
    system_prompt = "\n".join(
        [
            "You are the MetaList loop controller for iterative retrieval.",
            "After each executed expression, choose exactly one next action.",
            "",
            "Allowed decisions:",
            '- "answer": evidence is sufficient. You may give a tentative answer like "either X or Y".',
            '- "continue": keep searching with remaining planned expressions.',
            '- "uncertain": evidence is insufficient now (for example: "I do not know from current evidence").',
            '- "clarify": ask exactly one concise user question that would disambiguate.',
            "",
            "Rules:",
            "- Use only the provided evidence and executed-query history.",
            "- Do NOT repeat queries already in already_executed_queries.",
            "- Prefer simple high-confidence conclusions when directly supported by evidence.",
            "- If evidence conflicts, either answer with explicit uncertainty (X or Y) or ask clarify.",
            "- Never use capability/access disclaimers; this evidence is from the user's notes.",
            "",
            "Return ONLY JSON with exact shape:",
            (
                '{"reasoning":"<1-3 sentences>",'
                '"decision":"answer|continue|uncertain|clarify",'
                '"answer":"<required for answer, optional for uncertain>",'
                '"clarifying_question":"<required for clarify>",'
                '"confidence":"high|medium|low",'
                '"continue_reason":"<required for continue; otherwise empty>"}'
            ),
        ]
    )
    payload: Dict[str, object] = {
        "question": user_message,
        "active_search_context_query": search_context_query,
        "elapsed_ms_so_far": elapsed_ms,
        "latest_expression": latest_expression,
        "latest_expression_stats": latest_expression_stats,
        "query_history": expression_history,
        "already_executed_queries": executed_query_history,
        "carried_evidence_notes": carried_evidence_notes,
        "latest_result_notes": latest_result_notes,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _build_rewrite_loop_decision_messages(
    *,
    user_message: str,
    search_context_query: str,
    elapsed_ms: float,
    iteration_index: int,
    executed_query_history: List[dict],
    iteration_query_results: List[dict],
    carried_evidence_notes: List[dict],
) -> List[dict]:
    system_prompt = "\n".join(
        [
            "You are the MetaList loop decision engine.",
            "Given this iteration's query results and prior history, decide what to do next.",
            "",
            "Allowed decisions:",
            '- "answer": provide best-supported answer now.',
            '- "continue": run another iteration with new queries.',
            '- "clarify": ask exactly one short clarifying question.',
            '- "uncertain": evidence is insufficient; return best uncertainty statement.',
            "",
            "Rules:",
            "- Base decisions only on provided evidence.",
            "- Do not use capability/access disclaimers.",
            "- If you choose continue, explain what is still missing.",
            "",
            "Return ONLY JSON with exact shape:",
            (
                '{"reasoning":"<1-3 sentences>",'
                '"decision":"answer|continue|uncertain|clarify",'
                '"answer":"<required for answer, optional for uncertain>",'
                '"clarifying_question":"<required for clarify>",'
                '"confidence":"high|medium|low",'
                '"continue_reason":"<required for continue; otherwise empty>"}'
            ),
        ]
    )
    payload: Dict[str, object] = {
        "question": user_message,
        "active_search_context_query": search_context_query,
        "iteration_index": iteration_index,
        "elapsed_ms_so_far": elapsed_ms,
        "executed_query_history": executed_query_history,
        "iteration_query_results": iteration_query_results,
        "carried_evidence_notes": carried_evidence_notes,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _normalize_rewrite_iteration_decision(*, payload: object) -> dict:
    if not isinstance(payload, dict):
        payload = {}

    decision = payload.get("decision")
    if not isinstance(decision, str) or decision.strip() == "":
        fallback_action = payload.get("action")
        if isinstance(fallback_action, str):
            mapped = fallback_action.casefold().strip()
            if mapped in {"final", "answer"}:
                decision = "answer"
            elif mapped in {"continue", "tool"}:
                decision = "continue"
            elif mapped in {"clarify"}:
                decision = "clarify"
            elif mapped in {"uncertain", "unknown", "dont_know"}:
                decision = "uncertain"
    if not isinstance(decision, str) or decision.strip() == "":
        fallback_answer = payload.get("answer")
        fallback_question = payload.get("clarifying_question")
        fallback_continue_reason = payload.get("continue_reason")
        if isinstance(fallback_answer, str) and fallback_answer.strip() != "":
            decision = "answer"
        elif isinstance(fallback_question, str) and fallback_question.strip() != "":
            decision = "clarify"
        elif isinstance(fallback_continue_reason, str) and fallback_continue_reason.strip() != "":
            decision = "continue"
        else:
            decision = "uncertain"
    normalized_decision = str(decision).casefold().strip()

    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, str):
        reasoning = ""
    normalized_reasoning = reasoning.strip()

    confidence = payload.get("confidence")
    if not isinstance(confidence, str):
        confidence = "medium"
    normalized_confidence = confidence.casefold().strip()
    if normalized_confidence not in {"high", "medium", "low"}:
        normalized_confidence = "medium"

    answer = payload.get("answer")
    if not isinstance(answer, str):
        answer = ""
    normalized_answer = answer.strip()

    clarifying_question = payload.get("clarifying_question")
    if not isinstance(clarifying_question, str):
        clarifying_question = ""
    normalized_clarifying_question = clarifying_question.strip()

    continue_reason = payload.get("continue_reason")
    if not isinstance(continue_reason, str):
        continue_reason = ""
    normalized_continue_reason = continue_reason.strip()

    if normalized_decision not in {"answer", "continue", "uncertain", "clarify"}:
        if normalized_answer != "":
            normalized_decision = "answer"
        elif normalized_clarifying_question != "":
            normalized_decision = "clarify"
        elif normalized_continue_reason != "":
            normalized_decision = "continue"
        else:
            normalized_decision = "uncertain"

    if normalized_reasoning == "":
        if normalized_continue_reason != "":
            normalized_reasoning = normalized_continue_reason
        elif normalized_answer != "":
            normalized_reasoning = normalized_answer
        elif normalized_clarifying_question != "":
            normalized_reasoning = normalized_clarifying_question
        else:
            normalized_reasoning = "Model omitted reasoning."

    if normalized_decision == "answer" and normalized_answer == "":
        if normalized_clarifying_question != "":
            normalized_decision = "clarify"
        elif normalized_continue_reason != "":
            normalized_decision = "continue"
        else:
            normalized_decision = "uncertain"
    if normalized_decision == "clarify" and normalized_clarifying_question == "":
        if normalized_answer != "":
            normalized_decision = "answer"
        elif normalized_continue_reason != "":
            normalized_decision = "continue"
        else:
            normalized_decision = "uncertain"
    if normalized_decision == "continue" and normalized_continue_reason == "":
        normalized_continue_reason = normalized_reasoning
    if normalized_decision == "uncertain" and normalized_answer == "":
        normalized_answer = "I do not know based on the current evidence."

    return {
        "reasoning": normalized_reasoning,
        "decision": normalized_decision,
        "answer": normalized_answer,
        "clarifying_question": normalized_clarifying_question,
        "confidence": normalized_confidence,
        "continue_reason": normalized_continue_reason,
    }


def _find_first_answer_like_string(*, payload: object, max_depth: int) -> str:
    if max_depth <= 0:
        raise ValueError("max_depth must be > 0")
    answer_keys = (
        "answer",
        "final_answer",
        "summary",
        "response",
        "text",
        "result_text",
    )
    queue_items: List[tuple[object, int]] = [(payload, 0)]
    while len(queue_items) > 0:
        value, depth = queue_items.pop(0)
        if depth > max_depth:
            continue
        if isinstance(value, dict):
            for key in answer_keys:
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip() != "":
                    return candidate.strip()
            for child in value.values():
                queue_items.append((child, depth + 1))
            continue
        if isinstance(value, list):
            for child in value[:100]:
                queue_items.append((child, depth + 1))
            continue
    return ""


def _extract_synthesis_answer(*, payload: object) -> str:
    extracted = _find_first_answer_like_string(payload=payload, max_depth=6)
    if extracted != "":
        return extracted
    if isinstance(payload, str) and payload.strip() != "":
        return payload.strip()
    return "No synthesized answer returned."


def _is_access_refusal_answer(*, answer: str) -> bool:
    if not isinstance(answer, str):
        raise TypeError("answer must be a string")
    normalized = answer.casefold()
    refusal_markers = (
        "i do not have access",
        "i don't have access",
        "cannot access",
        "can't access",
        "do not have your personal information",
        "don't have your personal information",
    )
    for marker in refusal_markers:
        if marker in normalized:
            return True
    return False


def _expression_rank_weight(
    *,
    expression: dict,
    scoped_match_count: int,
    universe_note_count: int,
) -> float:
    if scoped_match_count < 0:
        raise ValueError("scoped_match_count must be >= 0")
    expression_type = expression.get("type")
    if not isinstance(expression_type, str):
        expression_type = ""

    base_weight = 1.0
    if expression_type == "regex":
        base_weight = 3.0
    elif expression_type == "phrase":
        value = expression.get("value")
        if isinstance(value, str):
            token_count = len(re.findall(r"[A-Za-z0-9]+", value))
            normalized_length = len(value.strip())
            base_weight = 1.4 + min(token_count, 8) * 0.35
            if normalized_length <= 3:
                base_weight *= 0.12
            elif token_count <= 1 and normalized_length <= 5:
                base_weight *= 0.35
        else:
            base_weight = 1.4
    elif expression_type == "tag":
        base_weight = 1.7

    if universe_note_count <= 0:
        inverse_freq = 1.0
    else:
        inverse_freq = math.log((universe_note_count + 1) / (scoped_match_count + 1)) + 1.0
        inverse_freq = max(inverse_freq, 0.05)
    return round(base_weight * inverse_freq, 6)


def _rank_candidate_note_ids(
    *,
    note_hit_counts: Dict[str, int],
    note_hit_expressions: Dict[str, List[str]],
    expression_stats: List[dict],
    universe_note_count: int,
    universe_note_ids: List[str] | None,
) -> tuple[List[str], dict]:
    expression_weight_by_label: Dict[str, float] = {}
    for row in expression_stats:
        if not isinstance(row, dict):
            continue
        label = row.get("expression_label")
        if not isinstance(label, str) or label == "":
            continue
        expression = row.get("expression")
        if not isinstance(expression, dict):
            continue
        scoped_match_count = row.get("scoped_match_count")
        if not isinstance(scoped_match_count, int):
            continue
        expression_weight_by_label[label] = _expression_rank_weight(
            expression=expression,
            scoped_match_count=scoped_match_count,
            universe_note_count=universe_note_count,
        )

    universe_rank: Dict[str, int] = {}
    if isinstance(universe_note_ids, list):
        for index, note_id in enumerate(universe_note_ids):
            if isinstance(note_id, str) and note_id not in universe_rank:
                universe_rank[note_id] = index

    first_seen_rank: Dict[str, int] = {}
    ranked_rows: List[dict] = []
    for index, note_id in enumerate(note_hit_counts.keys()):
        first_seen_rank[note_id] = index
        hit_count = note_hit_counts.get(note_id, 0)
        labels = note_hit_expressions.get(note_id, [])
        if not isinstance(labels, list):
            labels = []
        score = 0.0
        seen_labels = set()
        for label in labels:
            if not isinstance(label, str) or label == "":
                continue
            if label in seen_labels:
                continue
            seen_labels.add(label)
            score += expression_weight_by_label.get(label, 0.0)
        score += float(hit_count) * 0.05
        ranked_rows.append(
            {
                "note_id": note_id,
                "score": round(score, 6),
                "hit_count": hit_count,
                "matched_expression_count": len(seen_labels),
                "matched_expressions": list(seen_labels),
                "first_seen_rank": index,
                "universe_rank": universe_rank.get(note_id, 10**9),
            }
        )

    ranked_rows.sort(
        key=lambda row: (
            -row["score"],
            -row["matched_expression_count"],
            -row["hit_count"],
            row["universe_rank"],
            row["first_seen_rank"],
            row["note_id"],
        )
    )
    ordered_note_ids = [row["note_id"] for row in ranked_rows]
    return ordered_note_ids, {
        "expression_weights": expression_weight_by_label,
        "ranked_candidates_sample": ranked_rows[:_STEP_NOTE_ID_SAMPLE_LIMIT],
    }


def _clip_text_for_synthesis(*, text: str, max_chars: int) -> str:
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    if max_chars <= 16:
        return collapsed[:max_chars]
    marker = " ... "
    available = max_chars - len(marker)
    head_chars = max(available * 3 // 4, 1)
    tail_chars = max(available - head_chars, 1)
    return collapsed[:head_chars] + marker + collapsed[-tail_chars:]


def _prepare_synthesis_notes(
    *,
    hydrated_notes: List[dict],
    user_message: str,
    max_notes: int,
) -> List[dict]:
    if max_notes <= 0:
        raise ValueError("max_notes must be > 0")
    query_terms = _query_terms_for_tags(user_message=user_message)[:10]
    small_candidate_set = len(hydrated_notes) <= _SYNTHESIS_SMALL_CANDIDATE_THRESHOLD
    content_max_chars = _SYNTHESIS_MAX_CONTENT_EXCERPT_CHARS
    context_max_chars = _SYNTHESIS_MAX_CONTEXT_EXCERPT_CHARS
    if small_candidate_set:
        content_max_chars = _SYNTHESIS_SMALL_CANDIDATE_CONTENT_MAX_CHARS
        context_max_chars = _SYNTHESIS_SMALL_CANDIDATE_CONTEXT_MAX_CHARS
    prepared: List[dict] = []
    for note in hydrated_notes[:max_notes]:
        if not isinstance(note, dict):
            continue
        note_id = note.get("note_id")
        if not isinstance(note_id, str) or note_id == "":
            continue
        content_text = note.get("content_text")
        if not isinstance(content_text, str):
            content_text = ""
        context_text = note.get("context_text")
        if not isinstance(context_text, str):
            context_text = ""
        source_text = context_text if context_text != "" else content_text
        snippets: List[str] = []
        if source_text != "" and len(query_terms) > 0:
            snippets = _extract_term_snippets(
                plain_text=source_text,
                terms=query_terms,
                max_snippets=4,
            )
        prepared.append(
            {
                "note_id": note_id,
                "hit_count": note.get("hit_count"),
                "matched_expressions": note.get("matched_expressions"),
                "term_snippets": snippets,
                "content_excerpt": _clip_text_for_synthesis(
                    text=content_text,
                    max_chars=content_max_chars,
                ),
                "context_excerpt": _clip_text_for_synthesis(
                    text=context_text,
                    max_chars=context_max_chars,
                ) if context_text != "" else "",
                "ancestor_context_included": context_text != "" and context_text != content_text,
            }
        )
    return prepared


def _run_rewrite_request(
    *,
    user_message: str,
    search_context_query: str,
    mcp_url: str,
    ollama_chat_url: str,
    model: str,
    max_steps: int,
    max_expressions: int,
    hydrate_top_k: int,
    regex_engine: str,
    progress_callback: Callable[[dict], None] | None,
    status_callback: Callable[[str], None] | None = None,
) -> dict:
    if max_steps <= 0:
        raise ValueError("max_steps must be > 0")
    if max_expressions <= 0:
        raise ValueError("max_expressions must be > 0")
    if hydrate_top_k <= 0:
        raise ValueError("hydrate_top_k must be > 0")
    normalized_regex_engine = regex_engine.casefold()
    if normalized_regex_engine not in _ALLOWED_REGEX_ENGINES:
        raise ValueError(f"regex_engine must be one of: {sorted(_ALLOWED_REGEX_ENGINES)}")

    run_started_at = time.perf_counter()

    def _total_execution_ms() -> float:
        return round((time.perf_counter() - run_started_at) * 1000, 3)

    def _emit_status(*, detail: str) -> None:
        if status_callback is None:
            return
        status_callback(detail)

    resolved_model = ensure_ollama_model_available(
        ollama_chat_url=ollama_chat_url,
        model=model,
        autopull=_DEFAULT_OLLAMA_AUTOPULL,
    )

    steps: List[dict] = []

    def append_step(*, step_record: dict) -> None:
        steps.append(step_record)
        if progress_callback is not None:
            progress_callback(step_record)

    request_id = 100
    universe_mode = "scoped" if search_context_query.strip() != "" else "global"
    universe_note_ids: List[str] | None = None
    universe_note_id_set: set[str] | None = None
    universe_note_count = 0
    universe_resolution_ms = 0.0
    universe_boundary_tool = ""
    universe_boundary_arguments: dict = {}
    per_expression_limit = _MAX_EXPRESSION_SEARCH_RESULTS

    _emit_status(detail="Resolving retrieval universe...")
    if universe_mode == "scoped":
        universe_args = {
            "query": search_context_query,
            "required_tags": [],
            "forbidden_tags": [],
            "limit": _MAX_EXPRESSION_SEARCH_RESULTS,
            "offset": 0,
        }
        universe_start = time.perf_counter()
        universe_call = _tools_call(
            url=mcp_url,
            request_id=request_id,
            tool_name="search_note_ids",
            arguments=universe_args,
        )
        universe_resolution_ms = round((time.perf_counter() - universe_start) * 1000, 3)
        request_id += 1
        universe_tool_response = _extract_tool_response(call_response=universe_call)
        if universe_tool_response.get("ok") is not True:
            error = universe_tool_response.get("error", "Universe resolution failed")
            return {
                "ok": False,
                "answer": str(error),
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "total_execution_ms": _total_execution_ms(),
            }
        universe_note_ids = _ordered_note_ids_from_search_tool(tool_response=universe_tool_response)
        universe_note_id_set = set(universe_note_ids)
        universe_note_count = len(universe_note_ids)
        universe_boundary_tool = "search_note_ids"
        universe_boundary_arguments = universe_args
    else:
        count_start = time.perf_counter()
        count_call = _tools_call(
            url=mcp_url,
            request_id=request_id,
            tool_name="count_notes",
            arguments={},
        )
        universe_resolution_ms = round((time.perf_counter() - count_start) * 1000, 3)
        request_id += 1
        count_tool_response = _extract_tool_response(call_response=count_call)
        if count_tool_response.get("ok") is not True:
            error = count_tool_response.get("error", "Universe resolution failed")
            return {
                "ok": False,
                "answer": str(error),
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "total_execution_ms": _total_execution_ms(),
            }
        count_data = count_tool_response.get("data")
        if not isinstance(count_data, dict):
            raise TypeError("count_notes data must be an object")
        total_notes = count_data.get("total_notes")
        if not isinstance(total_notes, int) or total_notes < 0:
            raise TypeError("count_notes.total_notes must be a non-negative integer")
        universe_note_count = total_notes
        universe_boundary_tool = "count_notes"
        universe_boundary_arguments = {}

    run_config = {
        "max_steps": max_steps,
        "max_expressions": max_expressions,
        "hydrate_top_k": hydrate_top_k,
        "regex_engine": normalized_regex_engine,
        "active_search_context_query": search_context_query,
        "universe_mode": universe_mode,
        "universe_note_count": universe_note_count,
        "universe_resolution_ms": universe_resolution_ms,
        "universe_boundary_tool": universe_boundary_tool,
        "universe_boundary_arguments": universe_boundary_arguments,
        "per_expression_limit": per_expression_limit,
        "expression_target_count": _compute_expression_plan_target_count(max_expressions=max_expressions),
        "expression_probe_points": _compute_expression_probe_points(
            planned_expression_count=_compute_expression_plan_target_count(max_expressions=max_expressions)
        ),
    }

    note_hit_counts: Dict[str, int] = {}
    note_hit_expressions: Dict[str, List[str]] = {}
    note_evidence_by_id: Dict[str, dict] = {}
    expression_stats: List[dict] = []
    executed_query_history: List[dict] = []
    executed_query_signatures = set()

    def merge_scoped_entries(*, entries: List[dict], expression_label: str) -> List[str]:
        latest_note_ids: List[str] = []
        for entry in entries:
            note_id = entry.get("note_id")
            if not isinstance(note_id, str) or note_id == "":
                continue
            latest_note_ids.append(note_id)

            note_hit_counts[note_id] = note_hit_counts.get(note_id, 0) + 1
            matched_expression_list = note_hit_expressions.get(note_id)
            if matched_expression_list is None:
                matched_expression_list = []
                note_hit_expressions[note_id] = matched_expression_list
            if expression_label not in matched_expression_list:
                matched_expression_list.append(expression_label)

            existing_evidence = note_evidence_by_id.get(note_id)
            if existing_evidence is None:
                note_order_index = entry.get("note_order_index")
                if not isinstance(note_order_index, int) or note_order_index < 0:
                    note_order_index = 10**9
                existing_evidence = {
                    "preview_text": entry.get("preview_text", ""),
                    "content_text": entry.get("content_text", ""),
                    "context_text": entry.get("context_text", ""),
                    "tag_terms": entry.get("tag_terms", []),
                    "effective_tag_terms": entry.get("effective_tag_terms", []),
                    "matches": [],
                    "matched_expressions": [],
                    "hit_count": 0,
                    "note_order_index": note_order_index,
                }
                note_evidence_by_id[note_id] = existing_evidence
            else:
                existing_order_index = existing_evidence.get("note_order_index")
                candidate_order_index = entry.get("note_order_index")
                if not isinstance(existing_order_index, int):
                    existing_order_index = 10**9
                if not isinstance(candidate_order_index, int):
                    candidate_order_index = 10**9
                existing_evidence["note_order_index"] = min(
                    existing_order_index,
                    candidate_order_index,
                )

            if (
                isinstance(existing_evidence.get("context_text"), str)
                and isinstance(entry.get("context_text"), str)
                and len(entry["context_text"]) > len(existing_evidence["context_text"])
            ):
                existing_evidence["context_text"] = entry["context_text"]
            if (
                isinstance(existing_evidence.get("content_text"), str)
                and isinstance(entry.get("content_text"), str)
                and len(entry["content_text"]) > len(existing_evidence["content_text"])
            ):
                existing_evidence["content_text"] = entry["content_text"]
            if (
                isinstance(existing_evidence.get("preview_text"), str)
                and isinstance(entry.get("preview_text"), str)
                and len(entry["preview_text"]) > len(existing_evidence["preview_text"])
            ):
                existing_evidence["preview_text"] = entry["preview_text"]
            if isinstance(entry.get("tag_terms"), list):
                existing_evidence["tag_terms"] = entry["tag_terms"]
            if isinstance(entry.get("effective_tag_terms"), list):
                existing_evidence["effective_tag_terms"] = entry["effective_tag_terms"]
            existing_matches = existing_evidence.get("matches")
            if not isinstance(existing_matches, list):
                existing_matches = []
                existing_evidence["matches"] = existing_matches
            entry_matches = entry.get("matches")
            if isinstance(entry_matches, list):
                for match in entry_matches:
                    if not isinstance(match, dict):
                        continue
                    snippet = match.get("snippet")
                    field = match.get("field")
                    if not isinstance(snippet, str) or snippet.strip() == "":
                        continue
                    if not isinstance(field, str):
                        field = "unknown"
                    collapsed_snippet = re.sub(r"\s+", " ", snippet).strip()
                    sample = {
                        "field": field,
                        "snippet": _clip_text_for_synthesis(
                            text=collapsed_snippet,
                            max_chars=220,
                        ),
                    }
                    if sample not in existing_matches:
                        existing_matches.append(sample)
            existing_matched_expressions = existing_evidence.get("matched_expressions")
            if not isinstance(existing_matched_expressions, list):
                existing_matched_expressions = []
                existing_evidence["matched_expressions"] = existing_matched_expressions
            if expression_label not in existing_matched_expressions:
                existing_matched_expressions.append(expression_label)
            existing_evidence["hit_count"] = note_hit_counts.get(note_id, 0)
        return latest_note_ids

    for iteration_index in range(1, max_steps + 1):
        _emit_status(detail=f"Iteration {iteration_index}: planning queries...")
        ranking_universe_ids: List[str] | None
        if universe_mode == "scoped":
            ranking_universe_ids = universe_note_ids if universe_note_ids is not None else []
        else:
            ranking_universe_ids = None
        ordered_candidate_note_ids, _ = _rank_candidate_note_ids(
            note_hit_counts=note_hit_counts,
            note_hit_expressions=note_hit_expressions,
            expression_stats=expression_stats,
            universe_note_count=universe_note_count,
            universe_note_ids=ranking_universe_ids,
        )
        ordered_candidate_note_ids = _order_candidate_note_ids_by_note_order(
            ranked_note_ids=ordered_candidate_note_ids,
            note_evidence_by_id=note_evidence_by_id,
        )
        carried_entries: List[dict] = []
        for note_id in ordered_candidate_note_ids:
            evidence_entry = note_evidence_by_id.get(note_id)
            if evidence_entry is None:
                continue
            carried_entries.append(evidence_entry)
        carried_evidence_notes = _prepare_model_evidence_notes(
            note_entries=carried_entries,
            user_message=user_message,
            max_notes=min(_ITERATION_EVIDENCE_MAX_NOTES, hydrate_top_k),
        )

        plan_messages = _build_rewrite_expression_plan_messages(
            user_message=user_message,
            search_context_query=search_context_query,
            max_expressions=max_expressions,
            elapsed_ms=_total_execution_ms(),
            iteration_index=iteration_index,
            executed_query_history=executed_query_history[-32:],
            prior_evidence_notes=carried_evidence_notes,
        )
        append_step(
            step_record={
                "step": len(steps) + 1,
                "action": "loop_iteration",
                "reason": "planner prompt prepared; waiting for planner model output",
                "stats": {
                    "iteration_index": iteration_index,
                    "phase": "planning_prompt",
                    "planning_ms": 0.0,
                    "decision_ms": 0.0,
                    "elapsed_ms_so_far": _total_execution_ms(),
                    "planned_expression_count": 0,
                    "executed_query_count": 0,
                    "skipped_duplicate_query_count": 0,
                    "iteration_result_count": 0,
                    "decision": "pending",
                },
                "model_payload": {
                    "planner_prompt_messages": plan_messages,
                },
                "tool_response": {
                    "ok": True,
                    "data": {
                        "iteration_index": iteration_index,
                        "queries_executed": [],
                        "duplicate_queries_skipped": [],
                        "latest_result_notes": [],
                        "carried_evidence_notes": carried_evidence_notes,
                    },
                },
            }
        )
        _emit_status(detail=f"Iteration {iteration_index}: waiting for planner model...")
        plan_start = time.perf_counter()
        planned_payload, planner_raw_output = _ollama_chat_json_with_raw(
            ollama_chat_url=ollama_chat_url,
            model=resolved_model,
            messages=plan_messages,
        )
        planning_ms = round((time.perf_counter() - plan_start) * 1000, 3)
        plan_preview = _normalize_expression_plan_best_effort(
            payload=planned_payload,
            max_expressions=max_expressions,
            source_message=user_message,
        )
        planner_validation_error = ""
        try:
            expression_plan = _normalize_expression_plan(
                payload=planned_payload,
                max_expressions=max_expressions,
                source_message=user_message,
            )
        except ValueError as error:
            planner_validation_error = str(error)
            expression_plan = {
                "reasoning": "Planner output was partially invalid; continuing with usable subset for this iteration.",
                "expressions": plan_preview.get("expressions", []),
            }

        expression_items: List[dict] = []
        for expression_index, expression in enumerate(expression_plan["expressions"], start=1):
            if expression_index > max_expressions:
                break
            if not isinstance(expression, dict):
                raise TypeError("expression entry must be an object")
            expression_items.append(
                {
                    "original_index": expression_index,
                    "expression": expression,
                    "tier": _expression_execution_tier(expression=expression),
                }
            )
        _emit_status(
            detail=(
                f"Iteration {iteration_index}: planner returned "
                + str(len(expression_items))
                + " candidate queries."
            )
        )

        iteration_query_runs: List[dict] = []
        skipped_duplicate_queries: List[dict] = []
        iteration_latest_note_ids: List[str] = []
        iteration_seen_note_ids = set()

        for item in expression_items:
            expression = item["expression"]
            compiled = _compile_rewrite_expression_call(
                expression=expression,
                per_expression_limit=per_expression_limit,
                normalized_regex_engine=normalized_regex_engine,
                universe_note_ids=universe_note_ids,
            )
            tool_name = compiled["tool_name"]
            tool_args = compiled["tool_args"]
            display_args = compiled["display_args"]
            label = compiled["label"]
            query_signature = _rewrite_tool_call_semantic_signature(
                tool_name=tool_name,
                arguments=tool_args,
            )
            if query_signature in executed_query_signatures:
                skipped_duplicate_queries.append(
                    {
                        "expression": expression,
                        "expression_label": label,
                        "tool_name": tool_name,
                        "arguments": display_args,
                        "query_signature": query_signature,
                    }
                )
                continue
            executed_query_signatures.add(query_signature)

            _emit_status(
                detail=(
                    f"Iteration {iteration_index}: executing "
                    + label
                    + "..."
                )
            )
            expression_start = time.perf_counter()
            tool_call = _tools_call(
                url=mcp_url,
                request_id=request_id,
                tool_name=tool_name,
                arguments=tool_args,
            )
            request_id += 1
            execution_ms = round((time.perf_counter() - expression_start) * 1000, 3)
            tool_response = _extract_tool_response(call_response=tool_call)
            if tool_response.get("ok") is not True:
                append_step(
                    step_record={
                        "step": len(steps) + 1,
                        "action": "loop_iteration",
                        "reason": "plan queries, execute full retrieval results, and decide next action",
                        "stats": {
                            "iteration_index": iteration_index,
                            "planning_ms": planning_ms,
                            "decision_ms": 0.0,
                            "elapsed_ms_so_far": _total_execution_ms(),
                            "planned_expression_count": len(expression_plan["expressions"]),
                            "executed_query_count": len(iteration_query_runs),
                            "skipped_duplicate_query_count": len(skipped_duplicate_queries),
                            "iteration_result_count": len(iteration_latest_note_ids),
                            "decision": "error",
                        },
                        "model_payload": {
                            "planner_prompt_messages": plan_messages,
                            "planner_raw_model_output": planner_raw_output,
                            "planner_reasoning": expression_plan.get("reasoning", ""),
                            "planned_expressions": expression_plan.get("expressions", []),
                        },
                        "tool_response": {
                            "ok": False,
                            "error": str(tool_response.get("error", f"{tool_name} failed")),
                            "data": {
                                "iteration_index": iteration_index,
                                "failed_query": {
                                    "expression": expression,
                                    "expression_label": label,
                                    "tool_name": tool_name,
                                    "arguments": display_args,
                                    "execution_ms": execution_ms,
                                },
                                "queries_executed": iteration_query_runs,
                                "duplicate_queries_skipped": skipped_duplicate_queries,
                                "latest_result_notes": [],
                                "carried_evidence_notes": carried_evidence_notes,
                            },
                        },
                    }
                )
                return {
                    "ok": False,
                    "answer": str(tool_response.get("error", f"{tool_name} failed")),
                    "model": resolved_model,
                    "steps": steps,
                    "mode": "rewrite",
                    "run_config": run_config,
                    "expression_stats": expression_stats,
                    "total_execution_ms": _total_execution_ms(),
                }

            scoped_entries = _scoped_result_entries_from_tool_response(
                tool_response=tool_response,
                universe_mode=universe_mode,
                universe_note_ids=universe_note_ids,
                universe_note_id_set=universe_note_id_set,
            )
            latest_note_ids = merge_scoped_entries(
                entries=scoped_entries,
                expression_label=label,
            )
            for note_id in latest_note_ids:
                if note_id in iteration_seen_note_ids:
                    continue
                iteration_seen_note_ids.add(note_id)
                iteration_latest_note_ids.append(note_id)

            raw_match_count = len(
                _extract_ordered_note_ids_from_tool_results(tool_response=tool_response)
            )
            stat_row = {
                "expression_index": len(expression_stats) + 1,
                "execution_tier": item["tier"],
                "expression": expression,
                "expression_label": label,
                "tool_name": tool_name,
                "execution_ms": execution_ms,
                "raw_match_count": raw_match_count,
                "scoped_match_count": len(latest_note_ids),
                "universe_mode": universe_mode,
                "query_signature": query_signature,
            }
            expression_stats.append(stat_row)
            executed_query_history.append(
                {
                    "expression_index": stat_row["expression_index"],
                    "expression_label": label,
                    "tool_name": tool_name,
                    "arguments": display_args,
                    "query_signature": query_signature,
                    "execution_ms": execution_ms,
                    "scoped_match_count": len(latest_note_ids),
                }
            )

            iteration_query_runs.append(
                {
                    "expression": expression,
                    "expression_label": label,
                    "tool_name": tool_name,
                    "arguments": display_args,
                    "execution_ms": execution_ms,
                    "scoped_match_count": len(latest_note_ids),
                    "tool_response": _strip_note_ids_for_display(value=tool_response),
                }
            )

        _emit_status(
            detail=(
                f"Iteration {iteration_index}: executed "
                + str(len(iteration_query_runs))
                + " queries; deciding next action..."
            )
        )

        latest_entries: List[dict] = []
        for note_id in iteration_latest_note_ids:
            evidence_entry = note_evidence_by_id.get(note_id)
            if evidence_entry is None:
                continue
            latest_entries.append(evidence_entry)
        latest_result_notes = _prepare_model_evidence_notes(
            note_entries=latest_entries,
            user_message=user_message,
            max_notes=min(12, hydrate_top_k),
        )

        decision_query_results_for_prompt = [
            {
                "expression_label": row["expression_label"],
                "tool_name": row["tool_name"],
                "arguments": row["arguments"],
                "execution_ms": row["execution_ms"],
                "scoped_match_count": row["scoped_match_count"],
                "tool_response": row["tool_response"],
            }
            for row in iteration_query_runs
        ]

        decision_messages = _build_rewrite_loop_decision_messages(
            user_message=user_message,
            search_context_query=search_context_query,
            elapsed_ms=_total_execution_ms(),
            iteration_index=iteration_index,
            executed_query_history=executed_query_history[-32:],
            iteration_query_results=decision_query_results_for_prompt,
            carried_evidence_notes=carried_evidence_notes,
        )
        append_step(
            step_record={
                "step": len(steps) + 1,
                "action": "loop_iteration",
                "reason": "planner output accepted; queries executed; waiting for decision model",
                "stats": {
                    "iteration_index": iteration_index,
                    "phase": "decision_prompt",
                    "planning_ms": planning_ms,
                    "decision_ms": 0.0,
                    "elapsed_ms_so_far": _total_execution_ms(),
                    "planned_expression_count": len(expression_plan["expressions"]),
                    "executed_query_count": len(iteration_query_runs),
                    "skipped_duplicate_query_count": len(skipped_duplicate_queries),
                    "iteration_result_count": len(iteration_latest_note_ids),
                    "decision": "pending",
                },
                "model_payload": {
                    "planner_prompt_messages": plan_messages,
                    "planner_raw_model_output": planner_raw_output,
                    "planner_reasoning": expression_plan.get("reasoning", ""),
                    "planned_expressions": expression_plan.get("expressions", []),
                    "planner_validation_error": planner_validation_error,
                    "decision_prompt_messages": decision_messages,
                },
                "tool_response": {
                    "ok": True,
                    "data": {
                        "iteration_index": iteration_index,
                        "queries_executed": iteration_query_runs,
                        "duplicate_queries_skipped": skipped_duplicate_queries,
                        "latest_result_notes": latest_result_notes,
                        "carried_evidence_notes": carried_evidence_notes,
                    },
                },
            }
        )
        decision_start = time.perf_counter()
        _emit_status(detail=f"Iteration {iteration_index}: waiting for decision model...")
        decision_payload, decision_raw = _ollama_chat_json_with_raw(
            ollama_chat_url=ollama_chat_url,
            model=resolved_model,
            messages=decision_messages,
        )
        decision_ms = round((time.perf_counter() - decision_start) * 1000, 3)
        loop_decision: dict
        iteration_step_record = {
            "step": len(steps) + 1,
            "action": "iteration_decision_final",
            "reason": "decision model selected next action",
            "stats": {
                "iteration_index": iteration_index,
                "planning_ms": planning_ms,
                "decision_ms": decision_ms,
                "elapsed_ms_so_far": _total_execution_ms(),
                "decision": "pending",
            },
            "model_payload": {
                "decision_raw_model_output": decision_raw,
            },
            "tool_response": {
                "ok": True,
                "data": {
                    "iteration_index": iteration_index,
                },
            },
        }
        try:
            loop_decision = _normalize_rewrite_iteration_decision(payload=decision_payload)
        except ValueError as error:
            iteration_step_record["stats"]["decision"] = "error"
            iteration_step_record["tool_response"] = {
                "ok": False,
                "error": f"Iteration reasoning failed: {error}",
                "data": iteration_step_record["tool_response"]["data"],
            }
            append_step(step_record=iteration_step_record)
            return {
                "ok": False,
                "answer": f"Iteration reasoning failed: {error}",
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "run_config": run_config,
                "expression_stats": expression_stats,
                "total_execution_ms": _total_execution_ms(),
            }

        iteration_step_record["stats"]["decision"] = loop_decision["decision"]
        iteration_step_record["tool_response"]["data"]["decision"] = loop_decision
        append_step(step_record=iteration_step_record)

        if loop_decision["decision"] == "answer":
            return {
                "ok": True,
                "answer": loop_decision["answer"],
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "run_config": run_config,
                "expression_stats": expression_stats,
                "total_execution_ms": _total_execution_ms(),
            }
        if loop_decision["decision"] == "clarify":
            return {
                "ok": True,
                "answer": loop_decision["clarifying_question"],
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "run_config": run_config,
                "expression_stats": expression_stats,
                "total_execution_ms": _total_execution_ms(),
            }
        if loop_decision["decision"] == "uncertain":
            return {
                "ok": True,
                "answer": loop_decision["answer"],
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "run_config": run_config,
                "expression_stats": expression_stats,
                "total_execution_ms": _total_execution_ms(),
            }
        if len(iteration_query_runs) == 0 and len(skipped_duplicate_queries) > 0:
            return {
                "ok": False,
                "answer": "Iteration made no progress: all planned queries were duplicates.",
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "run_config": run_config,
                "expression_stats": expression_stats,
                "total_execution_ms": _total_execution_ms(),
            }

    return {
        "ok": True,
        "answer": "Reached max loop iterations without a final answer.",
        "model": resolved_model,
        "steps": steps,
        "mode": "rewrite",
        "run_config": run_config,
        "expression_stats": expression_stats,
        "total_execution_ms": _total_execution_ms(),
    }


def _run_agentic_request(
    *,
    user_message: str,
    mcp_url: str,
    ollama_chat_url: str,
    model: str,
    max_steps: int,
    planner_only: bool,
    planner_seed_tag_limit: int = _DEFAULT_PLANNER_SEED_TAG_LIMIT,
    planner_tag_count_mode: str = _DEFAULT_PLANNER_TAG_COUNT_MODE,
    progress_callback: Callable[[dict], None] | None,
) -> dict:
    if max_steps <= 0:
        raise ValueError("max_steps must be > 0")
    if planner_seed_tag_limit <= 0:
        raise ValueError("planner_seed_tag_limit must be > 0")
    if planner_tag_count_mode not in _ALLOWED_PLANNER_TAG_COUNT_MODES:
        raise ValueError(
            f"planner_tag_count_mode must be one of: {sorted(_ALLOWED_PLANNER_TAG_COUNT_MODES)}"
        )

    resolved_model = ensure_ollama_model_available(
        ollama_chat_url=ollama_chat_url,
        model=model,
        autopull=_DEFAULT_OLLAMA_AUTOPULL,
    )

    steps: List[dict] = []

    def append_step(*, step_record: dict) -> None:
        steps.append(step_record)
        if progress_callback is not None:
            progress_callback(step_record)

    request_id = 100
    planning_context: dict | None = None
    seed_tag_entries: List[dict] = []
    if planner_only:
        seed_tags_args = {
            "prefix": "",
            "limit": planner_seed_tag_limit,
            "mode": planner_tag_count_mode,
        }
        seed_tags_response = _tools_call(
            url=mcp_url,
            request_id=request_id,
            tool_name="list_tags",
            arguments=seed_tags_args,
        )
        request_id += 1
        parsed_seed_tags = _extract_tool_response(call_response=seed_tags_response)
        seed_tag_entries = _extract_tag_entries_from_list_tags(parsed_list_tags=parsed_seed_tags)
        append_step(
            step_record={
                "step": len(steps) + 1,
                "action": "tag_seed_context",
                "tool_name": "list_tags",
                "arguments": seed_tags_args,
                "reason": "deterministic seed context: top existing tags for planner prior",
                "tool_response": {
                    "ok": True,
                    "data": _compact_json_payload(
                        value={
                            "seed_tag_count": len(seed_tag_entries),
                            "seed_tag_mode": planner_tag_count_mode,
                            "seed_tags": seed_tag_entries,
                        },
                        max_depth=6,
                        max_list_items=max(50, planner_seed_tag_limit),
                        max_dict_items=30,
                        max_string_chars=220,
                    ),
                },
            }
        )

    query_hypothesis_messages = _build_query_hypothesis_messages(
        user_message=user_message,
        seed_tag_entries=seed_tag_entries,
        seed_tag_count_mode=planner_tag_count_mode,
    )
    query_hypothesis_payload, query_hypothesis_raw = _ollama_chat_json_with_raw(
        ollama_chat_url=ollama_chat_url,
        model=resolved_model,
        messages=query_hypothesis_messages,
    )
    planner_error_text = ""
    try:
        query_hypothesis = _normalize_query_hypothesis(
            payload=query_hypothesis_payload,
        )
    except ValueError as error:
        planner_error_text = str(error)
        query_hypothesis = {
            "reasoning": "Planner output was invalid, so using heuristic tags from the question tokens.",
            "hypothesized_tags": _build_tag_discovery_terms(user_message=user_message),
        }
    planning_context = {
        "query_hypothesis": query_hypothesis,
    }
    if planner_error_text != "":
        planning_context["planner_error"] = planner_error_text

    model_plan_payload = {
        "reasoning": query_hypothesis["reasoning"],
        "hypothesized_tags": query_hypothesis["hypothesized_tags"],
        "prompt_messages": query_hypothesis_messages,
    }
    if planner_error_text != "":
        model_plan_payload["planner_error"] = planner_error_text
        model_plan_payload["raw_model_output"] = query_hypothesis_raw
    append_step(
        step_record={
            "step": len(steps) + 1,
            "action": "model_plan",
            "reason": "model hypothesized likely tags before tool calls",
            "model_payload": model_plan_payload,
        }
    )

    if planner_only:
        hypothesized_tags = query_hypothesis["hypothesized_tags"]
        if not isinstance(hypothesized_tags, list):
            raise TypeError("query_hypothesis.hypothesized_tags must be an array")

        list_tags_args = {
            "prefix": "",
            "limit": _PLANNER_TAG_CATALOG_LIMIT,
            "mode": planner_tag_count_mode,
        }
        list_tags_response = _tools_call(
            url=mcp_url,
            request_id=request_id,
            tool_name="list_tags",
            arguments=list_tags_args,
        )
        request_id += 1
        parsed_list_tags = _extract_tool_response(call_response=list_tags_response)
        tag_entries = _extract_tag_entries_from_list_tags(parsed_list_tags=parsed_list_tags)
        tag_match_data = _match_hypothesized_tags_to_catalog(
            hypothesized_tags=hypothesized_tags,
            tag_entries=tag_entries,
        )
        seed_tag_keys = set()
        for seed_entry in seed_tag_entries:
            if not isinstance(seed_entry, dict):
                continue
            seed_tag = seed_entry.get("tag")
            if not isinstance(seed_tag, str) or seed_tag == "":
                continue
            seed_key = _normalize_tag_term(value=seed_tag)
            if seed_key == "":
                continue
            seed_tag_keys.add(seed_key)

        exact_matches_from_seed: List[str] = []
        exact_matches_not_from_seed: List[str] = []
        exact_matches = tag_match_data.get("exact_matches")
        if isinstance(exact_matches, list):
            for match_entry in exact_matches:
                if not isinstance(match_entry, dict):
                    continue
                catalog_tag = match_entry.get("catalog_tag")
                if not isinstance(catalog_tag, str) or catalog_tag == "":
                    continue
                catalog_key = _normalize_tag_term(value=catalog_tag)
                from_seed = catalog_key in seed_tag_keys
                match_entry["from_seed"] = from_seed
                if from_seed:
                    exact_matches_from_seed.append(catalog_tag)
                else:
                    exact_matches_not_from_seed.append(catalog_tag)

        tag_match_data["exact_matches_from_seed"] = exact_matches_from_seed
        tag_match_data["exact_matches_not_from_seed"] = exact_matches_not_from_seed
        tag_match_data["seed_tag_count"] = len(seed_tag_entries)
        tag_match_data["catalog_fetch"] = {
            "mode": planner_tag_count_mode,
            "limit": list_tags_args["limit"],
            "total_matches": parsed_list_tags.get("data", {}).get("total_matches")
            if isinstance(parsed_list_tags.get("data"), dict)
            else None,
            "returned_count": parsed_list_tags.get("data", {}).get("returned_count")
            if isinstance(parsed_list_tags.get("data"), dict)
            else None,
        }
        append_step(
            step_record={
                "step": len(steps) + 1,
                "action": "tag_catalog_match",
                "tool_name": "list_tags",
                "arguments": list_tags_args,
                "reason": "programmatic exact/fuzzy match of planner tags against full catalog",
                "tool_response": {
                    "ok": True,
                    "data": _compact_json_payload(
                        value=tag_match_data,
                        max_depth=8,
                        max_list_items=200,
                        max_dict_items=50,
                        max_string_chars=300,
                    ),
                },
            }
        )

        tags_display = ", ".join(hypothesized_tags)
        answer = tags_display
        return {
            "ok": True,
            "answer": answer,
            "model": resolved_model,
            "steps": steps,
            "mode": "planner_only",
        }

    tools_list_response = _tools_list(url=mcp_url, request_id=2)
    tools_catalog = _extract_tools_catalog(list_response=tools_list_response)
    tool_summaries = _build_tool_summaries(tools_catalog=tools_catalog)

    system_prompt = _build_agent_system_prompt(
        tool_summaries=tool_summaries,
        planning_context=planning_context,
    )
    messages: List[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    query_terms = _query_terms_for_tags(user_message=user_message)

    append_step(
        step_record={
            "step": len(steps) + 1,
            "action": "agent_prompt",
            "reason": "initial agent messages sent to model",
            "model_payload": {
                "messages": messages,
            },
        }
    )

    invalid_repairs_remaining = _MAX_INVALID_DECISION_REPAIRS
    seen_search_signatures = set()

    def handle_invalid_decision(*, step_number: int, decision: dict, error_text: str) -> dict | None:
        nonlocal invalid_repairs_remaining
        append_step(
            step_record={
                "step": step_number,
                "action": "invalid_decision",
                "model_payload": _compact_for_output(value=decision),
                "tool_response": {
                    "ok": False,
                    "error": error_text,
                },
            }
        )
        if invalid_repairs_remaining <= 0:
            return {
                "ok": False,
                "answer": error_text,
                "model": resolved_model,
                "steps": steps,
            }
        invalid_repairs_remaining -= 1
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(_compact_for_model(value=decision), ensure_ascii=False),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": _invalid_decision_feedback_message(error_text=error_text),
            }
        )
        return None

    step_start = len(steps) + 1
    step_end = len(steps) + max_steps + 1
    for step_number in range(step_start, step_end):
        decision, raw_model_content = _ollama_chat_json_with_raw(
            ollama_chat_url=ollama_chat_url,
            model=resolved_model,
            messages=messages,
        )
        if "action" not in decision:
            error_text = "Agent response missing action."
            failed = handle_invalid_decision(
                step_number=step_number,
                decision={
                    "parsed": decision,
                    "raw": raw_model_content,
                },
                error_text=error_text,
            )
            if failed is not None:
                return failed
            continue
        action = decision["action"]
        if not isinstance(action, str):
            error_text = "Agent action must be a string."
            failed = handle_invalid_decision(
                step_number=step_number,
                decision=decision,
                error_text=error_text,
            )
            if failed is not None:
                return failed
            continue

        # Robustness: some models emit action as the tool name directly
        # (e.g. {"action":"search_notes", ...}) instead of {"action":"tool", ...}.
        if action not in {"tool", "final", "error"} and _is_tool_available(
            tool_summaries=tool_summaries,
            tool_name=action,
        ):
            coerced_decision = dict(decision)
            coerced_decision["action"] = "tool"
            if "tool_name" not in coerced_decision:
                coerced_decision["tool_name"] = action
            decision = coerced_decision
            action = "tool"

        if action == "final":
            if "answer" not in decision:
                error_text = "Final action missing answer."
                failed = handle_invalid_decision(
                    step_number=step_number,
                    decision=decision,
                    error_text=error_text,
                )
                if failed is not None:
                    return failed
                continue
            answer = decision["answer"]
            if not isinstance(answer, str):
                error_text = "Final answer must be a string."
                failed = handle_invalid_decision(
                    step_number=step_number,
                    decision=decision,
                    error_text=error_text,
                )
                if failed is not None:
                    return failed
                continue
            synthesized_answer = answer
            if _answer_needs_synthesis_pass(answer=answer):
                synthesized_answer = _run_synthesis_pass(
                    user_message=user_message,
                    draft_answer=answer,
                    steps=steps,
                    ollama_chat_url=ollama_chat_url,
                    model=resolved_model,
                )
                append_step(
                    step_record={
                        "step": len(steps) + 1,
                        "action": "synthesis_pass",
                        "tool_response": {
                            "ok": True,
                            "data": {
                                "draft_answer": answer,
                                "synthesized_answer": synthesized_answer,
                            },
                        },
                    }
                )
            return {
                "ok": True,
                "answer": synthesized_answer,
                "model": resolved_model,
                "steps": steps,
            }

        if action == "error":
            error_text = _extract_agent_error_text(decision=decision)
            append_step(
                step_record={
                    "step": step_number,
                    "action": "agent_error",
                    "model_payload": _compact_for_output(value=decision),
                    "tool_response": {
                        "ok": False,
                        "error": error_text,
                    },
                }
            )
            return {
                "ok": False,
                "answer": error_text,
                "model": resolved_model,
                "steps": steps,
            }

        if action != "tool":
            error_text = f"Agent returned unsupported action: {action!r}."
            failed = handle_invalid_decision(
                step_number=step_number,
                decision=decision,
                error_text=error_text,
            )
            if failed is not None:
                return failed
            continue

        if "tool_name" not in decision:
            error_text = "Tool action missing tool_name."
            failed = handle_invalid_decision(
                step_number=step_number,
                decision=decision,
                error_text=error_text,
            )
            if failed is not None:
                return failed
            continue
        if "arguments" not in decision:
            error_text = "Tool action missing arguments."
            failed = handle_invalid_decision(
                step_number=step_number,
                decision=decision,
                error_text=error_text,
            )
            if failed is not None:
                return failed
            continue
        tool_name = decision["tool_name"]
        arguments = decision["arguments"]
        if not isinstance(tool_name, str):
            error_text = "tool_name must be a string."
            failed = handle_invalid_decision(
                step_number=step_number,
                decision=decision,
                error_text=error_text,
            )
            if failed is not None:
                return failed
            continue
        if not isinstance(arguments, dict):
            error_text = "arguments must be an object."
            failed = handle_invalid_decision(
                step_number=step_number,
                decision=decision,
                error_text=error_text,
            )
            if failed is not None:
                return failed
            continue

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
            if tool_name == "search_notes":
                signature = _search_notes_semantic_signature(arguments=normalized_arguments)
                if signature in seen_search_signatures:
                    tool_response = {
                        "ok": False,
                        "error": (
                            "Duplicate search strategy: this search_notes call is semantically identical "
                            "to one already executed. Use a materially different query, exclusions, "
                            "or offset pagination."
                        ),
                    }
                else:
                    seen_search_signatures.add(signature)
                    tool_call_response = _tools_call(
                        url=mcp_url,
                        request_id=request_id,
                        tool_name=tool_name,
                        arguments=normalized_arguments,
                    )
                    tool_response = _extract_tool_response(call_response=tool_call_response)
            else:
                tool_call_response = _tools_call(
                    url=mcp_url,
                    request_id=request_id,
                    tool_name=tool_name,
                    arguments=normalized_arguments,
                )
                tool_response = _extract_tool_response(call_response=tool_call_response)

        output_response = _compact_for_output(value=tool_response)
        if tool_name == "get_note":
            model_response = _summarize_get_note_for_model(
                tool_response=tool_response,
                query_terms=query_terms,
            )
        else:
            model_response = _compact_for_model(value=tool_response)
        tool_feedback = {
            "tool_name": tool_name,
            "tool_response": model_response,
        }
        step_record = {
            "step": step_number,
            "action": "tool",
            "tool_name": tool_name,
            "arguments": normalized_arguments,
            "tool_response": output_response,
        }
        step_record["tool_feedback"] = _compact_for_output(value=tool_feedback)
        if arguments_changed:
            step_record["raw_arguments"] = _compact_for_output(value=arguments)
        if "reason" in decision and isinstance(decision["reason"], str):
            step_record["reason"] = decision["reason"]
        append_step(step_record=step_record)
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(_compact_for_model(value=decision), ensure_ascii=False),
            }
        )
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
    max_expressions: int
    hydrate_top_k: int
    regex_engine: str
    search_context_query: str
    mcp_url: str
    ollama_chat_url: str


def _web_html(
    *,
    default_model: str,
    default_max_steps: int,
    default_max_expressions: int,
    default_hydrate_top_k: int,
    default_regex_engine: str,
    default_search_context_query: str,
    default_mcp_url: str,
    default_ollama_chat_url: str,
) -> str:
    model_value = json.dumps(default_model)
    mcp_url_value = json.dumps(default_mcp_url)
    ollama_chat_url_value = json.dumps(default_ollama_chat_url)
    max_steps_value = str(default_max_steps)
    max_expressions_value = str(default_max_expressions)
    hydrate_top_k_value = str(default_hydrate_top_k)
    regex_engine_python_re_selected = (
        "selected" if default_regex_engine == "python-re" else ""
    )
    regex_engine_re2_selected = "selected" if default_regex_engine == "re2" else ""
    search_context_query_value = json.dumps(default_search_context_query)
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
    input, textarea, button, select {{
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
    .answer {{
      white-space: pre-wrap;
      background: #eef5ff;
      color: #1f2a3a;
      border-radius: 10px;
      padding: 12px;
      border: 1px solid #c8ddff;
      min-height: 48px;
      margin-bottom: 8px;
    }}
    .stage-list {{
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .stage-card {{
      background: #f5f8ff;
      border: 1px solid #c8ddff;
      border-radius: 10px;
      padding: 10px;
    }}
    .stage-title {{
      font-weight: 600;
      margin-bottom: 8px;
    }}
    .stage-summary {{
      font-size: 13px;
      color: #24344f;
      margin-bottom: 8px;
    }}
    .stage-summary-line {{
      margin-bottom: 4px;
    }}
    .stage-raw summary {{
      cursor: pointer;
      color: #355a92;
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .stage-json {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      background: #0f1c36;
      color: #d8e6ff;
      border-radius: 8px;
      padding: 10px;
      margin: 0;
      max-height: 320px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.35;
      tab-size: 2;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}
    .stage-prompt {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      background: #0f1c36;
      color: #d8e6ff;
      border-radius: 8px;
      padding: 10px;
      margin: 0;
      max-height: 420px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.4;
      tab-size: 2;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
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
          <label for="max_expressions">Max expressions</label>
          <input id="max_expressions" type="number" min="1" value="{max_expressions_value}" />
        </div>
        <div>
          <label for="hydrate_top_k">Hydrate top K</label>
          <input id="hydrate_top_k" type="number" min="1" value="{hydrate_top_k_value}" />
        </div>
        <div>
          <label for="regex_engine">Regex engine</label>
          <select id="regex_engine">
            <option value="python-re" {regex_engine_python_re_selected}>python-re</option>
            <option value="re2" {regex_engine_re2_selected}>re2</option>
          </select>
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
      <label for="search_context_query">Search context query (universe boundary)</label>
      <input id="search_context_query" value={search_context_query_value} placeholder='e.g. work-journal -private -@password' />
      <label for="prompt">Request</label>
      <textarea id="prompt" placeholder="Ask something, e.g. summarize top project notes tagged work..."></textarea>
      <div class="row">
        <button id="run_btn">Run Agent</button>
        <button id="models_btn" class="secondary">Load Ollama Models</button>
      </div>
      <p id="run_status" class="muted">Idle.</p>
      <h3>Final Answer</h3>
      <div id="final_answer" class="answer">No result yet.</div>
      <p id="final_timing" class="muted" style="display:none;"></p>
      <h3>Stages</h3>
      <div id="stage_list" class="stage-list">
        <p class="muted">No stages yet.</p>
      </div>
    </div>
  </div>
  <script>
    const finalAnswer = document.getElementById("final_answer");
    const finalTiming = document.getElementById("final_timing");
    const runBtn = document.getElementById("run_btn");
    const modelsBtn = document.getElementById("models_btn");
    const runStatus = document.getElementById("run_status");
    const stageList = document.getElementById("stage_list");
    const promptEl = document.getElementById("prompt");
    const modelEl = document.getElementById("model");
    const maxStepsEl = document.getElementById("max_steps");
    const maxExpressionsEl = document.getElementById("max_expressions");
    const hydrateTopKEl = document.getElementById("hydrate_top_k");
    const regexEngineEl = document.getElementById("regex_engine");
    const searchContextQueryEl = document.getElementById("search_context_query");
    const mcpUrlEl = document.getElementById("mcp_url");
    const ollamaChatUrlEl = document.getElementById("ollama_chat_url");

    function print(obj) {{
      void obj;
    }}

    function setFinalAnswer(text) {{
      finalAnswer.textContent = text;
    }}

    function formatDurationMs(totalMs) {{
      if (typeof totalMs !== "number" || !Number.isFinite(totalMs) || totalMs < 0) {{
        return "";
      }}
      if (totalMs < 1000) {{
        return `${{totalMs.toFixed(1)}} ms`;
      }}
      return `${{(totalMs / 1000).toFixed(2)}} s (${{totalMs.toFixed(1)}} ms)`;
    }}

    function setFinalTiming(text) {{
      if (typeof text !== "string" || text.trim() === "") {{
        finalTiming.textContent = "";
        finalTiming.style.display = "none";
        return;
      }}
      finalTiming.textContent = text;
      finalTiming.style.display = "block";
    }}

    function setRunStatus(text) {{
      runStatus.textContent = text;
    }}

    function resetStages() {{
      stageList.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No stages yet.";
      stageList.appendChild(empty);
    }}

    function extractModelPlanData(step) {{
      if (!step || typeof step !== "object") {{
        return {{ reasoning: "", hypothesizedTags: [], promptMessages: [] }};
      }}
      const payload = step.model_payload;
      if (!payload || typeof payload !== "object") {{
        return {{ reasoning: "", hypothesizedTags: [], promptMessages: [] }};
      }}
      let reasoning = "";
      if (typeof payload.reasoning === "string") {{
        reasoning = payload.reasoning;
      }}
      let hypothesizedTags = [];
      if (Array.isArray(payload.hypothesized_tags)) {{
        hypothesizedTags = payload.hypothesized_tags.filter((tag) => typeof tag === "string");
      }}
      let promptMessages = [];
      if (Array.isArray(payload.prompt_messages)) {{
        promptMessages = payload.prompt_messages.filter((entry) => entry && typeof entry === "object");
      }}
      return {{ reasoning, hypothesizedTags, promptMessages }};
    }}

    function extractPromptMessages(step) {{
      if (!step || typeof step !== "object") {{
        return [];
      }}
      const action = typeof step.action === "string" ? step.action : "";
      if (action === "model_plan") {{
        const planData = extractModelPlanData(step);
        return planData.promptMessages;
      }}
      if (action === "loop_iteration" && step.model_payload && typeof step.model_payload === "object") {{
        const payload = step.model_payload;
        const combined = [];
        if (Array.isArray(payload.planner_prompt_messages)) {{
          combined.push(...payload.planner_prompt_messages.filter((entry) => entry && typeof entry === "object"));
        }}
        if (Array.isArray(payload.decision_prompt_messages)) {{
          if (combined.length > 0) {{
            combined.push({{ role: "meta", content: "--- decision prompt ---" }});
          }}
          combined.push(...payload.decision_prompt_messages.filter((entry) => entry && typeof entry === "object"));
        }}
        if (combined.length > 0) {{
          return combined;
        }}
      }}
      if (step.model_payload && typeof step.model_payload === "object") {{
        const payload = step.model_payload;
        if (Array.isArray(payload.prompt_messages)) {{
          return payload.prompt_messages.filter((entry) => entry && typeof entry === "object");
        }}
        if (Array.isArray(payload.messages)) {{
          return payload.messages.filter((entry) => entry && typeof entry === "object");
        }}
      }}
      return [];
    }}

    function formatPromptMessages(messages) {{
      if (!Array.isArray(messages) || messages.length === 0) {{
        return "";
      }}
      const sections = [];
      for (const message of messages) {{
        const role = typeof message.role === "string" ? message.role.toUpperCase() : "UNKNOWN";
        let content = "";
        if (typeof message.content === "string") {{
          const parsedContent = tryParseJsonText(message.content);
          if (parsedContent !== null) {{
            content = JSON.stringify(prettifyRawModelOutput(parsedContent), null, 2);
          }} else {{
            const parsedSuffix = tryParseJsonSuffix(message.content);
            if (parsedSuffix !== null) {{
              const prettySuffix = JSON.stringify(
                prettifyRawModelOutput(parsedSuffix.parsed),
                null,
                2,
              );
              content = parsedSuffix.prefix + "\\n" + prettySuffix;
            }} else {{
              content = message.content;
            }}
          }}
        }} else {{
          content = JSON.stringify(prettifyRawModelOutput(message.content), null, 2);
        }}
        sections.push(`${{role}}:\\n${{content}}`);
      }}
      return sections.join("\\n\\n");
    }}

    function tryParseJsonText(text) {{
      if (typeof text !== "string") {{
        return null;
      }}
      const trimmed = text.trim();
      if (trimmed === "") {{
        return null;
      }}
      const startsLikeJson = trimmed.startsWith("{{") || trimmed.startsWith("[");
      if (!startsLikeJson) {{
        return null;
      }}
      try {{
        return JSON.parse(trimmed);
      }} catch (_error) {{
        return null;
      }}
    }}

    function tryParseJsonSuffix(text) {{
      if (typeof text !== "string") {{
        return null;
      }}
      const firstBrace = text.indexOf("{{");
      if (firstBrace <= 0) {{
        return null;
      }}
      const prefix = text.slice(0, firstBrace).trimEnd();
      const suffix = text.slice(firstBrace).trim();
      const parsed = tryParseJsonText(suffix);
      if (parsed === null) {{
        return null;
      }}
      return {{ prefix, parsed }};
    }}

    function prettifyRawModelOutput(value) {{
      if (Array.isArray(value)) {{
        return value.map((entry) => prettifyRawModelOutput(entry));
      }}
      if (!value || typeof value !== "object") {{
        return value;
      }}
      const output = {{}};
      for (const [key, child] of Object.entries(value)) {{
        if (key === "raw_model_output" && typeof child === "string") {{
          const parsed = tryParseJsonText(child);
          if (parsed !== null) {{
            output.raw_model_output = prettifyRawModelOutput(parsed);
            continue;
          }}
        }}
        if (typeof child === "string") {{
          const parsed = tryParseJsonText(child);
          if (parsed !== null) {{
            output[key] = prettifyRawModelOutput(parsed);
            continue;
          }}
        }}
        output[key] = prettifyRawModelOutput(child);
      }}
      return output;
    }}

    function buildStageSummary(step) {{
      const wrap = document.createElement("div");
      wrap.className = "stage-summary";
      if (!step || typeof step !== "object") {{
        wrap.textContent = "No details available.";
        return wrap;
      }}

      const action = typeof step.action === "string" ? step.action : "";
      if (action === "model_plan") {{
        const data = extractModelPlanData(step);
        if (data.hypothesizedTags.length > 0) {{
          const tagsLine = document.createElement("div");
          tagsLine.className = "stage-summary-line";
          tagsLine.textContent = "Hypothesized tags: " + data.hypothesizedTags.join(", ");
          wrap.appendChild(tagsLine);
        }}
        if (data.reasoning !== "") {{
          const reasoningLine = document.createElement("div");
          reasoningLine.className = "stage-summary-line";
          reasoningLine.textContent = "Reasoning: " + data.reasoning;
          wrap.appendChild(reasoningLine);
        }}
        if (wrap.childElementCount === 0) {{
          wrap.textContent = "Model produced a planning stage.";
        }}
        return wrap;
      }}

      if (action === "run_config") {{
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        if (!data) {{
          wrap.textContent = "Run configuration captured.";
          return wrap;
        }}
        const keys = [
          "max_steps",
          "max_expressions",
          "expression_target_count",
          "expression_probe_points",
          "execution_iteration_cap",
          "hydrate_top_k",
          "per_expression_limit",
          "regex_engine",
          "active_search_context_query",
          "universe_mode",
          "universe_note_count",
          "universe_resolution_ms",
          "universe_boundary_tool",
          "universe_boundary_arguments",
        ];
        for (const key of keys) {{
          if (!(key in data)) {{
            continue;
          }}
          const line = document.createElement("div");
          line.className = "stage-summary-line";
          line.textContent = `${{key}}: ` + JSON.stringify(data[key]);
          wrap.appendChild(line);
        }}
        return wrap;
      }}

      if (action === "universe_resolve") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (!stats) {{
          wrap.textContent = "Universe resolved.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent =
          `Universe: ${{stats.execution_ms}}ms, notes=${{stats.universe_note_count}}`;
        wrap.appendChild(line);
        return wrap;
      }}

      if (action === "expression_plan" || action === "expression_plan_repair" || action === "expression_plan_partial_accept") {{
        const payload = step.model_payload && typeof step.model_payload === "object" ? step.model_payload : null;
        if (!payload) {{
          wrap.textContent = "Expression plan generated.";
          return wrap;
        }}
        if (typeof payload.reasoning === "string" && payload.reasoning !== "") {{
          const reason = document.createElement("div");
          reason.className = "stage-summary-line";
          reason.textContent = "Reasoning: " + payload.reasoning;
          wrap.appendChild(reason);
        }}
        const expressions = Array.isArray(payload.expressions) ? payload.expressions : [];
        if (expressions.length > 0) {{
          const exprLine = document.createElement("div");
          exprLine.className = "stage-summary-line";
          exprLine.textContent = "Expressions: " + expressions.map((expr) => JSON.stringify(expr)).join(", ");
          wrap.appendChild(exprLine);

          const plannedCalls = [];
          for (const expr of expressions) {{
            if (!expr || typeof expr !== "object") {{
              continue;
            }}
            const exprType = typeof expr.type === "string" ? expr.type : "";
            if (exprType === "phrase") {{
              const value = typeof expr.value === "string" ? expr.value : "";
              if (value !== "") {{
                const compiledQuery = '"' + value + '"';
                plannedCalls.push("search_notes(query=" + JSON.stringify(compiledQuery) + ")");
              }}
              continue;
            }}
            if (exprType === "tag") {{
              const value = typeof expr.value === "string" ? expr.value : "";
              if (value !== "") {{
                plannedCalls.push(`search_notes(query=${{JSON.stringify(value)}})`);
              }}
              continue;
            }}
            if (exprType === "regex") {{
              const pattern = typeof expr.pattern === "string" ? expr.pattern : "";
              const flags = typeof expr.flags === "string" ? expr.flags : "";
              if (pattern !== "") {{
                plannedCalls.push(`search_notes_regex(/${{pattern}}/${{flags}})`);
              }}
              continue;
            }}
            if (exprType === "near") {{
              const left = typeof expr.left === "string" ? expr.left : "";
              const right = typeof expr.right === "string" ? expr.right : "";
              const windowChars = Number.isInteger(expr.window_chars) ? expr.window_chars : null;
              if (left !== "" && right !== "" && windowChars !== null) {{
                plannedCalls.push(`search_notes_regex(near:${{JSON.stringify(left)}}~${{JSON.stringify(right)}}@${{windowChars}})`);
              }}
            }}
          }}
          if (plannedCalls.length > 0) {{
            const callsLine = document.createElement("div");
            callsLine.className = "stage-summary-line";
            callsLine.textContent = "Compiled tool calls: " + plannedCalls.join(" | ");
            wrap.appendChild(callsLine);
          }}
        }}
        if ("accepted" in payload) {{
          const acceptedLine = document.createElement("div");
          acceptedLine.className = "stage-summary-line";
          acceptedLine.textContent = "Accepted: " + JSON.stringify(payload.accepted);
          wrap.appendChild(acceptedLine);
        }}
        if (typeof payload.validation_error === "string" && payload.validation_error !== "") {{
          const errorLine = document.createElement("div");
          errorLine.className = "stage-summary-line";
          errorLine.textContent = "Validation error: " + payload.validation_error;
          wrap.appendChild(errorLine);
        }}
        return wrap;
      }}

      if (action === "loop_iteration") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        const appendLine = (text, indentLevel = 0) => {{
          const line = document.createElement("div");
          line.className = "stage-summary-line";
          line.textContent = text;
          if (indentLevel > 0) {{
            line.style.marginLeft = `${{indentLevel * 14}}px`;
          }}
          wrap.appendChild(line);
        }};
        if (stats) {{
          appendLine("Stats:");
          if (Number.isInteger(stats.iteration_index)) {{
            appendLine(`iteration: ${{stats.iteration_index}}`, 1);
          }}
          if (typeof stats.phase === "string" && stats.phase !== "") {{
            appendLine(`phase: ${{stats.phase}}`, 1);
          }}
          appendLine(`planning_ms: ${{stats.planning_ms}}`, 1);
          appendLine(`decision_ms: ${{stats.decision_ms}}`, 1);
          appendLine(`queries_executed: ${{stats.executed_query_count}}`, 1);
          appendLine(`results: ${{stats.iteration_result_count}}`, 1);
          appendLine(`decision: ${{stats.decision}}`, 1);
        }}
        const queries = data && Array.isArray(data.queries_executed) ? data.queries_executed : [];
        if (queries.length > 0) {{
          appendLine("Executed queries:");
        }} else {{
          appendLine("Executed queries: none");
        }}
        let queryDisplayIndex = 0;
        for (const query of queries) {{
          if (!query || typeof query !== "object") {{
            continue;
          }}
          queryDisplayIndex += 1;
          const label = typeof query.expression_label === "string" ? query.expression_label : "expression";
          const ms = typeof query.execution_ms === "number" ? query.execution_ms : "?";
          const matches = Number.isInteger(query.scoped_match_count) ? query.scoped_match_count : "?";
          appendLine(`[${{queryDisplayIndex}}] ${{label}}`, 1);
          appendLine(`execution_ms: ${{ms}}`, 2);
          appendLine(`matches: ${{matches}}`, 2);
          const args = query.arguments && typeof query.arguments === "object" ? query.arguments : null;
          if (args && typeof args.query === "string" && args.query !== "") {{
            appendLine(`query: ${{args.query}}`, 2);
          }}
          if (args && typeof args.pattern === "string" && args.pattern !== "") {{
            appendLine(`pattern: /${{args.pattern}}/${{typeof args.flags === "string" ? args.flags : ""}}`, 2);
          }}

          const toolResponse = query.tool_response && typeof query.tool_response === "object" ? query.tool_response : null;
          const toolData = toolResponse && toolResponse.data && typeof toolResponse.data === "object" ? toolResponse.data : null;
          const results = toolData && Array.isArray(toolData.results) ? toolData.results : [];
          const snippets = [];
          for (const result of results.slice(0, 2)) {{
            if (!result || typeof result !== "object") {{
              continue;
            }}
            let snippet = "";
            if (typeof result.context_text === "string" && result.context_text.trim() !== "") {{
              snippet = result.context_text;
            }} else if (typeof result.content_text === "string" && result.content_text.trim() !== "") {{
              snippet = result.content_text;
            }} else if (typeof result.preview_text === "string" && result.preview_text.trim() !== "") {{
              snippet = result.preview_text;
            }}
            snippet = snippet.replace(/\\s+/g, " ").trim();
            if (snippet !== "") {{
              snippets.push(snippet.length > 140 ? snippet.slice(0, 140) + "..." : snippet);
            }}
          }}
          if (snippets.length > 0) {{
            appendLine("samples:", 2);
            for (let i = 0; i < snippets.length; i += 1) {{
              appendLine(`[${{i + 1}}] ${{snippets[i]}}`, 3);
            }}
          }}
        }}
        const decision = data && data.decision && typeof data.decision === "object" ? data.decision : null;
        if (decision) {{
          const decisionType = typeof decision.decision === "string" ? decision.decision : "unknown";
          const confidence = typeof decision.confidence === "string" ? decision.confidence : "unknown";
          appendLine("Decision:");
          appendLine(`type: ${{decisionType}}`, 1);
          appendLine(`confidence: ${{confidence}}`, 1);
          if (typeof decision.reasoning === "string" && decision.reasoning !== "") {{
            appendLine("reasoning: " + decision.reasoning, 1);
          }}
        }}
        return wrap;
      }}

      if (action === "expression_execute") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (!stats) {{
          wrap.textContent = "Expression executed.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent =
          `Expression ${{stats.expression_index}} (${{stats.expression_label}}): ` +
          `${{stats.execution_ms}}ms, matches=${{stats.scoped_match_count}}`;
        wrap.appendChild(line);
        if (step.arguments && typeof step.arguments === "object") {{
          const argsLine = document.createElement("div");
          argsLine.className = "stage-summary-line";
          argsLine.textContent = "Executed arguments: " + JSON.stringify(step.arguments);
          wrap.appendChild(argsLine);
        }}
        const regexSamples = Array.isArray(stats.regex_match_samples) ? stats.regex_match_samples : [];
        if (regexSamples.length > 0) {{
          const sampleHeader = document.createElement("div");
          sampleHeader.className = "stage-summary-line";
          sampleHeader.textContent = `Regex match snippets (${{regexSamples.length}}):`;
          wrap.appendChild(sampleHeader);
          for (const sample of regexSamples) {{
            if (!sample || typeof sample !== "object") {{
              continue;
            }}
            const field = typeof sample.field === "string" ? sample.field : "unknown";
            const snippet = typeof sample.snippet === "string" ? sample.snippet : "";
            if (snippet === "") {{
              continue;
            }}
            const sampleLine = document.createElement("div");
            sampleLine.className = "stage-summary-line";
            sampleLine.textContent = `- [${{field}}] ${{snippet}}`;
            wrap.appendChild(sampleLine);
          }}
        }}
        return wrap;
      }}

      if (action === "expression_execute_skip") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (!stats) {{
          wrap.textContent = "Skipped broader expression tiers.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent =
          `Stopped after tier ${{stats.stop_after_tier}}, skipped=${{stats.skipped_expression_count}}, candidates=${{stats.candidate_count}}`;
        wrap.appendChild(line);
        return wrap;
      }}

      if (action === "expression_execute_skip_duplicate") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (!stats) {{
          wrap.textContent = "Skipped duplicate expression.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent = "Duplicate signature skipped: " + JSON.stringify(stats.expression_signature);
        wrap.appendChild(line);
        return wrap;
      }}

      if (action === "expression_execute_skip_duplicate_query") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (!stats) {{
          wrap.textContent = "Skipped duplicate compiled query.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent = "Duplicate query skipped: " + JSON.stringify(stats.arguments || {{}});
        wrap.appendChild(line);
        return wrap;
      }}

      if (action === "expression_probe") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (!stats) {{
          wrap.textContent = "Expression probe checkpoint.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent =
          `Probe @${{stats.probe_point}}: candidates=${{stats.candidate_count}}, executed_regex=${{stats.executed_regex_count}}/${{stats.planned_regex_count}}`;
        wrap.appendChild(line);
        return wrap;
      }}

      if (action === "expression_stats") {{
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        if (!data) {{
          wrap.textContent = "Expression stats aggregated.";
          return wrap;
        }}
        const countLine = document.createElement("div");
        countLine.className = "stage-summary-line";
        countLine.textContent = `Candidate notes: ${{data.candidate_count ?? "?"}}`;
        wrap.appendChild(countLine);
        const rows = Array.isArray(data.expression_stats) ? data.expression_stats : [];
        for (const row of rows) {{
          if (!row || typeof row !== "object") {{
            continue;
          }}
          const line = document.createElement("div");
          line.className = "stage-summary-line";
          line.textContent = `- ${{row.expression_label}} => ${{row.execution_ms}}ms, scoped matches=${{row.scoped_match_count}}`;
          wrap.appendChild(line);
          const rowSamples = Array.isArray(row.regex_match_samples) ? row.regex_match_samples : [];
          if (rowSamples.length > 0) {{
            const preview = rowSamples
              .slice(0, 3)
              .map((sample) => {{
                if (!sample || typeof sample !== "object") {{
                  return "";
                }}
                const snippet = typeof sample.snippet === "string" ? sample.snippet : "";
                if (snippet === "") {{
                  return "";
                }}
                return snippet;
              }})
              .filter((text) => text !== "");
            if (preview.length > 0) {{
              const sampleLine = document.createElement("div");
              sampleLine.className = "stage-summary-line";
              sampleLine.textContent = "  samples: " + preview.join(" | ");
              wrap.appendChild(sampleLine);
            }}
          }}
        }}
        return wrap;
      }}

      if (action === "bulk_hydration") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (!stats) {{
          wrap.textContent = "Bulk hydration completed.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent = `Hydration: ${{stats.execution_ms}}ms, hydrated=${{stats.hydrated_note_count}}`;
        wrap.appendChild(line);
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        const noteSamples = data && Array.isArray(data.notes_sample) ? data.notes_sample : [];
        if (noteSamples.length > 0) {{
          const sampleHeader = document.createElement("div");
          sampleHeader.className = "stage-summary-line";
          sampleHeader.textContent = "Hydrated note samples:";
          wrap.appendChild(sampleHeader);
          for (const sample of noteSamples.slice(0, 8)) {{
            if (!sample || typeof sample !== "object") {{
              continue;
            }}
            const contextExcerpt = typeof sample.context_excerpt === "string" ? sample.context_excerpt : "";
            const contentExcerpt = typeof sample.content_excerpt === "string" ? sample.content_excerpt : "";
            const snippet = contextExcerpt !== "" ? contextExcerpt : contentExcerpt;
            if (snippet === "") {{
              continue;
            }}
            const sampleLine = document.createElement("div");
            sampleLine.className = "stage-summary-line";
            sampleLine.textContent = `- ${{snippet}}`;
            wrap.appendChild(sampleLine);
          }}
        }}
        return wrap;
      }}

      if (action === "iteration_reasoning") {{
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        if (!data) {{
          wrap.textContent = "Iteration reasoning complete.";
          return wrap;
        }}
        const decisionLine = document.createElement("div");
        decisionLine.className = "stage-summary-line";
        decisionLine.textContent =
          "Decision: " + (typeof data.decision === "string" ? data.decision : "unknown") +
          ", confidence=" + (typeof data.confidence === "string" ? data.confidence : "medium");
        wrap.appendChild(decisionLine);
        if (typeof data.reasoning === "string" && data.reasoning !== "") {{
          const reasoningLine = document.createElement("div");
          reasoningLine.className = "stage-summary-line";
          reasoningLine.textContent = "Reasoning: " + data.reasoning;
          wrap.appendChild(reasoningLine);
        }}
        if (typeof data.continue_reason === "string" && data.continue_reason !== "") {{
          const continueLine = document.createElement("div");
          continueLine.className = "stage-summary-line";
          continueLine.textContent = "Continue reason: " + data.continue_reason;
          wrap.appendChild(continueLine);
        }}
        if (typeof data.answer === "string" && data.answer !== "") {{
          const answerLine = document.createElement("div");
          answerLine.className = "stage-summary-line";
          answerLine.textContent = "Candidate answer: " + data.answer;
          wrap.appendChild(answerLine);
        }}
        if (typeof data.clarifying_question === "string" && data.clarifying_question !== "") {{
          const questionLine = document.createElement("div");
          questionLine.className = "stage-summary-line";
          questionLine.textContent = "Clarifying question: " + data.clarifying_question;
          wrap.appendChild(questionLine);
        }}
        return wrap;
      }}

      if (action === "iteration_decision_final") {{
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        if (!data) {{
          wrap.textContent = "Iteration reached final decision.";
          return wrap;
        }}
        const decisionPayload =
          data.decision && typeof data.decision === "object" ? data.decision : null;
        const decisionValue =
          decisionPayload && typeof decisionPayload.decision === "string"
            ? decisionPayload.decision
            : (typeof data.decision === "string" ? data.decision : "unknown");
        const confidenceValue =
          decisionPayload && typeof decisionPayload.confidence === "string"
            ? decisionPayload.confidence
            : (typeof data.confidence === "string" ? data.confidence : "unknown");
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent = `Final loop decision: ${{decisionValue}} (confidence=${{confidenceValue}})`;
        wrap.appendChild(line);
        const answerValue =
          decisionPayload && typeof decisionPayload.answer === "string"
            ? decisionPayload.answer
            : (typeof data.answer === "string" ? data.answer : "");
        if (answerValue !== "") {{
          const answerLine = document.createElement("div");
          answerLine.className = "stage-summary-line";
          answerLine.textContent = "Final answer: " + answerValue;
          wrap.appendChild(answerLine);
        }}
        const reasoningValue =
          decisionPayload && typeof decisionPayload.reasoning === "string"
            ? decisionPayload.reasoning
            : "";
        if (reasoningValue !== "") {{
          const reasoningLine = document.createElement("div");
          reasoningLine.className = "stage-summary-line";
          reasoningLine.textContent = "Reasoning: " + reasoningValue;
          wrap.appendChild(reasoningLine);
        }}
        return wrap;
      }}

      if (action === "synthesis_error") {{
        const toolResponse = step.tool_response && typeof step.tool_response === "object" ? step.tool_response : null;
        const errorText = toolResponse && typeof toolResponse.error === "string" ? toolResponse.error : "Synthesis error.";
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent = errorText;
        wrap.appendChild(line);
        return wrap;
      }}

      if (action === "no_evidence") {{
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        if (!data) {{
          wrap.textContent = "No matching evidence.";
          return wrap;
        }}
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent = typeof data.answer === "string" ? data.answer : "No matching evidence.";
        wrap.appendChild(line);
        return wrap;
      }}

      if (action === "tag_seed_context") {{
        let data = null;
        if (step.tool_response && typeof step.tool_response === "object") {{
          if (step.tool_response.data && typeof step.tool_response.data === "object") {{
            data = step.tool_response.data;
          }}
        }}
        if (!data) {{
          wrap.textContent = "Seed tag context loaded.";
          return wrap;
        }}
        const seedTags = Array.isArray(data.seed_tags) ? data.seed_tags : [];
        const seedMode = typeof data.seed_tag_mode === "string" ? data.seed_tag_mode : "unknown";
        const preview = seedTags
          .slice(0, 20)
          .map((entry) => {{
            if (!entry || typeof entry !== "object") {{
              return "";
            }}
            const tag = typeof entry.tag === "string" ? entry.tag : "";
            const count = typeof entry.count === "number" ? entry.count : null;
            if (tag === "") {{
              return "";
            }}
            if (count === null) {{
              return tag;
            }}
            return `${{tag}}(${{count}})`;
          }})
          .filter((text) => text !== "");
        const countLine = document.createElement("div");
        countLine.className = "stage-summary-line";
        const totalSeedCount = typeof data.seed_tag_count === "number" ? data.seed_tag_count : seedTags.length;
        countLine.textContent = `Seed tags loaded: ${{totalSeedCount}} (mode=${{seedMode}})`;
        wrap.appendChild(countLine);
        const tagsLine = document.createElement("div");
        tagsLine.className = "stage-summary-line";
        tagsLine.textContent = "Top tags: " + (preview.length > 0 ? preview.join(", ") : "none");
        wrap.appendChild(tagsLine);
        const noPromptLine = document.createElement("div");
        noPromptLine.className = "stage-summary-line";
        noPromptLine.textContent = "Model prompt: none (deterministic stage).";
        wrap.appendChild(noPromptLine);
        return wrap;
      }}

      if (action === "tag_catalog_match") {{
        let data = null;
        if (step.tool_response && typeof step.tool_response === "object") {{
          if (step.tool_response.data && typeof step.tool_response.data === "object") {{
            data = step.tool_response.data;
          }}
        }}
        if (!data) {{
          wrap.textContent = "Tag catalog matching completed.";
          return wrap;
        }}

        const catalogFetch = data.catalog_fetch && typeof data.catalog_fetch === "object" ? data.catalog_fetch : null;
        const exactMatches = Array.isArray(data.exact_matches) ? data.exact_matches : [];
        const fuzzyMatches = Array.isArray(data.fuzzy_matches) ? data.fuzzy_matches : [];
        const resolvedTags = Array.isArray(data.resolved_tags) ? data.resolved_tags.filter((tag) => typeof tag === "string") : [];
        const unmatched = Array.isArray(data.unmatched_hypothesized_tags)
          ? data.unmatched_hypothesized_tags.filter((tag) => typeof tag === "string")
          : [];

        if (catalogFetch) {{
          const catalogLine = document.createElement("div");
          catalogLine.className = "stage-summary-line";
          const totalMatches = typeof catalogFetch.total_matches === "number" ? catalogFetch.total_matches : "?";
          const returnedCount = typeof catalogFetch.returned_count === "number" ? catalogFetch.returned_count : "?";
          const fetchMode = typeof catalogFetch.mode === "string" ? catalogFetch.mode : "unknown";
          catalogLine.textContent = `Catalog tags fetched: ${{returnedCount}} / ${{totalMatches}} (mode=${{fetchMode}})`;
          wrap.appendChild(catalogLine);
        }}

        const exactLine = document.createElement("div");
        exactLine.className = "stage-summary-line";
        const exactTags = exactMatches
          .map((entry) => (entry && typeof entry.catalog_tag === "string" ? entry.catalog_tag : ""))
          .filter((tag) => tag !== "");
        exactLine.textContent = `Exact matches (${{exactTags.length}}): ` + (exactTags.length > 0 ? exactTags.join(", ") : "none");
        wrap.appendChild(exactLine);

        const exactFromSeed = Array.isArray(data.exact_matches_from_seed)
          ? data.exact_matches_from_seed.filter((tag) => typeof tag === "string")
          : exactMatches
              .filter((entry) => entry && entry.from_seed === true && typeof entry.catalog_tag === "string")
              .map((entry) => entry.catalog_tag);
        const exactNotFromSeed = Array.isArray(data.exact_matches_not_from_seed)
          ? data.exact_matches_not_from_seed.filter((tag) => typeof tag === "string")
          : exactMatches
              .filter((entry) => entry && entry.from_seed === false && typeof entry.catalog_tag === "string")
              .map((entry) => entry.catalog_tag);

        const exactFromSeedLine = document.createElement("div");
        exactFromSeedLine.className = "stage-summary-line";
        exactFromSeedLine.textContent =
          `Exact matches from initial N (${{exactFromSeed.length}}): ` +
          (exactFromSeed.length > 0 ? exactFromSeed.join(", ") : "none");
        wrap.appendChild(exactFromSeedLine);

        const exactNotFromSeedLine = document.createElement("div");
        exactNotFromSeedLine.className = "stage-summary-line";
        exactNotFromSeedLine.textContent =
          `Exact matches outside initial N (${{exactNotFromSeed.length}}): ` +
          (exactNotFromSeed.length > 0 ? exactNotFromSeed.join(", ") : "none");
        wrap.appendChild(exactNotFromSeedLine);

        const fuzzyLine = document.createElement("div");
        fuzzyLine.className = "stage-summary-line";
        const fuzzyPreview = fuzzyMatches
          .map((entry) => {{
            if (!entry || typeof entry !== "object") {{
              return "";
            }}
            const hypothesis = typeof entry.hypothesis === "string" ? entry.hypothesis : "?";
            const catalogTag = typeof entry.catalog_tag === "string" ? entry.catalog_tag : "?";
            return `${{hypothesis}} -> ${{catalogTag}}`;
          }})
          .filter((text) => text !== "");
        fuzzyLine.textContent = `Fuzzy matches (${{fuzzyMatches.length}}): ` + (fuzzyPreview.length > 0 ? fuzzyPreview.join(", ") : "none");
        wrap.appendChild(fuzzyLine);

        if (resolvedTags.length > 0) {{
          const resolvedLine = document.createElement("div");
          resolvedLine.className = "stage-summary-line";
          resolvedLine.textContent = `Resolved tags (${{resolvedTags.length}}): ` + resolvedTags.join(", ");
          wrap.appendChild(resolvedLine);
        }}

        if (unmatched.length > 0) {{
          const unmatchedLine = document.createElement("div");
          unmatchedLine.className = "stage-summary-line";
          unmatchedLine.textContent = `Unmatched hypotheses (${{unmatched.length}}): ` + unmatched.join(", ");
          wrap.appendChild(unmatchedLine);
        }}

        const noPromptLine = document.createElement("div");
        noPromptLine.className = "stage-summary-line";
        noPromptLine.textContent = "Model prompt: none (deterministic stage).";
        wrap.appendChild(noPromptLine);

        return wrap;
      }}

      if (action === "tool") {{
        const toolName = typeof step.tool_name === "string" ? step.tool_name : "tool";
        const line = document.createElement("div");
        line.className = "stage-summary-line";
        line.textContent = "Tool call: " + toolName;
        wrap.appendChild(line);
        if (step.arguments && typeof step.arguments === "object") {{
          const args = document.createElement("div");
          args.className = "stage-summary-line";
          args.textContent = "Arguments: " + JSON.stringify(step.arguments);
          wrap.appendChild(args);
        }}
        return wrap;
      }}

      const reason = typeof step.reason === "string" ? step.reason : "";
      if (reason !== "") {{
        wrap.textContent = reason;
      }} else {{
        wrap.textContent = "Stage recorded.";
      }}
      return wrap;
    }}

    function appendStage(step) {{
      if (stageList.children.length === 1) {{
        const onlyChild = stageList.firstElementChild;
        if (onlyChild && onlyChild.classList.contains("muted")) {{
          stageList.innerHTML = "";
        }}
      }}

      const card = document.createElement("div");
      card.className = "stage-card";

      const title = document.createElement("div");
      title.className = "stage-title";
      title.textContent = describeStep(step);
      card.appendChild(title);

      card.appendChild(buildStageSummary(step));

      const promptMessages = extractPromptMessages(step);
      if (promptMessages.length > 0) {{
        const promptDetails = document.createElement("details");
        promptDetails.className = "stage-raw";
        const promptSummary = document.createElement("summary");
        promptSummary.textContent = "Prompt Messages";
        promptDetails.appendChild(promptSummary);
        const promptPre = document.createElement("pre");
        promptPre.className = "stage-prompt";
        let promptRendered = false;
        const renderPrompt = () => {{
          if (promptRendered) {{
            return;
          }}
          promptPre.textContent = formatPromptMessages(promptMessages);
          promptRendered = true;
        }};
        promptDetails.addEventListener("toggle", () => {{
          if (promptDetails.open) {{
            renderPrompt();
          }}
        }});
        promptDetails.appendChild(promptPre);
        card.appendChild(promptDetails);
      }}

      const rawDetails = document.createElement("details");
      rawDetails.className = "stage-raw";
      const rawSummary = document.createElement("summary");
      rawSummary.textContent = "Raw JSON";
      rawDetails.appendChild(rawSummary);
      const detail = document.createElement("pre");
      detail.className = "stage-json";
      let rawRendered = false;
      const renderRaw = () => {{
        if (rawRendered) {{
          return;
        }}
        detail.textContent = JSON.stringify(prettifyRawModelOutput(step), null, 2);
        rawRendered = true;
      }};
      rawDetails.addEventListener("toggle", () => {{
        if (rawDetails.open) {{
          renderRaw();
        }}
      }});
      rawDetails.appendChild(detail);
      card.appendChild(rawDetails);

      stageList.appendChild(card);
    }}

    function describeStep(step) {{
      if (!step || typeof step !== "object") {{
        return "Running...";
      }}
      const stepNo = typeof step.step === "number" ? `Step ${{step.step}}` : "Step";
      const action = typeof step.action === "string" ? step.action : "action";
      const reason = typeof step.reason === "string" ? step.reason : "";
      if (action === "tool") {{
        const tool = typeof step.tool_name === "string" ? step.tool_name : "tool";
        if (reason !== "") {{
          return `${{stepNo}}: ${{tool}} - ${{reason}}`;
        }}
        return `${{stepNo}}: ${{tool}}`;
      }}
      if (action === "model_plan") {{
        let planningReasoning = "";
        if (step.model_payload && typeof step.model_payload === "object") {{
          if (typeof step.model_payload.reasoning === "string") {{
            planningReasoning = step.model_payload.reasoning;
          }} else if (step.model_payload.query_hypothesis && typeof step.model_payload.query_hypothesis === "object") {{
            if (typeof step.model_payload.query_hypothesis.reasoning === "string") {{
              planningReasoning = step.model_payload.query_hypothesis.reasoning;
            }}
          }}
        }}
        if (planningReasoning !== "") {{
          return `${{stepNo}}: planning - ${{planningReasoning}}`;
        }}
      }}
      if (action === "tag_catalog_match") {{
        if (reason !== "") {{
          return `${{stepNo}}: tag matching - ${{reason}}`;
        }}
        return `${{stepNo}}: tag matching`;
      }}
      if (action === "tag_seed_context") {{
        if (reason !== "") {{
          return `${{stepNo}}: seed tags - ${{reason}}`;
        }}
        return `${{stepNo}}: seed tags`;
      }}
      if (action === "run_config") {{
        return `${{stepNo}}: run config`;
      }}
      if (action === "universe_resolve") {{
        return `${{stepNo}}: universe resolve`;
      }}
      if (action === "expression_plan") {{
        return `${{stepNo}}: expression planning`;
      }}
      if (action === "expression_plan_repair") {{
        return `${{stepNo}}: expression planning repair`;
      }}
      if (action === "expression_plan_partial_accept") {{
        return `${{stepNo}}: expression planning partial accept`;
      }}
      if (action === "expression_plan_error") {{
        return `${{stepNo}}: expression planning error`;
      }}
      if (action === "loop_iteration") {{
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        if (stats && Number.isInteger(stats.iteration_index)) {{
          return `${{stepNo}}: loop iteration #${{stats.iteration_index}}`;
        }}
        return `${{stepNo}}: loop iteration`;
      }}
      if (action === "expression_execute") {{
        return `${{stepNo}}: expression execute`;
      }}
      if (action === "expression_execute_skip") {{
        return `${{stepNo}}: expression execute skip`;
      }}
      if (action === "expression_execute_skip_duplicate") {{
        return `${{stepNo}}: expression execute skip duplicate`;
      }}
      if (action === "expression_execute_skip_duplicate_query") {{
        return `${{stepNo}}: expression execute skip duplicate query`;
      }}
      if (action === "expression_probe") {{
        return `${{stepNo}}: expression probe`;
      }}
      if (action === "expression_stats") {{
        return `${{stepNo}}: expression stats`;
      }}
      if (action === "bulk_hydration") {{
        return `${{stepNo}}: bulk hydration`;
      }}
      if (action === "no_evidence") {{
        return `${{stepNo}}: no evidence`;
      }}
      if (action === "synthesis") {{
        return `${{stepNo}}: synthesis`;
      }}
      if (action === "iteration_reasoning") {{
        return `${{stepNo}}: iteration reasoning`;
      }}
      if (action === "iteration_decision_final") {{
        return `${{stepNo}}: iteration final`;
      }}
      if (action === "iteration_reasoning_error") {{
        return `${{stepNo}}: iteration reasoning error`;
      }}
      if (action === "synthesis_error") {{
        return `${{stepNo}}: synthesis error`;
      }}
      if (reason !== "") {{
        return `${{stepNo}}: ${{action}} - ${{reason}}`;
      }}
      return `${{stepNo}}: ${{action}}`;
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
      runBtn.textContent = "Running...";
      setFinalAnswer("Running...");
      setFinalTiming("");
      setRunStatus("Running...");
      resetStages();
      print({{ status: "running" }});
      try {{
        const payload = {{
          message: promptEl.value,
          model: modelEl.value,
          max_steps: Number(maxStepsEl.value),
          max_expressions: Number(maxExpressionsEl.value),
          hydrate_top_k: Number(hydrateTopKEl.value),
          regex_engine: regexEngineEl.value,
          search_context_query: searchContextQueryEl.value,
          mcp_url: mcpUrlEl.value,
          ollama_chat_url: ollamaChatUrlEl.value,
        }};
        const res = await fetchWithTimeout("/api/chat_stream", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload),
        }}, 180000);
        if (!res.ok) {{
          const errorBody = await readErrorResponse(res);
          print({{
            status: "error",
            where: "/api/chat_stream",
            http_status: res.status,
            detail: errorBody
          }});
          setFinalAnswer(`Error: ${{errorBody}}`);
          return;
        }}
        if (!res.body) {{
          print({{
            status: "error",
            where: "/api/chat_stream",
            detail: "Streaming response body missing"
          }});
          setFinalAnswer("Error: Streaming response body missing");
          return;
        }}
        const decoder = new TextDecoder();
        const reader = res.body.getReader();
        let buffer = "";
        let sawFinal = false;
        let sawError = false;
        const runningState = {{
          status: "running",
          steps: []
        }};
        print(runningState);

        while (true) {{
          const chunk = await reader.read();
          if (chunk.done) {{
            break;
          }}
          buffer += decoder.decode(chunk.value, {{ stream: true }});
          const lines = buffer.split("\\n");
          buffer = lines.pop() || "";
          for (const line of lines) {{
            const trimmed = line.trim();
            if (trimmed === "") {{
              continue;
            }}
            let event;
            try {{
              event = JSON.parse(trimmed);
            }} catch (parseError) {{
              print({{
                status: "error",
                where: "browser_stream_parse",
                detail: String(parseError),
                raw: trimmed
              }});
              setFinalAnswer("Error: " + String(parseError));
              return;
            }}
            if (event.type === "step") {{
              runningState.steps.push(event.step);
              setRunStatus(describeStep(event.step));
              appendStage(event.step);
              print(runningState);
              continue;
            }}
            if (event.type === "final") {{
              sawFinal = true;
              let answerText = "[No textual answer returned]";
              let timingText = "";
              if (event.result && typeof event.result === "object") {{
                if (typeof event.result.answer === "string" && event.result.answer !== "") {{
                  answerText = event.result.answer;
                }}
                const totalExecutionMs = event.result.total_execution_ms;
                if (typeof totalExecutionMs === "number" && Number.isFinite(totalExecutionMs)) {{
                  const formattedDuration = formatDurationMs(totalExecutionMs);
                  if (formattedDuration !== "") {{
                    timingText = "Total compute time: " + formattedDuration;
                  }}
                }}
              }}
              setFinalAnswer(answerText);
              setFinalTiming(timingText);
              setRunStatus(`Completed (${{runningState.steps.length}} steps).`);
              print({{ status: "ok", result: event.result }});
              continue;
            }}
            if (event.type === "error") {{
              sawError = true;
              print({{
                status: "error",
                where: "/api/chat_stream",
                detail: event.detail
              }});
              if (typeof event.detail === "string") {{
                setFinalAnswer("Error: " + event.detail);
              }} else {{
                setFinalAnswer("Error: unknown stream error");
              }}
              setFinalTiming("");
              setRunStatus("Failed.");
              continue;
            }}
            if (event.type === "status") {{
              runningState.status = event.status;
              if (event.status === "running") {{
                const detail = typeof event.detail === "string" ? event.detail : "";
                if (detail !== "") {{
                  setRunStatus(detail);
                }} else {{
                  setRunStatus("Running...");
                }}
                if (!sawFinal && !sawError) {{
                  setFinalAnswer("Running...");
                  setFinalTiming("");
                }}
              }}
              print(runningState);
            }}
          }}
        }}
        if (!sawFinal && !sawError) {{
          setFinalAnswer("No final answer returned. Check Stages for details.");
          setFinalTiming("");
          setRunStatus("Finished without final answer.");
        }}
      }} catch (err) {{
        let message = err instanceof Error ? err.message : String(err);
        if (message.includes("request-timeout")) {{
          message = "Request timed out after 180s. If model auto-pull is running, wait and retry.";
        }}
        print({{
          status: "error",
          where: "browser_fetch",
          detail: message
        }});
        setFinalAnswer("Error: " + message);
        setFinalTiming("");
        setRunStatus("Failed.");
      }} finally {{
        runBtn.disabled = false;
        runBtn.textContent = "Run Agent";
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
    default_max_expressions: int,
    default_hydrate_top_k: int,
    default_regex_engine: str,
    default_search_context_query: str,
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
            default_max_expressions=default_max_expressions,
            default_hydrate_top_k=default_hydrate_top_k,
            default_regex_engine=default_regex_engine,
            default_search_context_query=default_search_context_query,
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
        if payload.max_expressions <= 0:
            raise HTTPException(status_code=400, detail="max_expressions must be > 0")
        if payload.hydrate_top_k <= 0:
            raise HTTPException(status_code=400, detail="hydrate_top_k must be > 0")
        normalized_regex_engine = payload.regex_engine.casefold()
        if normalized_regex_engine not in _ALLOWED_REGEX_ENGINES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "regex_engine must be one of: "
                    + ", ".join(sorted(_ALLOWED_REGEX_ENGINES))
                ),
            )
        result = _run_rewrite_request(
            user_message=payload.message,
            search_context_query=payload.search_context_query,
            mcp_url=payload.mcp_url,
            ollama_chat_url=payload.ollama_chat_url,
            model=payload.model,
            max_steps=payload.max_steps,
            max_expressions=payload.max_expressions,
            hydrate_top_k=payload.hydrate_top_k,
            regex_engine=normalized_regex_engine,
            progress_callback=None,
        )
        return result

    @app.post("/api/chat_stream")
    def chat_stream(payload: AgentChatRequest) -> StreamingResponse:
        if payload.message.strip() == "":
            raise HTTPException(status_code=400, detail="message must not be empty")
        if payload.max_steps <= 0:
            raise HTTPException(status_code=400, detail="max_steps must be > 0")
        if payload.max_expressions <= 0:
            raise HTTPException(status_code=400, detail="max_expressions must be > 0")
        if payload.hydrate_top_k <= 0:
            raise HTTPException(status_code=400, detail="hydrate_top_k must be > 0")
        normalized_regex_engine = payload.regex_engine.casefold()
        if normalized_regex_engine not in _ALLOWED_REGEX_ENGINES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "regex_engine must be one of: "
                    + ", ".join(sorted(_ALLOWED_REGEX_ENGINES))
                ),
            )

        event_queue: queue.Queue[dict] = queue.Queue()
        worker_finished = threading.Event()
        heartbeat_lock = threading.Lock()
        heartbeat_state: Dict[str, object] = {
            "detail": "Starting...",
            "run_started_at": time.perf_counter(),
        }

        def progress_callback(step_record: dict) -> None:
            event_queue.put(
                {
                    "type": "step",
                    "step": step_record,
                }
            )

        def status_callback(detail: str) -> None:
            with heartbeat_lock:
                heartbeat_state["detail"] = detail
            event_queue.put(
                {
                    "type": "status",
                    "status": "running",
                    "detail": detail,
                }
            )

        def worker() -> None:
            try:
                result = _run_rewrite_request(
                    user_message=payload.message,
                    search_context_query=payload.search_context_query,
                    mcp_url=payload.mcp_url,
                    ollama_chat_url=payload.ollama_chat_url,
                    model=payload.model,
                    max_steps=payload.max_steps,
                    max_expressions=payload.max_expressions,
                    hydrate_top_k=payload.hydrate_top_k,
                    regex_engine=normalized_regex_engine,
                    progress_callback=progress_callback,
                    status_callback=status_callback,
                )
                event_queue.put(
                    {
                        "type": "final",
                        "result": result,
                    }
                )
            except Exception as exc:
                traceback.print_exc()
                event_queue.put(
                    {
                        "type": "error",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                )
            finally:
                worker_finished.set()
                event_queue.put({"type": "end"})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def event_stream():
            yield json.dumps({"type": "status", "status": "running", "detail": "Running..."}, ensure_ascii=False) + "\n"
            while True:
                try:
                    event = event_queue.get(timeout=1.0)
                except queue.Empty:
                    if worker_finished.is_set():
                        continue
                    with heartbeat_lock:
                        latest_detail = heartbeat_state.get("detail")
                        run_started_at = heartbeat_state.get("run_started_at")
                    if not isinstance(latest_detail, str) or latest_detail.strip() == "":
                        latest_detail = "Running..."
                    elapsed_ms = 0.0
                    if isinstance(run_started_at, float):
                        elapsed_ms = max((time.perf_counter() - run_started_at) * 1000.0, 0.0)
                    elapsed_sec = int(elapsed_ms // 1000.0)
                    heartbeat_detail = latest_detail + " (elapsed " + str(elapsed_sec) + "s)"
                    yield json.dumps(
                        {
                            "type": "status",
                            "status": "running",
                            "detail": heartbeat_detail,
                            "heartbeat": True,
                        },
                        ensure_ascii=False,
                    ) + "\n"
                    continue
                if not isinstance(event, dict):
                    continue
                if "type" not in event:
                    continue
                event_type = event["type"]
                if not isinstance(event_type, str):
                    continue
                if event_type == "end":
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"

        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    return app


def _run_web(
    *,
    host: str,
    port: int,
    mcp_url: str,
    ollama_chat_url: str,
    model: str,
    max_steps: int,
    max_expressions: int,
    hydrate_top_k: int,
    regex_engine: str,
    search_context_query: str,
) -> None:
    app = create_web_app(
        default_model=model,
        default_max_steps=max_steps,
        default_max_expressions=max_expressions,
        default_hydrate_top_k=hydrate_top_k,
        default_regex_engine=regex_engine,
        default_search_context_query=search_context_query,
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
    web_parser.add_argument("--max-expressions", type=int)
    web_parser.add_argument("--hydrate-top-k", type=int)
    web_parser.add_argument("--regex-engine")
    web_parser.add_argument("--search-context-query")

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

    if args.max_expressions is None:
        max_expressions = _DEFAULT_MAX_EXPRESSIONS
    else:
        max_expressions = args.max_expressions
    if max_expressions <= 0:
        raise ValueError("max-expressions must be > 0")

    if args.hydrate_top_k is None:
        hydrate_top_k = _DEFAULT_HYDRATE_TOP_K
    else:
        hydrate_top_k = args.hydrate_top_k
    if hydrate_top_k <= 0:
        raise ValueError("hydrate-top-k must be > 0")

    if args.regex_engine is None:
        regex_engine = _DEFAULT_REGEX_ENGINE
    else:
        regex_engine = args.regex_engine.casefold()
    if regex_engine not in _ALLOWED_REGEX_ENGINES:
        raise ValueError(
            "regex-engine must be one of: "
            + ", ".join(sorted(_ALLOWED_REGEX_ENGINES))
        )

    if args.search_context_query is None:
        search_context_query = _DEFAULT_SEARCH_CONTEXT_QUERY
    else:
        search_context_query = args.search_context_query

    _run_web(
        host=host,
        port=port,
        mcp_url=mcp_url,
        ollama_chat_url=ollama_chat_url,
        model=model,
        max_steps=max_steps,
        max_expressions=max_expressions,
        hydrate_top_k=hydrate_top_k,
        regex_engine=regex_engine,
        search_context_query=search_context_query,
    )


if __name__ == "__main__":
    main()
