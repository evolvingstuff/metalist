from __future__ import annotations

import argparse
import difflib
import html
import json
import math
import os
import queue
import re
import shutil
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
_DEFAULT_OLLAMA_MODEL = "qwen2.5:14b-instruct"
_DEFAULT_WEB_HOST = "127.0.0.1"
_DEFAULT_WEB_PORT = 8765
_DEFAULT_MAX_STEPS = 6
_DEFAULT_OLLAMA_AUTOSTART = True
_DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS = 20
_DEFAULT_OLLAMA_AUTOPULL = True
_DEFAULT_OLLAMA_PULL_TIMEOUT_SECONDS = 30
_DEFAULT_OLLAMA_TEMPERATURE = 0.0
_DEFAULT_OLLAMA_CONTEXT_LENGTH = 16384
_DEFAULT_POST_JSON_TIMEOUT_SECONDS = 60
_PLANNER_MAX_PHRASE_TOKENS = 2
_MAX_INVALID_DECISION_REPAIRS = 2
_OLLAMA_CHAT_TIMEOUT_SECONDS = 600
_DEFAULT_PLANNER_SEED_TAG_LIMIT = 50
_DEFAULT_PLANNER_TAG_COUNT_MODE = "raw"
_ALLOWED_PLANNER_TAG_COUNT_MODES = frozenset({"effective", "raw"})
_PLANNER_TAG_CATALOG_LIMIT = 100000
_DEFAULT_SEARCH_CONTEXT_QUERY = ""
_DEFAULT_MAX_EXPRESSIONS = 20
_DEFAULT_HYDRATE_TOP_K = 80
_DEFAULT_REGEX_ENGINE = "python-re"
_DEFAULT_CONTEXT_WINDOW_MAX_CHARS = 48000
_DEFAULT_V2_INCLUDE_TAGS_IN_CONTEXT_WINDOW = False
_DEFAULT_V2_NUM_CTX = 16384
_ALLOWED_REGEX_ENGINES = frozenset({"python-re", "re2"})
_PLANNER_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "should",
        "the",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "would",
    }
)
_MAX_EXPRESSION_SEARCH_RESULTS = 100000
_MAX_REWRITE_STEP_RESULT_LIMIT = 400
_STEP_NOTE_ID_SAMPLE_LIMIT = 50
_TAG_ATOM_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_EXPRESSION_PLAN_TARGET_CAP = 8
_EXPRESSION_PROBE_FIRST = 4
_EXPRESSION_PROBE_SECOND = 8
_SYNTHESIS_MAX_NOTES = 40
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
DEFAULT_OLLAMA_CONTEXT_LENGTH = _DEFAULT_OLLAMA_CONTEXT_LENGTH
DEFAULT_PLANNER_SEED_TAG_LIMIT = _DEFAULT_PLANNER_SEED_TAG_LIMIT
DEFAULT_PLANNER_TAG_COUNT_MODE = _DEFAULT_PLANNER_TAG_COUNT_MODE
DEFAULT_SEARCH_CONTEXT_QUERY = _DEFAULT_SEARCH_CONTEXT_QUERY
DEFAULT_MAX_EXPRESSIONS = _DEFAULT_MAX_EXPRESSIONS
DEFAULT_HYDRATE_TOP_K = _DEFAULT_HYDRATE_TOP_K
DEFAULT_REGEX_ENGINE = _DEFAULT_REGEX_ENGINE
DEFAULT_CONTEXT_WINDOW_MAX_CHARS = _DEFAULT_CONTEXT_WINDOW_MAX_CHARS
DEFAULT_V2_INCLUDE_TAGS_IN_CONTEXT_WINDOW = _DEFAULT_V2_INCLUDE_TAGS_IN_CONTEXT_WINDOW
DEFAULT_V2_NUM_CTX = _DEFAULT_V2_NUM_CTX

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


def _mapping_value_or_none(*, mapping: dict, key: str) -> object | None:
    if not isinstance(mapping, dict):
        raise TypeError("mapping must be an object")
    if not isinstance(key, str) or key == "":
        raise TypeError("key must be a non-empty string")
    if key in mapping:
        return mapping[key]
    return None


def _mapping_dict_or_none(*, mapping: dict, key: str) -> dict | None:
    value = _mapping_value_or_none(mapping=mapping, key=key)
    if not isinstance(value, dict):
        return None
    return value


def _mapping_list_or_empty(*, mapping: dict, key: str) -> list:
    value = _mapping_value_or_none(mapping=mapping, key=key)
    if not isinstance(value, list):
        return []
    return value


class _CapturedExceptionContext:
    def __init__(self, *exception_types: type[BaseException]) -> None:
        if len(exception_types) == 0:
            raise ValueError("exception_types must not be empty")
        self._exception_types = exception_types
        self.captured_exception: BaseException | None = None

    def __enter__(self) -> "_CapturedExceptionContext":
        self.captured_exception = None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> bool:
        if exc_type is None:
            return False
        for expected_type in self._exception_types:
            if issubclass(exc_type, expected_type):
                if exc is None:
                    raise RuntimeError("Captured exception context received missing exception")
                self.captured_exception = exc
                return True
        return False


def _post_json(*, url: str, payload: dict, timeout_seconds: int) -> dict | None:
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
        timeout_seconds=_DEFAULT_POST_JSON_TIMEOUT_SECONDS,
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
        timeout_seconds=_DEFAULT_POST_JSON_TIMEOUT_SECONDS,
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
        timeout_seconds=_DEFAULT_POST_JSON_TIMEOUT_SECONDS,
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


def _ancestor_plus_content_context_text(*, entry: dict) -> str:
    if not isinstance(entry, dict):
        raise TypeError("entry must be an object")

    content_text = _mapping_value_or_none(mapping=entry, key="content_text")
    if not isinstance(content_text, str):
        content_text = ""
    content_text = re.sub(r"\s+", " ", content_text).strip()

    ancestor_texts_raw = _mapping_value_or_none(mapping=entry, key="ancestor_texts")
    ancestor_texts: List[str] = []
    if isinstance(ancestor_texts_raw, list):
        for ancestor in ancestor_texts_raw:
            if not isinstance(ancestor, str):
                continue
            normalized = re.sub(r"\s+", " ", ancestor).strip()
            if normalized == "":
                continue
            ancestor_texts.append(normalized)

    if len(ancestor_texts) > 0:
        segments = [*ancestor_texts, content_text]
        return " --- ".join(segment for segment in segments if segment != "")

    if content_text != "":
        return content_text

    context_text = _mapping_value_or_none(mapping=entry, key="context_text")
    if isinstance(context_text, str):
        normalized_context = re.sub(r"\s+", " ", context_text).strip()
        if normalized_context != "":
            return normalized_context
    return content_text


def _note_snippet_text(*, note: dict) -> str:
    if not isinstance(note, dict):
        raise TypeError("note must be an object")
    for key in ("snippet_excerpt", "context_excerpt", "content_excerpt"):
        value = _mapping_value_or_none(mapping=note, key=key)
        if isinstance(value, str):
            normalized = re.sub(r"\s+", " ", value).strip()
            if normalized != "":
                return normalized
    return ""


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
        tag = _mapping_value_or_none(mapping=entry, key="tag")
        count = _mapping_value_or_none(mapping=entry, key="count")
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
        previous = _mapping_value_or_none(mapping=by_key, key=key)
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

        exact = _mapping_value_or_none(mapping=by_key, key=guess_key)
        has_exact = isinstance(exact, dict)
        if isinstance(exact, dict):
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

    reasoning_value = payload["reasoning"]
    if not isinstance(reasoning_value, str) or reasoning_value.strip() == "":
        raise ValueError("Planner reasoning must be a non-empty string")
    reasoning = reasoning_value.strip()

    raw_hypothesized_tags = _coerce_string_list(value=payload["hypothesized_tags"], max_items=32)
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
        tag = _mapping_value_or_none(mapping=entry, key="tag")
        count = _mapping_value_or_none(mapping=entry, key="count")
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
        tag = _mapping_value_or_none(mapping=tag_entry, key="tag")
        count = _mapping_value_or_none(mapping=tag_entry, key="count")
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
        "options": {"temperature": _DEFAULT_OLLAMA_TEMPERATURE},
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
        "options": {"temperature": _DEFAULT_OLLAMA_TEMPERATURE},
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


def _ollama_chat_text(
    *,
    ollama_chat_url: str,
    model: str,
    messages: List[dict],
    num_ctx: int | None,
) -> str:
    runtime = _ollama_chat_text_with_runtime(
        ollama_chat_url=ollama_chat_url,
        model=model,
        messages=messages,
        num_ctx=num_ctx,
    )
    content = _mapping_value_or_none(mapping=runtime, key="content")
    if not isinstance(content, str):
        raise TypeError("runtime content must be a string")
    return content


def _ollama_chat_text_with_runtime(
    *,
    ollama_chat_url: str,
    model: str,
    messages: List[dict],
    num_ctx: int | None,
) -> dict:
    if num_ctx is not None and num_ctx <= 0:
        raise ValueError("num_ctx must be > 0")
    ensure_ollama_running(
        ollama_chat_url=ollama_chat_url,
        autostart=_DEFAULT_OLLAMA_AUTOSTART,
        wait_timeout_seconds=_DEFAULT_OLLAMA_STARTUP_TIMEOUT_SECONDS,
    )
    options = {"temperature": _DEFAULT_OLLAMA_TEMPERATURE}
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    payload = {
        "model": model,
        "stream": False,
        "options": options,
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
    served_model = _mapping_value_or_none(mapping=response, key="model")
    if not isinstance(served_model, str):
        served_model = ""
    return {
        "content": content,
        "served_model": served_model,
    }


def _derive_tags_url(*, ollama_chat_url: str) -> str:
    suffix = "/api/chat"
    if not ollama_chat_url.endswith(suffix):
        raise ValueError("ollama_chat_url must end with /api/chat")
    return ollama_chat_url[: -len(suffix)] + "/api/tags"


def _derive_show_url(*, ollama_chat_url: str) -> str:
    suffix = "/api/chat"
    if not ollama_chat_url.endswith(suffix):
        raise ValueError("ollama_chat_url must end with /api/chat")
    return ollama_chat_url[: -len(suffix)] + "/api/show"


def _derive_ps_url(*, ollama_chat_url: str) -> str:
    suffix = "/api/chat"
    if not ollama_chat_url.endswith(suffix):
        raise ValueError("ollama_chat_url must end with /api/chat")
    return ollama_chat_url[: -len(suffix)] + "/api/ps"


def _extract_model_context_length_from_show_response(*, show_response: dict) -> int | None:
    model_info = _mapping_value_or_none(mapping=show_response, key="model_info")
    if not isinstance(model_info, dict):
        return None

    for key in model_info:
        if not isinstance(key, str):
            continue
        if not key.endswith(".context_length"):
            continue
        value = model_info[key]
        if isinstance(value, int) and value > 0:
            return value

    details = _mapping_value_or_none(mapping=show_response, key="details")
    if isinstance(details, dict):
        context_length = _mapping_value_or_none(mapping=details, key="context_length")
        if isinstance(context_length, int) and context_length > 0:
            return context_length

    return None


def _ollama_model_context_length(*, ollama_chat_url: str, model: str) -> int | None:
    show_url = _derive_show_url(ollama_chat_url=ollama_chat_url)
    response = _post_json(
        url=show_url,
        payload={"model": model},
        timeout_seconds=30,
    )
    if response is None:
        return None
    return _extract_model_context_length_from_show_response(show_response=response)


def _extract_running_model_num_ctx(*, ps_payload: dict, model: str) -> int | None:
    models = _mapping_value_or_none(mapping=ps_payload, key="models")
    if not isinstance(models, list):
        return None

    target = model.strip().casefold()
    for model_entry in models:
        if not isinstance(model_entry, dict):
            continue
        entry_model = _mapping_value_or_none(mapping=model_entry, key="model")
        if not isinstance(entry_model, str):
            continue
        if entry_model.strip().casefold() != target:
            continue

        top_level_num_ctx = _mapping_value_or_none(mapping=model_entry, key="num_ctx")
        if isinstance(top_level_num_ctx, int) and top_level_num_ctx > 0:
            return top_level_num_ctx

        details = _mapping_value_or_none(mapping=model_entry, key="details")
        if isinstance(details, dict):
            details_num_ctx = _mapping_value_or_none(mapping=details, key="num_ctx")
            if isinstance(details_num_ctx, int) and details_num_ctx > 0:
                return details_num_ctx

        options = _mapping_value_or_none(mapping=model_entry, key="options")
        if isinstance(options, dict):
            options_num_ctx = _mapping_value_or_none(mapping=options, key="num_ctx")
            if isinstance(options_num_ctx, int) and options_num_ctx > 0:
                return options_num_ctx

    return None


def _ollama_running_model_num_ctx(*, ollama_chat_url: str, model: str) -> int | None:
    ps_url = _derive_ps_url(ollama_chat_url=ollama_chat_url)
    payload = _get_json(url=ps_url)
    return _extract_running_model_num_ctx(ps_payload=payload, model=model)


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


def _report_ollama_reset_skip(*, detail: str) -> None:
    print(f"Skipping Ollama reset: {detail}", file=sys.stderr)


def reset_local_ollama_server(*, ollama_chat_url: str) -> None:
    host, _ = _ollama_host_port(ollama_chat_url=ollama_chat_url)
    if not _is_local_host(host=host):
        return

    global _OLLAMA_SIDECAR_PROCESS
    _OLLAMA_SIDECAR_PROCESS = None
    if shutil.which("pkill") is None:
        _report_ollama_reset_skip(detail="`pkill` is unavailable on this system.")
        return

    run_capture = _CapturedExceptionContext(OSError)
    completed: subprocess.CompletedProcess[str] | None = None
    with run_capture:
        completed = subprocess.run(
            ["pkill", "-f", "ollama serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    if run_capture.captured_exception is not None:
        error = run_capture.captured_exception
        _report_ollama_reset_skip(detail=f"`pkill -f 'ollama serve'` failed: {error}")
        return
    if completed is None:
        raise RuntimeError("pkill subprocess did not produce a completion record")

    if completed.returncode not in {0, 1}:
        stderr_output = completed.stderr.strip()
        detail = f"`pkill -f 'ollama serve'` failed with code {completed.returncode}."
        if stderr_output != "":
            detail = f"{detail} stderr: {stderr_output}"
        _report_ollama_reset_skip(detail=detail)
        return

    time.sleep(0.25)


def _resolve_ollama_context_length() -> int:
    if "MCP_AGENT_OLLAMA_CONTEXT_LENGTH" in os.environ:
        configured_value = os.environ["MCP_AGENT_OLLAMA_CONTEXT_LENGTH"].strip()
        if configured_value == "":
            raise ValueError("MCP_AGENT_OLLAMA_CONTEXT_LENGTH must not be empty")
        if not configured_value.isdigit():
            raise ValueError("MCP_AGENT_OLLAMA_CONTEXT_LENGTH must be a positive integer")
        resolved = int(configured_value)
        if resolved <= 0:
            raise ValueError("MCP_AGENT_OLLAMA_CONTEXT_LENGTH must be > 0")
        return resolved

    if "OLLAMA_CONTEXT_LENGTH" in os.environ:
        configured_value = os.environ["OLLAMA_CONTEXT_LENGTH"].strip()
        if configured_value == "":
            raise ValueError("OLLAMA_CONTEXT_LENGTH must not be empty")
        if not configured_value.isdigit():
            raise ValueError("OLLAMA_CONTEXT_LENGTH must be a positive integer")
        resolved = int(configured_value)
        if resolved <= 0:
            raise ValueError("OLLAMA_CONTEXT_LENGTH must be > 0")
        return resolved

    return _DEFAULT_OLLAMA_CONTEXT_LENGTH


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
        resolved_context_length = _resolve_ollama_context_length()
        ollama_env = dict(os.environ)
        ollama_env["OLLAMA_CONTEXT_LENGTH"] = str(resolved_context_length)
        print(
            "Starting Ollama automatically: "
            f"OLLAMA_CONTEXT_LENGTH={resolved_context_length} ollama serve"
        )
        _OLLAMA_SIDECAR_PROCESS = subprocess.Popen(
            ["ollama", "serve"],
            env=ollama_env,
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

    required_raw: object = []
    if "required_tags" in arguments:
        required_raw = arguments["required_tags"]
    forbidden_raw: object = []
    if "forbidden_tags" in arguments:
        forbidden_raw = arguments["forbidden_tags"]
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

    parse_capture = _CapturedExceptionContext(ValueError)
    with parse_capture:
        parse_search_query(canonical_query)
    if parse_capture.captured_exception is not None:
        error = parse_capture.captured_exception
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

    limit: int | None = None
    if "limit" in arguments:
        limit_value = arguments["limit"]
        if isinstance(limit_value, int):
            limit = limit_value
    offset: int | None = None
    if "offset" in arguments:
        offset_value = arguments["offset"]
        if isinstance(offset_value, int):
            offset = offset_value

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
    pattern = _mapping_value_or_none(mapping=arguments, key="pattern")
    flags = _mapping_value_or_none(mapping=arguments, key="flags")
    regex_engine = _mapping_value_or_none(mapping=arguments, key="regex_engine")
    target = _mapping_value_or_none(mapping=arguments, key="target")
    limit = _mapping_value_or_none(mapping=arguments, key="limit")
    offset = _mapping_value_or_none(mapping=arguments, key="offset")
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

    scope_note_ids = _mapping_value_or_none(mapping=arguments, key="scope_note_ids")
    scope_note_ids_count = 0
    if isinstance(scope_note_ids, list):
        scope_note_ids_count = len(scope_note_ids)
    scope_query = _mapping_value_or_none(mapping=arguments, key="scope_query")
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
    if _mapping_value_or_none(mapping=tool_response, key="ok") is not True:
        return []
    data = _mapping_value_or_none(mapping=tool_response, key="data")
    if not isinstance(data, dict):
        return []
    return _extract_note_ids_from_tool_data(data=data)


def _extract_ordered_note_ids_from_tool_results(*, tool_response: dict) -> List[str]:
    if not isinstance(tool_response, dict):
        raise TypeError("tool_response must be an object")
    if _mapping_value_or_none(mapping=tool_response, key="ok") is not True:
        return []
    data = _mapping_value_or_none(mapping=tool_response, key="data")
    if not isinstance(data, dict):
        return []
    return _extract_note_ids_from_tool_data(data=data)


def _extract_note_ids_from_tool_data(*, data: dict) -> List[str]:
    if not isinstance(data, dict):
        raise TypeError("data must be an object")

    ordered: List[str] = []
    seen = set()

    note_ids = _mapping_value_or_none(mapping=data, key="note_ids")
    if isinstance(note_ids, list):
        for note_id in note_ids:
            if not isinstance(note_id, str) or note_id == "":
                continue
            if note_id in seen:
                continue
            seen.add(note_id)
            ordered.append(note_id)
        return ordered

    results = _mapping_value_or_none(mapping=data, key="results")
    if not isinstance(results, list):
        return ordered

    for entry in results:
        if not isinstance(entry, dict):
            continue
        note_id = _mapping_value_or_none(mapping=entry, key="note_id")
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
    if _mapping_value_or_none(mapping=tool_response, key="ok") is not True:
        return tool_response

    data = _mapping_value_or_none(mapping=tool_response, key="data")
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

    notes = _mapping_value_or_none(mapping=data, key="notes")
    if isinstance(notes, list):
        note_entries: List[dict] = []
        for note in notes:
            if not isinstance(note, dict):
                continue
            entry: Dict[str, object] = {}
            content_text = _mapping_value_or_none(mapping=note, key="content_text")
            if isinstance(content_text, str) and content_text.strip() != "":
                entry["content_excerpt"] = _clip_text_for_synthesis(
                    text=content_text,
                    max_chars=220,
                )
            context_text = _mapping_value_or_none(mapping=note, key="context_text")
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

    results = _mapping_value_or_none(mapping=data, key="results")
    if isinstance(results, list):
        regex_match_samples: List[dict] = []
        max_samples = max(4, min(note_id_sample_limit * 2, 24))
        for entry in results:
            if not isinstance(entry, dict):
                continue
            matches = _mapping_value_or_none(mapping=entry, key="matches")
            if not isinstance(matches, list):
                continue
            for match in matches:
                if not isinstance(match, dict):
                    continue
                snippet = _mapping_value_or_none(mapping=match, key="snippet")
                if not isinstance(snippet, str) or snippet.strip() == "":
                    continue
                field = _mapping_value_or_none(mapping=match, key="field")
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


def _compact_iteration_result_entry_for_model(*, entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise TypeError("entry must be an object")

    snippet_source = _ancestor_plus_content_context_text(entry=entry)
    if snippet_source == "":
        return {}
    return {
        "snippet_excerpt": _clip_text_for_synthesis(
            text=snippet_source,
            max_chars=1200,
        )
    }


def _compact_tool_response_for_iteration(*, tool_response: dict, max_results: int) -> dict:
    if not isinstance(tool_response, dict):
        raise TypeError("tool_response must be an object")
    if max_results <= 0:
        raise ValueError("max_results must be > 0")

    if _mapping_value_or_none(mapping=tool_response, key="ok") is not True:
        error_value = _mapping_value_or_none(mapping=tool_response, key="error")
        error_text = "tool call failed"
        if isinstance(error_value, str) and error_value.strip() != "":
            error_text = error_value
        return {
            "ok": False,
            "error": error_text,
        }

    data = _mapping_value_or_none(mapping=tool_response, key="data")
    if not isinstance(data, dict):
        return {
            "ok": True,
            "data": {},
        }

    compact_data: Dict[str, object] = {}
    passthrough_keys = [
        "query",
        "resolved_query",
        "pattern",
        "flags",
        "regex_engine",
        "target",
        "limit",
        "offset",
        "total_matches",
        "returned_count",
    ]
    for key in passthrough_keys:
        if key in data:
            compact_data[key] = data[key]

    results = _mapping_value_or_none(mapping=data, key="results")
    if isinstance(results, list):
        compact_results: List[dict] = []
        for entry in results[:max_results]:
            if not isinstance(entry, dict):
                continue
            compact_entry = _compact_iteration_result_entry_for_model(entry=entry)
            if len(compact_entry) == 0:
                continue
            compact_results.append(compact_entry)
        compact_data["results_total"] = len(results)
        compact_data["results"] = compact_results

    return {
        "ok": True,
        "data": compact_data,
    }


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
    min_expressions: int,
    source_message: str | None,
) -> dict:
    if min_expressions < 0:
        raise ValueError("min_expressions must be >= 0")
    if min_expressions > max_expressions:
        raise ValueError("min_expressions must be <= max_expressions")
    if not isinstance(payload, dict):
        raise ValueError("Expression planner output must be a JSON object")

    reasoning_value = _mapping_value_or_none(mapping=payload, key="reasoning")
    if not isinstance(reasoning_value, str):
        reasoning = "Model omitted reasoning."
    else:
        reasoning = reasoning_value.strip()
        if reasoning == "":
            reasoning = "Model omitted reasoning."

    raw_expressions = _mapping_value_or_none(mapping=payload, key="expressions")
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
        raw_type = _mapping_value_or_none(mapping=raw_expression, key="type")
        if not isinstance(raw_type, str):
            continue
        normalized_type = raw_type.casefold().strip()
        if normalized_type not in {"phrase", "regex", "near"}:
            continue

        normalized_expression: dict
        dedupe_key: tuple
        if normalized_type == "phrase":
            value = _mapping_value_or_none(mapping=raw_expression, key="value")
            if not isinstance(value, str):
                continue
            normalized_value = re.sub(r"\s+", " ", value).strip()
            if normalized_value == "":
                continue
            if _phrase_token_count(value=normalized_value) > _PLANNER_MAX_PHRASE_TOKENS:
                continue
            if enforce_ascii_only and not normalized_value.isascii():
                continue
            normalized_expression = {
                "type": "phrase",
                "value": normalized_value,
            }
            dedupe_key = ("phrase", normalized_value.casefold())
        elif normalized_type == "regex":
            pattern = _mapping_value_or_none(mapping=raw_expression, key="pattern")
            if not isinstance(pattern, str) or pattern.strip() == "":
                continue
            pattern = pattern.replace("\x08", r"\b")
            if enforce_ascii_only and not pattern.isascii():
                continue
            flags_value = _mapping_value_or_none(mapping=raw_expression, key="flags")
            if flags_value is None:
                flags_value = ""
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
            left_value = _mapping_value_or_none(mapping=raw_expression, key="left")
            right_value = _mapping_value_or_none(mapping=raw_expression, key="right")
            window_chars = _mapping_value_or_none(mapping=raw_expression, key="window_chars")
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


def _extract_planner_anchor_terms(*, source_message: str, max_terms: int) -> List[str]:
    if not isinstance(source_message, str):
        raise TypeError("source_message must be a string")
    if max_terms <= 0:
        raise ValueError("max_terms must be > 0")
    raw_tokens = re.findall(r"[A-Za-z0-9']+", source_message)
    anchors: List[str] = []
    seen = set()
    for raw in raw_tokens:
        token = raw.casefold().strip()
        if token.endswith("'s"):
            token = token[:-2]
        if token == "":
            continue
        if token in _PLANNER_STOPWORDS:
            continue
        if len(token) < 3:
            continue
        if token in seen:
            continue
        seen.add(token)
        anchors.append(token)
        if len(anchors) >= max_terms:
            break
    return anchors


def _expression_execution_tier(*, expression: dict) -> int:
    if not isinstance(expression, dict):
        raise TypeError("expression must be an object")
    expression_type = _mapping_value_or_none(mapping=expression, key="type")
    if not isinstance(expression_type, str):
        return 2
    if expression_type == "near":
        return 1
    if expression_type == "phrase":
        value = _mapping_value_or_none(mapping=expression, key="value")
        if not isinstance(value, str):
            return 2
        token_count = _phrase_token_count(value=value)
        if token_count >= 2:
            return 0
        return 2
    if expression_type == "regex":
        pattern = _mapping_value_or_none(mapping=expression, key="pattern")
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

    def _single_phrase_to_regex_tokens(phrase: str) -> str:
        escaped = re.escape(phrase)
        return re.sub(r"\\\s+", r"\\s+", escaped)

    def _anchor_to_pattern(anchor: str) -> str:
        raw_parts = anchor.split("|")
        normalized_parts: List[str] = []
        for raw_part in raw_parts:
            part = re.sub(r"\s+", " ", raw_part).strip()
            if part == "":
                continue
            if (
                len(part) >= 2
                and ((part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")))
            ):
                part = part[1:-1].strip()
            if part == "":
                continue
            token_pattern = _single_phrase_to_regex_tokens(part)
            if token_pattern == "":
                continue
            normalized_parts.append(token_pattern)
        if len(normalized_parts) == 0:
            raise ValueError("near anchor must include at least one non-empty phrase")
        if len(normalized_parts) == 1:
            return normalized_parts[0]
        return "(?:" + "|".join(normalized_parts) + ")"

    left_pattern = _anchor_to_pattern(left)
    right_pattern = _anchor_to_pattern(right)
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
    expression_type = _mapping_value_or_none(mapping=expression, key="type")
    if not isinstance(expression_type, str):
        raise TypeError("expression.type must be a string")

    if expression_type == "phrase":
        phrase_value = _mapping_value_or_none(mapping=expression, key="value")
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
        tag_value = _mapping_value_or_none(mapping=expression, key="value")
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
        pattern = _mapping_value_or_none(mapping=expression, key="pattern")
        flags = _mapping_value_or_none(mapping=expression, key="flags")
        if not isinstance(pattern, str):
            raise TypeError("regex expression pattern must be a string")
        if not isinstance(flags, str):
            raise TypeError("regex expression flags must be a string")
        scope_note_ids: List[str] = []
        scope_note_ids_count = 0
        if universe_note_ids is not None:
            scope_note_ids = universe_note_ids
            scope_note_ids_count = len(universe_note_ids)
        tool_name = "search_notes_regex"
        tool_args = {
            "pattern": pattern,
            "flags": flags,
            "regex_engine": normalized_regex_engine,
            "target": "both",
            "scope_note_ids": scope_note_ids,
            "limit": per_expression_limit,
            "offset": 0,
        }
        display_args = {
            "pattern": pattern,
            "flags": flags,
            "regex_engine": normalized_regex_engine,
            "target": "both",
            "scope_note_ids_count": scope_note_ids_count,
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
        left = _mapping_value_or_none(mapping=expression, key="left")
        right = _mapping_value_or_none(mapping=expression, key="right")
        window_chars = _mapping_value_or_none(mapping=expression, key="window_chars")
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
    source_message: str | None,
) -> dict:
    normalize_capture = _CapturedExceptionContext(ValueError)
    normalized_plan: dict | None = None
    with normalize_capture:
        normalized_plan = _normalize_expression_plan(
            payload=payload,
            max_expressions=max_expressions,
            min_expressions=0,
            source_message=source_message,
        )
    if normalize_capture.captured_exception is not None:
        return {
            "reasoning": "",
            "expressions": [],
        }
    if normalized_plan is None:
        raise RuntimeError("Expression-plan normalization did not return a plan")
    return normalized_plan


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
    elapsed_ms: float,
    iteration_index: int,
    executed_query_history: List[dict] | None,
    prior_evidence_notes: List[dict] | None,
    planner_feedback: List[str] | None,
) -> List[dict]:
    if executed_query_history is None:
        executed_query_history = []
    if prior_evidence_notes is None:
        prior_evidence_notes = []
    if planner_feedback is None:
        planner_feedback = []
    query_anchor_terms = _extract_planner_anchor_terms(
        source_message=user_message,
        max_terms=8,
    )
    question_lower = user_message.casefold()
    likely_structured_value = any(
        [
            "number" in question_lower,
            "date" in question_lower,
            "birth" in question_lower,
            "ssn" in question_lower,
            "identifier" in question_lower,
            " id" in (" " + question_lower),
            "phone" in question_lower,
            "account" in question_lower,
            "code" in question_lower,
        ]
    )
    likely_event_time_query = False
    if "when" in question_lower:
        likely_event_time_query = any(
            [
                "last" in question_lower,
                "most recent" in question_lower,
                "recently" in question_lower,
            ]
        )
    structured_hint_text = "no"
    if likely_structured_value:
        structured_hint_text = "yes"
    event_time_hint_text = "no"
    if likely_event_time_query:
        event_time_hint_text = "yes"
    system_prompt = "\n".join(
        [
            "You are a MetaList retrieval planner for one loop iteration.",
            "Pick the next text-search expressions to execute.",
            "",
            "Context:",
            "- User question: " + user_message,
            "- Notes are hierarchical; context_text includes ancestor + current note text.",
            "- Prior query history and prior evidence are provided below.",
            "- likely_structured_value: " + structured_hint_text,
            "- likely_event_time_query: " + event_time_hint_text,
            "",
            "What to do:",
            "- Return best-first queries for this iteration (most likely hit first).",
            "- Do not repeat anything already in executed_query_history.",
            "- Use the same language/script as the user question.",
            "",
            "Allowed expression types only: phrase, regex, near.",
            "How to choose expressions:",
            "- Start from the key words in the question.",
            "- Phrase queries should look like realistic note text chunks, not copied question wording.",
            "- Phrase queries must be short: 1-2 words only.",
            "- Avoid conversational framing words in phrases (for example: when, did, I, my, last) unless they are likely literal note text.",
            "- For multi-term intent, include one near expression early.",
            "- near supports simple alternatives with | (example: dad|father).",
            "- If likely_structured_value is yes, include a value-shape regex in the first 2 expressions.",
            "- For structured searches, combine nearby text intent with value-shape regexes (do both).",
            "- Keep regex practical for real notes (separator variants, spacing variants).",
            "- Example structured regex shape: \\b\\d{3}[- ]?\\d{2}[- ]?\\d{4}\\b for 3-2-4 numeric identifiers.",
            "- For event-time questions (for example: when did I last ...), do NOT use a broad standalone date-only regex as a first-pass query.",
            "- For event-time questions, tie date regex to person/activity terms, or prioritize person/activity expressions before date regex.",
            "- Avoid full-sentence phrase queries unless the user gave an exact quote.",
            "- Avoid unrelated expansions.",
            "",
            "Return ONLY JSON with exact shape:",
            '{"reasoning":"<1-3 sentences>","expressions":[{"type":"phrase","value":"..."},{"type":"regex","pattern":"...","flags":"ims"},{"type":"near","left":"...","right":"...","window_chars":200}]}',
            "Maximum expressions per iteration: " + str(max_expressions) + ".",
        ]
    )
    user_payload = {
        "question": user_message,
        "iteration_index": iteration_index,
        "elapsed_ms_so_far": elapsed_ms,
        "active_search_context_query": search_context_query,
        "query_anchor_terms": query_anchor_terms,
        "executed_query_history": executed_query_history,
        "prior_evidence_notes": prior_evidence_notes,
        "planner_feedback": planner_feedback,
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
    query_anchor_terms = _extract_planner_anchor_terms(
        source_message=user_message,
        max_terms=8,
    )
    system_prompt = "\n".join(
        [
            "You are repairing a MetaList retrieval plan that failed validation or was too weak.",
            "Keep valid high-signal expressions from the prior plan and improve coverage.",
            "",
            "Rules:",
            "- Use expression types only: phrase, regex, near.",
            "- Keep expressions ordered best-first (high signal first).",
            "- Prefer simple realistic queries over brittle patterns.",
            "- Use near when multi-term proximity is useful.",
            "- near supports simple alternatives with | in left/right.",
            "- Use the same language/script as the query.",
            "- Preserve the key words from the user query before broadening.",
            "- Phrase queries should look like realistic note text chunks, not copied question wording.",
            "- Phrase queries must be short: 1-2 words only.",
            "- Avoid conversational framing words in phrases (for example: when, did, I, my, last) unless they are likely literal note text.",
            "- For multi-term questions, put one combined expression first.",
            "- If question target is structured (date/phone/identifier/code), include a practical value-shape regex early.",
            "- Example structured regex shape: \\b\\d{3}[- ]?\\d{2}[- ]?\\d{4}\\b for 3-2-4 numeric identifiers.",
            "- For event-time questions, avoid broad standalone date-only regex in early repairs.",
            "- Avoid phrase-only repairs when structured value retrieval is likely.",
            "",
            "Output contract:",
            '- Return ONLY JSON with this exact shape: {"reasoning":"<1-3 sentences>","expressions":[{"type":"phrase","value":"..."},{"type":"regex","pattern":"...","flags":"ims"},{"type":"near","left":"...","right":"...","window_chars":200}]}.',
            "- Produce up to "
            + str(target_expressions)
            + " expressions for this pass (maximum "
            + str(max_expressions)
            + ").",
        ]
    )
    scoped_hint = ""
    if search_context_query.strip() != "":
        scoped_hint = search_context_query
    user_prompt_payload = {
        "user_question": user_message,
        "active_search_context_query": scoped_hint,
        "query_anchor_terms": query_anchor_terms,
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
    evidence_notes: List[dict] | None,
    hydrated_notes: List[dict] | None,
) -> List[dict]:
    if evidence_notes is None:
        evidence_notes = []
        if hydrated_notes is not None:
            evidence_notes = hydrated_notes
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
    expression_type = _mapping_value_or_none(mapping=expression, key="type")
    if not isinstance(expression_type, str):
        return "unknown"
    normalized_type = expression_type.casefold()
    if normalized_type == "phrase":
        value = _mapping_value_or_none(mapping=expression, key="value")
        if not isinstance(value, str):
            return "phrase:"
        return "phrase:" + value.casefold().strip()
    if normalized_type == "tag":
        value = _mapping_value_or_none(mapping=expression, key="value")
        if not isinstance(value, str):
            return "tag:"
        return "tag:" + value.casefold().strip()
    if normalized_type == "regex":
        pattern = _mapping_value_or_none(mapping=expression, key="pattern")
        flags = _mapping_value_or_none(mapping=expression, key="flags")
        if not isinstance(pattern, str):
            pattern = ""
        if not isinstance(flags, str):
            flags = ""
        return "regex:/" + pattern + "/" + flags
    if normalized_type == "near":
        left = _mapping_value_or_none(mapping=expression, key="left")
        right = _mapping_value_or_none(mapping=expression, key="right")
        window_chars = _mapping_value_or_none(mapping=expression, key="window_chars")
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
    if _mapping_value_or_none(mapping=tool_response, key="ok") is not True:
        return []
    data = _mapping_value_or_none(mapping=tool_response, key="data")
    if not isinstance(data, dict):
        return []
    results = _mapping_value_or_none(mapping=data, key="results")
    if not isinstance(results, list):
        return []

    ordered_results: List[dict] = []
    by_note_id: Dict[str, dict] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        note_id = _mapping_value_or_none(mapping=row, key="note_id")
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
        entry = _mapping_value_or_none(mapping=by_note_id, key=note_id)
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
        expression_payload = _mapping_value_or_none(mapping=row, key="expression")
        if isinstance(expression_payload, dict):
            clean_row["expression"] = expression_payload
        regex_samples = _mapping_value_or_none(mapping=row, key="regex_match_samples")
        if isinstance(regex_samples, list):
            clean_samples: List[dict] = []
            for sample in regex_samples[:8]:
                if not isinstance(sample, dict):
                    continue
                field = _mapping_value_or_none(mapping=sample, key="field")
                snippet = _mapping_value_or_none(mapping=sample, key="snippet")
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

    prepared: List[dict] = []
    for note in note_entries[:max_notes]:
        if not isinstance(note, dict):
            continue
        content_text = _mapping_value_or_none(mapping=note, key="content_text")
        if not isinstance(content_text, str):
            content_text = ""
        context_text = _ancestor_plus_content_context_text(entry=note)

        prepared_note: Dict[str, object] = {
            "snippet_excerpt": _clip_text_for_synthesis(
                text=context_text,
                max_chars=_SYNTHESIS_MAX_CONTEXT_EXCERPT_CHARS,
            ) if context_text != "" else "",
            "ancestor_context_included": context_text != "" and context_text != content_text,
        }
        if prepared_note["snippet_excerpt"] == "":
            prepared_note["snippet_excerpt"] = _clip_text_for_synthesis(
                text=content_text,
                max_chars=_SYNTHESIS_MAX_CONTENT_EXCERPT_CHARS,
            )
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
        entry = _mapping_value_or_none(mapping=note_evidence_by_id, key=note_id)
        if not isinstance(entry, dict):
            continue
        note_order_index = _mapping_value_or_none(mapping=entry, key="note_order_index")
        if not isinstance(note_order_index, int) or note_order_index < 0:
            note_order_index = 10**9
        sortable_rows.append((note_order_index, fallback_index, note_id))

    sortable_rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[2] for row in sortable_rows]


def _interleave_note_id_lists_round_robin(*, note_id_lists: List[List[str]]) -> List[str]:
    if not isinstance(note_id_lists, list):
        raise TypeError("note_id_lists must be a list")
    if len(note_id_lists) == 0:
        return []

    normalized_lists: List[List[str]] = []
    for note_ids in note_id_lists:
        if not isinstance(note_ids, list):
            raise TypeError("each note_id list must be a list")
        normalized: List[str] = []
        for note_id in note_ids:
            if not isinstance(note_id, str) or note_id == "":
                continue
            normalized.append(note_id)
        normalized_lists.append(normalized)

    cursors = [0 for _ in normalized_lists]
    seen = set()
    ordered: List[str] = []

    while True:
        progressed = False
        for list_index, note_ids in enumerate(normalized_lists):
            cursor = cursors[list_index]
            while cursor < len(note_ids):
                candidate_note_id = note_ids[cursor]
                cursor += 1
                if candidate_note_id in seen:
                    continue
                seen.add(candidate_note_id)
                ordered.append(candidate_note_id)
                progressed = True
                break
            cursors[list_index] = cursor
        if not progressed:
            break

    return ordered


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
        if not isinstance(note_id, str) or note_id == "":
            continue
        entry = _mapping_value_or_none(mapping=note_evidence_by_id, key=note_id)
        if not isinstance(entry, dict):
            continue
        preview_text = _mapping_value_or_none(mapping=entry, key="preview_text")
        context_text = _mapping_value_or_none(mapping=entry, key="context_text")
        if not isinstance(preview_text, str):
            preview_text = ""
        if not isinstance(context_text, str):
            context_text = ""
        hit_count = _mapping_value_or_none(mapping=note_hit_counts, key=note_id)
        if not isinstance(hit_count, int):
            hit_count = 0
        matched_expressions = _mapping_value_or_none(mapping=note_hit_expressions, key=note_id)
        if not isinstance(matched_expressions, list):
            matched_expressions = []
        preview_source = context_text
        if preview_text != "":
            preview_source = preview_text
        sample.append(
            {
                "hit_count": hit_count,
                "matched_expression_count": len(matched_expressions),
                "preview_excerpt": _clip_text_for_synthesis(
                    text=preview_source,
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
    evidence_overview: dict,
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
            "- If evidence_overview indicates non-zero evidence, prefer a tentative answer with low/medium confidence over empty uncertainty.",
            '- A tentative answer can be explicit uncertainty like "I think it is X, possibly Y".',
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
        "evidence_overview": evidence_overview,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _build_rewrite_relevance_filter_messages(
    *,
    user_message: str,
    search_context_query: str,
    elapsed_ms: float,
    iteration_index: int,
    executed_query_history: List[dict],
    iteration_query_results: List[dict],
    candidate_notes: List[dict],
    evidence_overview: dict,
) -> List[dict]:
    candidate_lines: List[str] = []
    for note in candidate_notes:
        if not isinstance(note, dict):
            continue
        snippet = _note_snippet_text(note=note)
        if snippet == "":
            continue
        candidate_lines.append("- " + snippet)

    query_summary_lines: List[str] = []
    for row in iteration_query_results:
        if not isinstance(row, dict):
            continue
        label = _mapping_value_or_none(mapping=row, key="expression_label")
        if not isinstance(label, str) or label.strip() == "":
            label = "query"
        scoped_match_count = _mapping_value_or_none(mapping=row, key="scoped_match_count")
        if not isinstance(scoped_match_count, int):
            scoped_match_count = 0
        execution_ms = _mapping_value_or_none(mapping=row, key="execution_ms")
        if not isinstance(execution_ms, (int, float)):
            execution_ms = 0.0
        query_summary_lines.append(
            f"- {label} (matches={scoped_match_count}, ms={round(float(execution_ms), 3)})"
        )

    context_query_display = "none"
    if search_context_query.strip() != "":
        context_query_display = search_context_query
    evidence_band = "none"
    if isinstance(evidence_overview, dict):
        band = _mapping_value_or_none(mapping=evidence_overview, key="band")
        if isinstance(band, str) and band.strip() != "":
            evidence_band = band

    prompt_lines: List[str] = [
        "You are the MetaList evidence relevance filter.",
        "Your task is ONLY to pick which candidate note contexts are relevant to the user question.",
        "Do NOT answer the user question yet.",
        "",
        "User question:",
        user_message,
        "",
        "Iteration context:",
        f"- iteration_index: {iteration_index}",
        f"- elapsed_ms_so_far: {elapsed_ms}",
        f"- active_search_context_query: {context_query_display}",
        f"- evidence_band: {evidence_band}",
        f"- prior_executed_query_count: {len(executed_query_history)}",
        "",
        "Executed queries this iteration:",
        *(query_summary_lines if len(query_summary_lines) > 0 else ["- none"]),
        "",
        "Candidate note contexts (one per note):",
        *(candidate_lines if len(candidate_lines) > 0 else ["- none"]),
        "",
        "Output format:",
        "- Return plain text only (not JSON).",
        "- Return only relevant contexts, one context per line.",
        "- Copy each selected context exactly from the candidate list when possible.",
        "- If nothing is relevant, return exactly: NONE",
    ]
    return [
        {"role": "system", "content": "\n".join(prompt_lines)},
    ]


def _clean_relevance_line(*, line: str) -> str:
    if not isinstance(line, str):
        raise TypeError("line must be a string")
    cleaned = line.strip()
    if cleaned == "":
        return ""
    cleaned = re.sub(r"^\s*[-*•]+\s*", "", cleaned)
    cleaned = re.sub(r"^\s*\d{1,2}[)\]:.\-]\s+", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _best_candidate_index_for_relevance_line(
    *,
    cleaned_line: str,
    candidate_norms: List[str],
) -> int | None:
    if cleaned_line == "":
        return None
    line_norm = cleaned_line.casefold()

    for idx, candidate_norm in enumerate(candidate_norms):
        if candidate_norm == line_norm:
            return idx
    if len(line_norm) >= 16:
        for idx, candidate_norm in enumerate(candidate_norms):
            if line_norm in candidate_norm or candidate_norm in line_norm:
                return idx

    best_idx: int | None = None
    best_ratio = 0.0
    for idx, candidate_norm in enumerate(candidate_norms):
        ratio = difflib.SequenceMatcher(a=line_norm, b=candidate_norm).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = idx
    if best_idx is not None and best_ratio >= 0.90:
        return best_idx
    return None


def _normalize_rewrite_relevance_filter(*, raw_model_output: str, notes: List[dict]) -> dict:
    if not isinstance(raw_model_output, str):
        raise TypeError("raw_model_output must be a string")
    if not isinstance(notes, list):
        raise TypeError("notes must be a list")

    candidate_snippets: List[str] = []
    candidate_norms: List[str] = []
    for note in notes:
        if not isinstance(note, dict):
            candidate_snippets.append("")
            candidate_norms.append("")
            continue
        snippet = _note_snippet_text(note=note)
        candidate_snippets.append(snippet)
        candidate_norms.append(snippet.casefold())

    text = raw_model_output.strip()
    if text == "":
        return {
            "reasoning": "Model returned empty relevance output.",
            "selected_relevant_snippets": [],
            "relevant_note_indexes": [],
        }

    selected_lines: List[str] = []
    for line in text.splitlines():
        cleaned = _clean_relevance_line(line=line)
        if cleaned == "":
            continue
        if cleaned.casefold() in {"none", "no relevant notes", "no relevant snippets"}:
            continue
        selected_lines.append(cleaned)

    selected_indexes: List[int] = []
    selected_snippets: List[str] = []
    seen_indexes = set()
    for line in selected_lines:
        matched_index = _best_candidate_index_for_relevance_line(
            cleaned_line=line,
            candidate_norms=candidate_norms,
        )
        if matched_index is None:
            continue
        index_1_based = matched_index + 1
        if index_1_based in seen_indexes:
            continue
        seen_indexes.add(index_1_based)
        selected_indexes.append(index_1_based)
        snippet = candidate_snippets[matched_index]
        if snippet != "":
            selected_snippets.append(snippet)

    reasoning = (
        "Selected "
        + str(len(selected_indexes))
        + " relevant snippets from model output."
    )
    return {
        "reasoning": reasoning,
        "selected_relevant_snippets": selected_snippets,
        "relevant_note_indexes": selected_indexes,
    }


def _select_notes_by_indexes(*, notes: List[dict], indexes: List[int]) -> List[dict]:
    if not isinstance(notes, list):
        raise TypeError("notes must be a list")
    if not isinstance(indexes, list):
        raise TypeError("indexes must be a list")
    selected: List[dict] = []
    for index in indexes:
        if not isinstance(index, int):
            continue
        if index < 1 or index > len(notes):
            continue
        note = notes[index - 1]
        if not isinstance(note, dict):
            continue
        selected.append(note)
    return selected


def _normalize_rewrite_iteration_decision(*, payload: object) -> dict:
    if not isinstance(payload, dict):
        payload = {}

    decision = _mapping_value_or_none(mapping=payload, key="decision")
    if not isinstance(decision, str) or decision.strip() == "":
        fallback_action = _mapping_value_or_none(mapping=payload, key="action")
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
        fallback_answer = _mapping_value_or_none(mapping=payload, key="answer")
        fallback_question = _mapping_value_or_none(mapping=payload, key="clarifying_question")
        fallback_continue_reason = _mapping_value_or_none(mapping=payload, key="continue_reason")
        if isinstance(fallback_answer, str) and fallback_answer.strip() != "":
            decision = "answer"
        elif isinstance(fallback_question, str) and fallback_question.strip() != "":
            decision = "clarify"
        elif isinstance(fallback_continue_reason, str) and fallback_continue_reason.strip() != "":
            decision = "continue"
        else:
            decision = "uncertain"
    normalized_decision = str(decision).casefold().strip()

    reasoning = _mapping_value_or_none(mapping=payload, key="reasoning")
    if not isinstance(reasoning, str):
        reasoning = ""
    normalized_reasoning = reasoning.strip()

    confidence = _mapping_value_or_none(mapping=payload, key="confidence")
    if not isinstance(confidence, str):
        confidence = "medium"
    normalized_confidence = confidence.casefold().strip()
    if normalized_confidence not in {"high", "medium", "low"}:
        normalized_confidence = "medium"

    answer = _mapping_value_or_none(mapping=payload, key="answer")
    if not isinstance(answer, str):
        answer = ""
    normalized_answer = answer.strip()

    clarifying_question = _mapping_value_or_none(mapping=payload, key="clarifying_question")
    if not isinstance(clarifying_question, str):
        clarifying_question = ""
    normalized_clarifying_question = clarifying_question.strip()

    continue_reason = _mapping_value_or_none(mapping=payload, key="continue_reason")
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
                candidate = _mapping_value_or_none(mapping=value, key=key)
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
    expression_type = _mapping_value_or_none(mapping=expression, key="type")
    if not isinstance(expression_type, str):
        expression_type = ""

    base_weight = 1.0
    if expression_type == "regex":
        base_weight = 3.0
    elif expression_type == "phrase":
        value = _mapping_value_or_none(mapping=expression, key="value")
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
        label = _mapping_value_or_none(mapping=row, key="expression_label")
        if not isinstance(label, str) or label == "":
            continue
        expression = _mapping_value_or_none(mapping=row, key="expression")
        if not isinstance(expression, dict):
            continue
        scoped_match_count = _mapping_value_or_none(mapping=row, key="scoped_match_count")
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
        if not isinstance(note_id, str) or note_id == "":
            continue
        first_seen_rank[note_id] = index
        hit_count = _mapping_value_or_none(mapping=note_hit_counts, key=note_id)
        if not isinstance(hit_count, int):
            hit_count = 0
        labels = _mapping_value_or_none(mapping=note_hit_expressions, key=note_id)
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
            expression_weight = _mapping_value_or_none(mapping=expression_weight_by_label, key=label)
            if not isinstance(expression_weight, (int, float)):
                expression_weight = 0.0
            score += float(expression_weight)
        score += float(hit_count) * 0.05
        note_universe_rank = _mapping_value_or_none(mapping=universe_rank, key=note_id)
        if not isinstance(note_universe_rank, int):
            note_universe_rank = 10**9
        ranked_rows.append(
            {
                "note_id": note_id,
                "score": round(score, 6),
                "hit_count": hit_count,
                "matched_expression_count": len(seen_labels),
                "matched_expressions": list(seen_labels),
                "first_seen_rank": index,
                "universe_rank": note_universe_rank,
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
        note_id = _mapping_value_or_none(mapping=note, key="note_id")
        if not isinstance(note_id, str) or note_id == "":
            continue
        content_text = _mapping_value_or_none(mapping=note, key="content_text")
        if not isinstance(content_text, str):
            content_text = ""
        context_text = _mapping_value_or_none(mapping=note, key="context_text")
        if not isinstance(context_text, str):
            context_text = ""
        source_text = content_text
        if context_text != "":
            source_text = context_text
        hit_count = _mapping_value_or_none(mapping=note, key="hit_count")
        matched_expressions = _mapping_value_or_none(mapping=note, key="matched_expressions")
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
                "hit_count": hit_count,
                "matched_expressions": matched_expressions,
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
    status_callback: Callable[[str], None] | None,
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
    universe_mode = "global"
    if search_context_query.strip() != "":
        universe_mode = "scoped"
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
        universe_ok = _mapping_value_or_none(mapping=universe_tool_response, key="ok")
        if universe_ok is not True:
            error = _mapping_value_or_none(mapping=universe_tool_response, key="error")
            if not isinstance(error, str) or error.strip() == "":
                error = "Universe resolution failed"
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
        count_ok = _mapping_value_or_none(mapping=count_tool_response, key="ok")
        if count_ok is not True:
            error = _mapping_value_or_none(mapping=count_tool_response, key="error")
            if not isinstance(error, str) or error.strip() == "":
                error = "Universe resolution failed"
            return {
                "ok": False,
                "answer": str(error),
                "model": resolved_model,
                "steps": steps,
                "mode": "rewrite",
                "total_execution_ms": _total_execution_ms(),
            }
        count_data = _mapping_dict_or_none(mapping=count_tool_response, key="data")
        if count_data is None:
            raise TypeError("count_notes data must be an object")
        total_notes = _mapping_value_or_none(mapping=count_data, key="total_notes")
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
        "evidence_selection_strategy": "query_round_robin_interleaved",
        "carried_evidence_max_notes": hydrate_top_k,
        "latest_result_evidence_max_notes": hydrate_top_k,
        "decision_stage_enabled": False,
        "relevance_filter_stage_enabled": True,
    }

    note_hit_counts: Dict[str, int] = {}
    note_hit_expressions: Dict[str, List[str]] = {}
    note_evidence_by_id: Dict[str, dict] = {}
    expression_stats: List[dict] = []
    executed_query_history: List[dict] = []
    executed_query_signatures = set()
    planner_feedback_messages: List[str] = []

    def merge_scoped_entries(*, entries: List[dict], expression_label: str) -> List[str]:
        latest_note_ids: List[str] = []
        for entry in entries:
            note_id = _mapping_value_or_none(mapping=entry, key="note_id")
            if not isinstance(note_id, str) or note_id == "":
                continue
            latest_note_ids.append(note_id)

            note_hit_count = 0
            if note_id in note_hit_counts:
                note_hit_count = note_hit_counts[note_id]
            note_hit_counts[note_id] = note_hit_count + 1

            matched_expression_list: List[str] | None = None
            if note_id in note_hit_expressions:
                matched_expression_list = note_hit_expressions[note_id]
            if matched_expression_list is None:
                matched_expression_list = []
                note_hit_expressions[note_id] = matched_expression_list
            if expression_label not in matched_expression_list:
                matched_expression_list.append(expression_label)

            existing_evidence: dict | None = None
            if note_id in note_evidence_by_id:
                existing_evidence = note_evidence_by_id[note_id]
            entry_context_no_descendants = _ancestor_plus_content_context_text(entry=entry)
            if existing_evidence is None:
                note_order_index = _mapping_value_or_none(mapping=entry, key="note_order_index")
                if not isinstance(note_order_index, int) or note_order_index < 0:
                    note_order_index = 10**9
                preview_text = _mapping_value_or_none(mapping=entry, key="preview_text")
                if not isinstance(preview_text, str):
                    preview_text = ""
                content_text = _mapping_value_or_none(mapping=entry, key="content_text")
                if not isinstance(content_text, str):
                    content_text = ""
                ancestor_texts = _mapping_list_or_empty(mapping=entry, key="ancestor_texts")
                tag_terms = _mapping_list_or_empty(mapping=entry, key="tag_terms")
                effective_tag_terms = _mapping_list_or_empty(
                    mapping=entry,
                    key="effective_tag_terms",
                )
                existing_evidence = {
                    "preview_text": preview_text,
                    "content_text": content_text,
                    "context_text": entry_context_no_descendants,
                    "ancestor_texts": ancestor_texts,
                    "tag_terms": tag_terms,
                    "effective_tag_terms": effective_tag_terms,
                    "matches": [],
                    "matched_expressions": [],
                    "hit_count": 0,
                    "note_order_index": note_order_index,
                }
                note_evidence_by_id[note_id] = existing_evidence
            else:
                existing_order_index = _mapping_value_or_none(
                    mapping=existing_evidence,
                    key="note_order_index",
                )
                candidate_order_index = _mapping_value_or_none(
                    mapping=entry,
                    key="note_order_index",
                )
                if not isinstance(existing_order_index, int):
                    existing_order_index = 10**9
                if not isinstance(candidate_order_index, int):
                    candidate_order_index = 10**9
                existing_evidence["note_order_index"] = min(
                    existing_order_index,
                    candidate_order_index,
                )

            existing_context_text = _mapping_value_or_none(mapping=existing_evidence, key="context_text")
            if (
                isinstance(existing_context_text, str)
                and isinstance(entry_context_no_descendants, str)
                and len(entry_context_no_descendants) > len(existing_evidence["context_text"])
            ):
                existing_evidence["context_text"] = entry_context_no_descendants
            existing_content_text = _mapping_value_or_none(mapping=existing_evidence, key="content_text")
            entry_content_text = _mapping_value_or_none(mapping=entry, key="content_text")
            if (
                isinstance(existing_content_text, str)
                and isinstance(entry_content_text, str)
                and len(entry["content_text"]) > len(existing_evidence["content_text"])
            ):
                existing_evidence["content_text"] = entry["content_text"]
            existing_preview_text = _mapping_value_or_none(mapping=existing_evidence, key="preview_text")
            entry_preview_text = _mapping_value_or_none(mapping=entry, key="preview_text")
            if (
                isinstance(existing_preview_text, str)
                and isinstance(entry_preview_text, str)
                and len(entry["preview_text"]) > len(existing_evidence["preview_text"])
            ):
                existing_evidence["preview_text"] = entry["preview_text"]
            entry_tag_terms = _mapping_value_or_none(mapping=entry, key="tag_terms")
            if isinstance(entry_tag_terms, list):
                existing_evidence["tag_terms"] = entry["tag_terms"]
            entry_effective_tag_terms = _mapping_value_or_none(
                mapping=entry,
                key="effective_tag_terms",
            )
            if isinstance(entry_effective_tag_terms, list):
                existing_evidence["effective_tag_terms"] = entry["effective_tag_terms"]
            entry_ancestor_texts = _mapping_value_or_none(mapping=entry, key="ancestor_texts")
            if isinstance(entry_ancestor_texts, list):
                existing_evidence["ancestor_texts"] = entry["ancestor_texts"]
            existing_matches = _mapping_value_or_none(mapping=existing_evidence, key="matches")
            if not isinstance(existing_matches, list):
                existing_matches = []
                existing_evidence["matches"] = existing_matches
            entry_matches = _mapping_value_or_none(mapping=entry, key="matches")
            if isinstance(entry_matches, list):
                for match in entry_matches:
                    if not isinstance(match, dict):
                        continue
                    snippet = _mapping_value_or_none(mapping=match, key="snippet")
                    field = _mapping_value_or_none(mapping=match, key="field")
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
            existing_matched_expressions = _mapping_value_or_none(
                mapping=existing_evidence,
                key="matched_expressions",
            )
            if not isinstance(existing_matched_expressions, list):
                existing_matched_expressions = []
                existing_evidence["matched_expressions"] = existing_matched_expressions
            if expression_label not in existing_matched_expressions:
                existing_matched_expressions.append(expression_label)
            hit_count = 0
            if note_id in note_hit_counts:
                hit_count = note_hit_counts[note_id]
            existing_evidence["hit_count"] = hit_count
        return latest_note_ids

    for iteration_index in range(1, max_steps + 1):
        _emit_status(detail=f"Iteration {iteration_index}: planning queries...")
        ranking_universe_ids: List[str] | None
        if universe_mode == "scoped":
            ranking_universe_ids = []
            if universe_note_ids is not None:
                ranking_universe_ids = universe_note_ids
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
            evidence_entry = None
            if note_id in note_evidence_by_id:
                evidence_entry = note_evidence_by_id[note_id]
            if evidence_entry is None:
                continue
            carried_entries.append(evidence_entry)
        carried_evidence_notes = _prepare_model_evidence_notes(
            note_entries=carried_entries,
            user_message=user_message,
            max_notes=hydrate_top_k,
        )

        plan_messages = _build_rewrite_expression_plan_messages(
            user_message=user_message,
            search_context_query=search_context_query,
            max_expressions=max_expressions,
            elapsed_ms=_total_execution_ms(),
            iteration_index=iteration_index,
            executed_query_history=executed_query_history[-32:],
            prior_evidence_notes=carried_evidence_notes,
            planner_feedback=planner_feedback_messages[-16:],
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
                    "skipped_invalid_expression_count": 0,
                    "skipped_unexecutable_query_count": 0,
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
                        "invalid_expressions_skipped": [],
                        "unexecutable_queries_skipped": [],
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
        planner_capture = _CapturedExceptionContext(ValueError)
        expression_plan: dict | None = None
        with planner_capture:
            expression_plan = _normalize_expression_plan(
                payload=planned_payload,
                max_expressions=max_expressions,
                min_expressions=0,
                source_message=user_message,
            )
        if planner_capture.captured_exception is not None:
            planner_validation_error = str(planner_capture.captured_exception)
            planner_feedback_messages.append(
                "Planner normalization warning: " + planner_validation_error
            )
            expression_plan = {
                "reasoning": "Planner output was partially invalid; continuing with usable subset for this iteration.",
                "expressions": plan_preview["expressions"],
            }
        elif expression_plan is None:
            raise RuntimeError("Planner normalization did not return a plan")

        expression_items: List[dict] = []
        skipped_invalid_expressions: List[dict] = []
        for expression_index, expression in enumerate(expression_plan["expressions"], start=1):
            if expression_index > max_expressions:
                break
            if not isinstance(expression, dict):
                skipped_invalid_expressions.append(
                    {
                        "original_index": expression_index,
                        "error": "expression entry must be an object",
                        "expression": expression,
                    }
                )
                planner_feedback_messages.append(
                    "Skipped invalid expression at index "
                    + str(expression_index)
                    + ": expected object."
                )
                continue
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
        iteration_query_note_id_lists: List[List[str]] = []
        skipped_duplicate_queries: List[dict] = []
        skipped_unexecutable_queries: List[dict] = []
        iteration_latest_note_ids: List[str] = []
        iteration_seen_note_ids = set()

        for item in expression_items:
            expression = item["expression"]
            compile_capture = _CapturedExceptionContext(TypeError, ValueError)
            compiled: dict | None = None
            with compile_capture:
                compiled = _compile_rewrite_expression_call(
                    expression=expression,
                    per_expression_limit=per_expression_limit,
                    normalized_regex_engine=normalized_regex_engine,
                    universe_note_ids=universe_note_ids,
                )
            if compile_capture.captured_exception is not None:
                error = compile_capture.captured_exception
                skipped_unexecutable_queries.append(
                    {
                        "expression": expression,
                        "error": str(error),
                    }
                )
                planner_feedback_messages.append(
                    "Skipped unexecutable expression: " + str(error)
                )
                continue
            if compiled is None:
                raise RuntimeError("Expression compilation did not return a tool call")
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
            tool_ok = _mapping_value_or_none(mapping=tool_response, key="ok")
            tool_error = _mapping_value_or_none(mapping=tool_response, key="error")
            if not isinstance(tool_error, str) or tool_error.strip() == "":
                tool_error = f"{tool_name} failed"
            if tool_ok is not True:
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
                            "skipped_invalid_expression_count": len(skipped_invalid_expressions),
                            "skipped_unexecutable_query_count": len(skipped_unexecutable_queries),
                            "iteration_result_count": len(iteration_latest_note_ids),
                            "decision": "error",
                        },
                        "model_payload": {
                            "planner_prompt_messages": plan_messages,
                            "planner_raw_model_output": planner_raw_output,
                            "planner_reasoning": expression_plan["reasoning"],
                            "planned_expressions": expression_plan["expressions"],
                        },
                        "tool_response": {
                            "ok": False,
                            "error": str(tool_error),
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
                                "invalid_expressions_skipped": skipped_invalid_expressions,
                                "unexecutable_queries_skipped": skipped_unexecutable_queries,
                                "latest_result_notes": [],
                                "carried_evidence_notes": carried_evidence_notes,
                            },
                        },
                    }
                )
                return {
                    "ok": False,
                    "answer": str(tool_error),
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
            iteration_query_note_id_lists.append(latest_note_ids)
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
                    "tool_response": _compact_tool_response_for_iteration(
                        tool_response=tool_response,
                        max_results=hydrate_top_k,
                    ),
                }
            )

        _emit_status(
            detail=(
                f"Iteration {iteration_index}: executed "
                + str(len(iteration_query_runs))
                + " queries; running relevance filter..."
            )
        )

        interleaved_iteration_note_ids = _interleave_note_id_lists_round_robin(
            note_id_lists=iteration_query_note_id_lists
        )
        latest_entries: List[dict] = []
        for note_id in interleaved_iteration_note_ids:
            evidence_entry = None
            if note_id in note_evidence_by_id:
                evidence_entry = note_evidence_by_id[note_id]
            if evidence_entry is None:
                continue
            latest_entries.append(evidence_entry)
        latest_result_notes = _prepare_model_evidence_notes(
            note_entries=latest_entries,
            user_message=user_message,
            max_notes=hydrate_top_k,
        )
        matched_query_count = sum(1 for row in iteration_query_runs if row["scoped_match_count"] > 0)
        total_scoped_matches = sum(int(row["scoped_match_count"]) for row in iteration_query_runs)
        candidate_note_count = len(latest_result_notes)
        evidence_band = "none"
        if candidate_note_count > 0:
            if candidate_note_count <= 4:
                evidence_band = "narrow"
            elif candidate_note_count <= 25:
                evidence_band = "medium"
            else:
                evidence_band = "broad"
        evidence_overview = {
            "band": evidence_band,
            "candidate_note_count": candidate_note_count,
            "executed_query_count": len(iteration_query_runs),
            "queries_with_matches": matched_query_count,
            "total_scoped_matches": total_scoped_matches,
        }

        query_results_for_prompt = [
            {
                "expression_label": row["expression_label"],
                "execution_ms": row["execution_ms"],
                "scoped_match_count": row["scoped_match_count"],
            }
            for row in iteration_query_runs
        ]

        relevance_messages = _build_rewrite_relevance_filter_messages(
            user_message=user_message,
            search_context_query=search_context_query,
            elapsed_ms=_total_execution_ms(),
            iteration_index=iteration_index,
            executed_query_history=executed_query_history[-32:],
            iteration_query_results=query_results_for_prompt,
            candidate_notes=latest_result_notes,
            evidence_overview=evidence_overview,
        )
        append_step(
            step_record={
                "step": len(steps) + 1,
                "action": "loop_iteration",
                "reason": "planner output accepted; queries executed; waiting for relevance filter model",
                "stats": {
                    "iteration_index": iteration_index,
                    "phase": "relevance_prompt",
                    "planning_ms": planning_ms,
                    "decision_ms": 0.0,
                    "elapsed_ms_so_far": _total_execution_ms(),
                    "planned_expression_count": len(expression_plan["expressions"]),
                    "executed_query_count": len(iteration_query_runs),
                    "skipped_duplicate_query_count": len(skipped_duplicate_queries),
                    "skipped_invalid_expression_count": len(skipped_invalid_expressions),
                    "skipped_unexecutable_query_count": len(skipped_unexecutable_queries),
                    "iteration_result_count": len(iteration_latest_note_ids),
                    "decision": "pending",
                },
                "model_payload": {
                    "planner_prompt_messages": plan_messages,
                    "planner_raw_model_output": planner_raw_output,
                    "planner_reasoning": expression_plan["reasoning"],
                    "planned_expressions": expression_plan["expressions"],
                    "planner_validation_error": planner_validation_error,
                    "relevance_prompt_messages": relevance_messages,
                },
                "tool_response": {
                    "ok": True,
                    "data": {
                        "iteration_index": iteration_index,
                        "queries_executed": iteration_query_runs,
                        "duplicate_queries_skipped": skipped_duplicate_queries,
                        "invalid_expressions_skipped": skipped_invalid_expressions,
                        "unexecutable_queries_skipped": skipped_unexecutable_queries,
                        "latest_result_notes": latest_result_notes,
                        "carried_evidence_notes": carried_evidence_notes,
                        "evidence_overview": evidence_overview,
                        "latest_result_selection_order": "query_round_robin_interleaved",
                        "latest_result_note_count_before_limit": len(interleaved_iteration_note_ids),
                        "latest_result_limit": hydrate_top_k,
                    },
                },
            }
        )
        relevance_start = time.perf_counter()
        _emit_status(detail=f"Iteration {iteration_index}: waiting for relevance filter model...")
        relevance_raw = _ollama_chat_text(
            ollama_chat_url=ollama_chat_url,
            model=resolved_model,
            messages=relevance_messages,
            num_ctx=None,
        )
        relevance_ms = round((time.perf_counter() - relevance_start) * 1000, 3)
        relevance_result = _normalize_rewrite_relevance_filter(
            raw_model_output=relevance_raw,
            notes=latest_result_notes,
        )
        relevant_notes = _select_notes_by_indexes(
            notes=latest_result_notes,
            indexes=relevance_result["relevant_note_indexes"],
        )

        append_step(
            step_record={
                "step": len(steps) + 1,
                "action": "evidence_relevance_filter",
                "reason": "model selected relevant evidence snippets before any final answer",
                "stats": {
                    "iteration_index": iteration_index,
                    "planning_ms": planning_ms,
                    "relevance_ms": relevance_ms,
                    "elapsed_ms_so_far": _total_execution_ms(),
                    "candidate_note_count": len(latest_result_notes),
                    "relevant_note_count": len(relevant_notes),
                    "selected_snippet_count": len(relevance_result["selected_relevant_snippets"]),
                },
                "model_payload": {
                    "prompt_messages": relevance_messages,
                    "raw_model_output": relevance_raw,
                },
                "tool_response": {
                    "ok": True,
                    "data": {
                        "iteration_index": iteration_index,
                        "reasoning": relevance_result["reasoning"],
                        "selected_relevant_snippets": relevance_result["selected_relevant_snippets"],
                        "relevant_note_indexes": relevance_result["relevant_note_indexes"],
                        "candidate_notes": latest_result_notes,
                        "relevant_notes": relevant_notes,
                        "queries_executed": iteration_query_runs,
                        "evidence_overview": evidence_overview,
                        "latest_result_selection_order": "query_round_robin_interleaved",
                        "latest_result_note_count_before_limit": len(interleaved_iteration_note_ids),
                        "latest_result_limit": hydrate_top_k,
                    },
                },
            }
        )

        return {
            "ok": True,
            "answer": (
                "Relevance filtering complete. Relevant notes: "
                + str(len(relevant_notes))
                + " / "
                + str(len(latest_result_notes))
                + "."
            ),
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
    planner_seed_tag_limit: int,
    planner_tag_count_mode: str,
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
    query_hypothesis_capture = _CapturedExceptionContext(ValueError)
    query_hypothesis: dict | None = None
    with query_hypothesis_capture:
        query_hypothesis = _normalize_query_hypothesis(
            payload=query_hypothesis_payload,
        )
    if query_hypothesis_capture.captured_exception is not None:
        planner_error_text = str(query_hypothesis_capture.captured_exception)
        query_hypothesis = {
            "reasoning": "Planner output was invalid, so using heuristic tags from the question tokens.",
            "hypothesized_tags": _build_tag_discovery_terms(user_message=user_message),
        }
    elif query_hypothesis is None:
        raise RuntimeError("Query-hypothesis normalization did not return a payload")
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
            seed_tag = _mapping_value_or_none(mapping=seed_entry, key="tag")
            if not isinstance(seed_tag, str) or seed_tag == "":
                continue
            seed_key = _normalize_tag_term(value=seed_tag)
            if seed_key == "":
                continue
            seed_tag_keys.add(seed_key)

        exact_matches_from_seed: List[str] = []
        exact_matches_not_from_seed: List[str] = []
        exact_matches = _mapping_value_or_none(mapping=tag_match_data, key="exact_matches")
        if isinstance(exact_matches, list):
            for match_entry in exact_matches:
                if not isinstance(match_entry, dict):
                    continue
                catalog_tag = _mapping_value_or_none(mapping=match_entry, key="catalog_tag")
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
        parsed_list_tags_data = _mapping_dict_or_none(mapping=parsed_list_tags, key="data")
        total_matches = None
        returned_count = None
        if parsed_list_tags_data is not None:
            total_matches = _mapping_value_or_none(mapping=parsed_list_tags_data, key="total_matches")
            returned_count = _mapping_value_or_none(mapping=parsed_list_tags_data, key="returned_count")
        tag_match_data["catalog_fetch"] = {
            "mode": planner_tag_count_mode,
            "limit": list_tags_args["limit"],
            "total_matches": total_matches,
            "returned_count": returned_count,
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


class AgentChatV2HistoryMessage(BaseModel):
    role: str
    content: str


class AgentChatV2Request(BaseModel):
    message: str
    conversation_history: List[AgentChatV2HistoryMessage]
    model: str
    context_window_max_chars: int
    num_ctx: int
    include_tags_in_context_window: bool
    mcp_url: str
    ollama_chat_url: str


def _validate_v2_conversation_history(
    *,
    entries: List[AgentChatV2HistoryMessage],
) -> List[dict]:
    normalized: List[dict] = []
    for index, entry in enumerate(entries, start=1):
        role_value = entry.role.strip().casefold()
        if role_value not in {"user", "assistant"}:
            raise ValueError(
                f"conversation_history[{index}] role must be user or assistant"
            )
        content_value = entry.content.strip()
        if content_value == "":
            raise ValueError(f"conversation_history[{index}] content must not be empty")
        normalized.append(
            {
                "role": role_value,
                "content": content_value,
            }
        )
    return normalized


def _build_v2_system_prompt(*, include_tags_in_context_window: bool) -> str:
    tags_line = "Tag lines are omitted in this run to save context space. "
    if include_tags_in_context_window:
        tags_line = "Tag lines start with '# ' and represent direct raw tags only. "
    return (
        "You are the MetaList assistant. "
        "You must answer using only the provided context window and conversation history. "
        "The context window is plain text from notes with hierarchy shown by indentation. "
        + tags_line
        + "For this prompt, items lower in the context window should be treated as more important than items above them. "
        "Do not claim you lack access to notes when relevant evidence is present in context. "
        "If evidence is ambiguous or insufficient, say what is missing and ask one clarifying question or suggest narrowing search scope. "
        "Keep answers concise and practical."
    )


def _build_v2_note_block(
    *,
    note: dict,
    order_index: int,
    include_tags_in_context_window: bool,
) -> dict | None:
    if not isinstance(note, dict):
        return None

    note_id_value = _mapping_value_or_none(mapping=note, key="note_id")
    note_id: str | None = None
    if isinstance(note_id_value, str) and note_id_value != "":
        note_id = note_id_value

    ancestor_texts: List[str] = []
    ancestor_texts_raw = _mapping_value_or_none(mapping=note, key="ancestor_texts")
    if isinstance(ancestor_texts_raw, list):
        for ancestor_text in ancestor_texts_raw:
            if not isinstance(ancestor_text, str):
                ancestor_texts.append("")
                continue
            normalized_ancestor = re.sub(r"\s+", " ", ancestor_text).strip()
            ancestor_texts.append(normalized_ancestor)

    ancestor_raw_tags: List[str] = []
    if include_tags_in_context_window:
        ancestor_raw_tags_raw = _mapping_value_or_none(mapping=note, key="ancestor_raw_tag_strings")
        if isinstance(ancestor_raw_tags_raw, list):
            for ancestor_tag in ancestor_raw_tags_raw:
                if not isinstance(ancestor_tag, str):
                    ancestor_raw_tags.append("")
                    continue
                normalized_tag = re.sub(r"\s+", " ", ancestor_tag).strip()
                ancestor_raw_tags.append(normalized_tag)

    content_raw = _mapping_value_or_none(mapping=note, key="content_text")
    if not isinstance(content_raw, str):
        content_raw = ""
    content_text = _strip_html_to_text(text=content_raw)
    content_text = re.sub(r"\s+", " ", content_text).strip()

    descendant_texts: List[str] = []
    descendant_texts_raw = _mapping_value_or_none(mapping=note, key="descendant_texts")
    if isinstance(descendant_texts_raw, list):
        for descendant_text in descendant_texts_raw:
            if not isinstance(descendant_text, str):
                descendant_texts.append("")
                continue
            normalized_descendant = re.sub(r"\s+", " ", descendant_text).strip()
            descendant_texts.append(normalized_descendant)

    descendant_raw_tags: List[str] = []
    if include_tags_in_context_window:
        descendant_raw_tags_raw = _mapping_value_or_none(mapping=note, key="descendant_raw_tag_strings")
        if isinstance(descendant_raw_tags_raw, list):
            for descendant_tag in descendant_raw_tags_raw:
                if not isinstance(descendant_tag, str):
                    descendant_raw_tags.append("")
                    continue
                normalized_tag = re.sub(r"\s+", " ", descendant_tag).strip()
                descendant_raw_tags.append(normalized_tag)

    descendant_relative_depths: List[int] = []
    descendant_relative_depths_raw = _mapping_value_or_none(mapping=note, key="descendant_relative_depths")
    if isinstance(descendant_relative_depths_raw, list):
        for relative_depth in descendant_relative_depths_raw:
            if not isinstance(relative_depth, int) or relative_depth < 1:
                descendant_relative_depths.append(1)
                continue
            descendant_relative_depths.append(relative_depth)

    raw_tag_string = ""
    if include_tags_in_context_window:
        raw_tag_value = _mapping_value_or_none(mapping=note, key="raw_tag_string")
        if isinstance(raw_tag_value, str):
            raw_tag_string = re.sub(r"\s+", " ", raw_tag_value).strip()

    covered_note_ids: List[str] = []
    if note_id is not None:
        covered_note_ids.append(note_id)
    descendant_note_ids_raw = _mapping_value_or_none(mapping=note, key="descendant_note_ids")
    if isinstance(descendant_note_ids_raw, list):
        seen_covered = set(covered_note_ids)
        for descendant_note_id in descendant_note_ids_raw:
            if not isinstance(descendant_note_id, str) or descendant_note_id == "":
                continue
            if descendant_note_id in seen_covered:
                continue
            seen_covered.add(descendant_note_id)
            covered_note_ids.append(descendant_note_id)

    ancestor_note_ids = _mapping_value_or_none(mapping=note, key="ancestor_note_ids")
    depth = 0
    if isinstance(ancestor_note_ids, list):
        for ancestor_note_id in ancestor_note_ids:
            if isinstance(ancestor_note_id, str) and ancestor_note_id != "":
                depth += 1

    lines: List[str] = []
    ancestor_item_count = max(len(ancestor_texts), len(ancestor_raw_tags))
    for ancestor_index in range(ancestor_item_count):
        ancestor_text = ""
        if ancestor_index < len(ancestor_texts):
            ancestor_text = ancestor_texts[ancestor_index]
        ancestor_tag = ""
        if ancestor_index < len(ancestor_raw_tags):
            ancestor_tag = ancestor_raw_tags[ancestor_index]
        ancestor_indent = "    " * ancestor_index
        if ancestor_text != "":
            lines.append(ancestor_indent + ancestor_text)
        if ancestor_tag != "":
            lines.append(ancestor_indent + "# " + ancestor_tag)

    indent = "    " * depth
    if content_text != "":
        lines.append(indent + content_text)
    if raw_tag_string != "":
        lines.append(indent + "# " + raw_tag_string)

    descendant_item_count = max(
        len(descendant_texts),
        len(descendant_raw_tags),
        len(descendant_relative_depths),
    )
    for descendant_index in range(descendant_item_count):
        descendant_text = ""
        if descendant_index < len(descendant_texts):
            descendant_text = descendant_texts[descendant_index]
        descendant_tag = ""
        if descendant_index < len(descendant_raw_tags):
            descendant_tag = descendant_raw_tags[descendant_index]
        relative_depth = 1
        if descendant_index < len(descendant_relative_depths):
            relative_depth = descendant_relative_depths[descendant_index]
        descendant_indent = "    " * (depth + relative_depth)
        if descendant_text != "":
            lines.append(descendant_indent + descendant_text)
        if descendant_tag != "":
            lines.append(descendant_indent + "# " + descendant_tag)

    if len(lines) == 0:
        return None

    block_text = "\n".join(lines) + "\n\n"
    return {
        "block_text": block_text,
        "note": {
            "note_id": note_id,
            "order_index": order_index,
            "depth": depth,
            "ancestor_count": len(ancestor_texts),
            "descendant_count": len(descendant_texts),
            "content_text": content_text,
            "raw_tags": raw_tag_string,
            "covered_note_ids": covered_note_ids,
        },
    }


def _build_v2_context_window(
    *,
    mcp_url: str,
    context_window_max_chars: int,
    include_tags_in_context_window: bool,
    request_id: int,
) -> dict:
    if context_window_max_chars <= 0:
        raise ValueError("context_window_max_chars must be > 0")

    context_resolution_started_at = time.perf_counter()
    context_call = _tools_call(
        url=mcp_url,
        request_id=request_id,
        tool_name="get_active_search_context",
        arguments={},
    )
    context_resolution_ms = round(
        (time.perf_counter() - context_resolution_started_at) * 1000,
        3,
    )
    context_tool_response = _extract_tool_response(call_response=context_call)
    context_ok = _mapping_value_or_none(mapping=context_tool_response, key="ok")
    if context_ok is not True:
        error = _mapping_value_or_none(mapping=context_tool_response, key="error")
        if not isinstance(error, str) or error.strip() == "":
            error = "get_active_search_context failed"
        raise RuntimeError(str(error))

    context_data = _mapping_dict_or_none(mapping=context_tool_response, key="data")
    if context_data is None:
        raise TypeError("get_active_search_context data must be an object")

    active_search_context_query = _mapping_value_or_none(mapping=context_data, key="search_query")
    if not isinstance(active_search_context_query, str):
        raise TypeError("get_active_search_context search_query must be a string")
    active_tab_id = _mapping_value_or_none(mapping=context_data, key="active_tab_id")
    if not isinstance(active_tab_id, str) or active_tab_id == "":
        raise TypeError("get_active_search_context active_tab_id must be a non-empty string")
    tab_state_version = _mapping_value_or_none(mapping=context_data, key="tab_state_version")
    if not isinstance(tab_state_version, int) or tab_state_version < 0:
        raise TypeError("get_active_search_context tab_state_version must be a non-negative integer")
    tab_count = _mapping_value_or_none(mapping=context_data, key="tab_count")
    if not isinstance(tab_count, int) or tab_count <= 0:
        raise TypeError("get_active_search_context tab_count must be a positive integer")

    search_arguments = {
        "query": active_search_context_query,
        "required_tags": [],
        "forbidden_tags": [],
        "limit": _MAX_EXPRESSION_SEARCH_RESULTS,
        "offset": 0,
    }

    search_started_at = time.perf_counter()
    search_call = _tools_call(
        url=mcp_url,
        request_id=request_id + 1,
        tool_name="search_notes",
        arguments=search_arguments,
    )
    search_execution_ms = round((time.perf_counter() - search_started_at) * 1000, 3)
    search_tool_response = _extract_tool_response(call_response=search_call)
    search_ok = _mapping_value_or_none(mapping=search_tool_response, key="ok")
    if search_ok is not True:
        error = _mapping_value_or_none(mapping=search_tool_response, key="error")
        if not isinstance(error, str) or error.strip() == "":
            error = "search_notes failed"
        raise RuntimeError(str(error))

    search_data = _mapping_dict_or_none(mapping=search_tool_response, key="data")
    if search_data is None:
        raise TypeError("search_notes data must be an object")

    results = _mapping_value_or_none(mapping=search_data, key="results")
    if not isinstance(results, list):
        raise TypeError("search_notes results must be an array")
    total_matches = _mapping_value_or_none(mapping=search_data, key="total_matches")
    if not isinstance(total_matches, int) or total_matches < 0:
        raise TypeError("search_notes total_matches must be a non-negative integer")
    returned_count = _mapping_value_or_none(mapping=search_data, key="returned_count")
    if not isinstance(returned_count, int) or returned_count < 0:
        raise TypeError("search_notes returned_count must be a non-negative integer")

    context_parts: List[str] = []
    included_notes: List[dict] = []
    used_chars = 0
    included_note_count = 0
    covered_note_ids: set[str] = set()
    skipped_duplicate_note_count = 0

    for order_index, entry in enumerate(results, start=1):
        entry_note_id = _mapping_value_or_none(mapping=entry, key="note_id")
        if not isinstance(entry_note_id, str) or entry_note_id == "":
            raise TypeError("search_notes result entry missing note_id")
        if entry_note_id in covered_note_ids:
            skipped_duplicate_note_count += 1
            continue

        rendered = _build_v2_note_block(
            note=entry,
            order_index=order_index,
            include_tags_in_context_window=include_tags_in_context_window,
        )
        if rendered is None:
            continue
        block_text = rendered["block_text"]
        if not isinstance(block_text, str):
            raise TypeError("block_text must be a string")
        rendered_note = _mapping_dict_or_none(mapping=rendered, key="note")
        if rendered_note is None:
            raise TypeError("rendered note metadata must be an object")
        block_covered_note_ids_raw = _mapping_list_or_empty(mapping=rendered_note, key="covered_note_ids")
        block_covered_note_ids: List[str] = []
        for covered_note_id in block_covered_note_ids_raw:
            if not isinstance(covered_note_id, str) or covered_note_id == "":
                continue
            block_covered_note_ids.append(covered_note_id)
        if len(block_covered_note_ids) == 0:
            block_covered_note_ids.append(entry_note_id)

        remaining_chars = context_window_max_chars - used_chars
        if remaining_chars <= 0:
            break

        if len(block_text) <= remaining_chars:
            context_parts.append(block_text)
            used_chars += len(block_text)
            included_notes.append(rendered_note)
            for covered_note_id in block_covered_note_ids:
                covered_note_ids.add(covered_note_id)
            included_note_count += 1
            continue

        if included_note_count == 0:
            partial_block = block_text[:remaining_chars]
            if partial_block.strip() != "":
                context_parts.append(partial_block)
                used_chars += len(partial_block)
                partial_note = dict(rendered_note)
                partial_note["truncated"] = True
                included_notes.append(partial_note)
                for covered_note_id in block_covered_note_ids:
                    covered_note_ids.add(covered_note_id)
                included_note_count += 1
        break

    context_window_text = "".join(context_parts).rstrip()
    context_window_text_for_prompt = "".join(reversed(context_parts)).rstrip()
    omitted_note_count = max(total_matches - included_note_count, 0)

    return {
        "search_arguments": search_arguments,
        "search_execution_ms": search_execution_ms,
        "search_context_resolution_ms": context_resolution_ms,
        "active_tab_id": active_tab_id,
        "tab_state_version": tab_state_version,
        "tab_count": tab_count,
        "search_data": {
            "query": _mapping_value_or_none(mapping=search_data, key="query"),
            "resolved_query": _mapping_value_or_none(mapping=search_data, key="resolved_query"),
            "limit": _mapping_value_or_none(mapping=search_data, key="limit"),
            "offset": _mapping_value_or_none(mapping=search_data, key="offset"),
            "total_matches": total_matches,
            "returned_count": returned_count,
        },
        "active_search_context_query": active_search_context_query,
        "universe_note_count": total_matches,
        "included_note_count": included_note_count,
        "omitted_note_count": omitted_note_count,
        "skipped_duplicate_note_count": skipped_duplicate_note_count,
        "include_tags_in_context_window": include_tags_in_context_window,
        "budget": {
            "max_chars": context_window_max_chars,
            "used_chars": used_chars,
        },
        "notes": included_notes,
        "context_window_text": context_window_text,
        "context_window_text_for_prompt": context_window_text_for_prompt,
    }


def _build_v2_prompt_messages(
    *,
    user_message: str,
    conversation_history: List[dict],
    context_window: dict,
    num_ctx: int,
) -> List[dict]:
    if not isinstance(user_message, str) or user_message.strip() == "":
        raise ValueError("user_message must be a non-empty string")
    if num_ctx <= 0:
        raise ValueError("num_ctx must be > 0")

    context_lines: List[str] = []
    context_lines.append("NOTES")

    context_window_text_for_prompt = _mapping_value_or_none(
        mapping=context_window,
        key="context_window_text_for_prompt",
    )
    if (
        isinstance(context_window_text_for_prompt, str)
        and context_window_text_for_prompt.strip() != ""
    ):
        context_lines.append(context_window_text_for_prompt)
    else:
        context_lines.append("[No notes were included in this context window]")
    context_lines.append("")
    context_lines.append("END OF NOTES")
    context_lines.append("")
    context_lines.append("CONTEXT METADATA")
    active_search_context_query = _mapping_value_or_none(
        mapping=context_window,
        key="active_search_context_query",
    )
    if not isinstance(active_search_context_query, str):
        active_search_context_query = ""
    context_lines.append(
        "Active search context query: "
        + json.dumps(active_search_context_query, ensure_ascii=False)
    )
    universe_note_count = _mapping_value_or_none(mapping=context_window, key="universe_note_count")
    if not isinstance(universe_note_count, int):
        universe_note_count = 0
    context_lines.append(
        "Universe notes: " + str(universe_note_count)
    )
    included_note_count = _mapping_value_or_none(mapping=context_window, key="included_note_count")
    if not isinstance(included_note_count, int):
        included_note_count = 0
    context_lines.append(
        "Included notes: " + str(included_note_count)
    )
    omitted_note_count = _mapping_value_or_none(mapping=context_window, key="omitted_note_count")
    if not isinstance(omitted_note_count, int):
        omitted_note_count = 0
    context_lines.append(
        "Omitted notes: " + str(omitted_note_count)
    )
    budget = _mapping_dict_or_none(mapping=context_window, key="budget")
    if isinstance(budget, dict):
        used_chars = _mapping_value_or_none(mapping=budget, key="used_chars")
        if not isinstance(used_chars, int):
            used_chars = 0
        max_chars = _mapping_value_or_none(mapping=budget, key="max_chars")
        if not isinstance(max_chars, int):
            max_chars = 0
        context_lines.append(
            "Context budget (chars): "
            + str(used_chars)
            + " / "
            + str(max_chars)
        )
    include_tags_in_context_window = _mapping_value_or_none(
        mapping=context_window,
        key="include_tags_in_context_window",
    )
    context_lines.append(
        "Ordering for model input: top notes are generally lower-priority; notes farther down are generally more recent and/or higher-priority."
    )
    context_lines.append(
        "Include tags in context window: "
        + str(bool(include_tags_in_context_window)).lower()
    )
    context_lines.append("Requested Ollama num_ctx: " + str(num_ctx))

    messages: List[dict] = [
        {
            "role": "system",
            "content": "\n".join(context_lines),
        }
    ]
    messages.extend(conversation_history)
    messages.append(
        {
            "role": "system",
            "content": _build_v2_system_prompt(
                include_tags_in_context_window=bool(include_tags_in_context_window)
            ),
        }
    )
    messages.append(
        {
            "role": "user",
            "content": user_message.strip(),
        }
    )
    return messages


def _run_context_window_request(
    *,
    user_message: str,
    conversation_history: List[dict],
    context_window_max_chars: int,
    num_ctx: int,
    include_tags_in_context_window: bool,
    mcp_url: str,
    ollama_chat_url: str,
    model: str,
    progress_callback: Callable[[dict], None] | None,
    status_callback: Callable[[str], None] | None,
) -> dict:
    if user_message.strip() == "":
        raise ValueError("message must not be empty")
    if context_window_max_chars <= 0:
        raise ValueError("context_window_max_chars must be > 0")
    if num_ctx <= 0:
        raise ValueError("num_ctx must be > 0")

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

    request_id = 300

    _emit_status(detail="Building context window...")
    context_build_started_at = time.perf_counter()
    context_window = _build_v2_context_window(
        mcp_url=mcp_url,
        context_window_max_chars=context_window_max_chars,
        include_tags_in_context_window=include_tags_in_context_window,
        request_id=request_id,
    )
    context_build_ms = round((time.perf_counter() - context_build_started_at) * 1000, 3)
    request_id += 2
    append_step(
        step_record={
            "step": 1,
            "action": "context_window_build",
            "reason": "resolved active search context from MCP server and built context window",
            "tool_name": "search_notes",
            "arguments": context_window["search_arguments"],
            "stats": {
                "execution_ms": context_build_ms,
                "search_context_resolution_ms": context_window["search_context_resolution_ms"],
                "search_execution_ms": context_window["search_execution_ms"],
                "active_tab_id": context_window["active_tab_id"],
                "tab_state_version": context_window["tab_state_version"],
                "tab_count": context_window["tab_count"],
                "active_search_context_query": context_window["active_search_context_query"],
                "include_tags_in_context_window": context_window["include_tags_in_context_window"],
                "num_ctx": num_ctx,
                "universe_note_count": context_window["universe_note_count"],
                "included_note_count": context_window["included_note_count"],
                "omitted_note_count": context_window["omitted_note_count"],
                "skipped_duplicate_note_count": context_window["skipped_duplicate_note_count"],
                "budget_max_chars": context_window_max_chars,
                "budget_used_chars": context_window["budget"]["used_chars"],
            },
            "tool_response": {
                "ok": True,
                "data": {
                    "active_tab_id": context_window["active_tab_id"],
                    "tab_state_version": context_window["tab_state_version"],
                    "tab_count": context_window["tab_count"],
                    "active_search_context_query": context_window["active_search_context_query"],
                    "include_tags_in_context_window": context_window["include_tags_in_context_window"],
                    "num_ctx": num_ctx,
                    "search_data": context_window["search_data"],
                    "included_note_count": context_window["included_note_count"],
                    "omitted_note_count": context_window["omitted_note_count"],
                    "skipped_duplicate_note_count": context_window["skipped_duplicate_note_count"],
                    "budget": context_window["budget"],
                },
            },
        }
    )

    _emit_status(detail="Composing model prompt...")
    prompt_messages = _build_v2_prompt_messages(
        user_message=user_message,
        conversation_history=conversation_history,
        context_window=context_window,
        num_ctx=num_ctx,
    )
    append_step(
        step_record={
            "step": 2,
            "action": "prompt_compose",
            "reason": "composed system prompt + context window + conversation history",
            "model_payload": {
                "prompt_messages": prompt_messages,
            },
        }
    )

    _emit_status(detail="Waiting for model...")
    model_started_at = time.perf_counter()
    model_runtime = _ollama_chat_text_with_runtime(
        ollama_chat_url=ollama_chat_url,
        model=resolved_model,
        messages=prompt_messages,
        num_ctx=num_ctx,
    )
    model_execution_ms = round((time.perf_counter() - model_started_at) * 1000, 3)
    answer = _mapping_value_or_none(mapping=model_runtime, key="content")
    if not isinstance(answer, str):
        raise TypeError("model runtime content must be a string")
    served_model = _mapping_value_or_none(mapping=model_runtime, key="served_model")
    if not isinstance(served_model, str) or served_model.strip() == "":
        served_model = resolved_model

    _emit_status(detail="Verifying runtime model/context...")
    running_num_ctx = _ollama_running_model_num_ctx(
        ollama_chat_url=ollama_chat_url,
        model=served_model,
    )
    model_max_context_window = _ollama_model_context_length(
        ollama_chat_url=ollama_chat_url,
        model=served_model,
    )

    effective_context_window = num_ctx
    if isinstance(running_num_ctx, int):
        effective_context_window = running_num_ctx
    elif isinstance(model_max_context_window, int):
        effective_context_window = min(num_ctx, model_max_context_window)
    combined_verify_error = ""

    append_step(
        step_record={
            "step": 3,
            "action": "model_response",
            "reason": "model produced assistant response from current prompt context",
            "stats": {
                "execution_ms": model_execution_ms,
                "num_ctx": num_ctx,
                "served_model": served_model,
                "running_num_ctx": running_num_ctx,
                "model_max_context_window": model_max_context_window,
                "effective_context_window": effective_context_window,
            },
            "model_payload": {
                "raw_model_output": answer,
            },
            "tool_response": {
                "ok": True,
                "data": {
                    "served_model": served_model,
                    "requested_num_ctx": num_ctx,
                    "running_num_ctx": running_num_ctx,
                    "model_max_context_window": model_max_context_window,
                    "effective_context_window": effective_context_window,
                },
                "error": combined_verify_error,
            },
        }
    )

    normalized_answer = answer.strip()
    if normalized_answer == "":
        normalized_answer = "I do not know based on the current context window."

    return {
        "ok": True,
        "answer": normalized_answer,
        "model": resolved_model,
        "served_model": served_model,
        "steps": steps,
        "prompt_messages": prompt_messages,
        "context_window": {
            "active_search_context_query": context_window["active_search_context_query"],
            "universe_note_count": context_window["universe_note_count"],
            "included_note_count": context_window["included_note_count"],
            "omitted_note_count": context_window["omitted_note_count"],
            "skipped_duplicate_note_count": context_window["skipped_duplicate_note_count"],
            "include_tags_in_context_window": context_window["include_tags_in_context_window"],
            "num_ctx": num_ctx,
            "budget": context_window["budget"],
            "notes": context_window["notes"],
            "context_window_text": context_window["context_window_text"],
        },
        "runtime_verification": {
            "served_model": served_model,
            "requested_num_ctx": num_ctx,
            "running_num_ctx": running_num_ctx,
            "model_max_context_window": model_max_context_window,
            "effective_context_window": effective_context_window,
            "verify_error": combined_verify_error,
        },
        "total_execution_ms": _total_execution_ms(),
        "mode": "v2_context_window",
    }


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
    regex_engine_python_re_selected = ""
    if default_regex_engine == "python-re":
        regex_engine_python_re_selected = "selected"
    regex_engine_re2_selected = ""
    if default_regex_engine == "re2":
        regex_engine_re2_selected = "selected"
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
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        const phase = stats && typeof stats.phase === "string" ? stats.phase : "";
        if (phase === "planning_prompt" && Array.isArray(payload.planner_prompt_messages)) {{
          return payload.planner_prompt_messages.filter((entry) => entry && typeof entry === "object");
        }}
        if (phase === "relevance_prompt" && Array.isArray(payload.relevance_prompt_messages)) {{
          return payload.relevance_prompt_messages.filter((entry) => entry && typeof entry === "object");
        }}
        if (phase === "decision_prompt" && Array.isArray(payload.decision_prompt_messages)) {{
          return payload.decision_prompt_messages.filter((entry) => entry && typeof entry === "object");
        }}
        const combined = [];
        if (Array.isArray(payload.planner_prompt_messages)) {{
          combined.push(...payload.planner_prompt_messages.filter((entry) => entry && typeof entry === "object"));
        }}
        if (Array.isArray(payload.relevance_prompt_messages)) {{
          combined.push(...payload.relevance_prompt_messages.filter((entry) => entry && typeof entry === "object"));
        }}
        if (Array.isArray(payload.decision_prompt_messages)) {{
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
      if (typeof value === "string") {{
        const parsed = tryParseJsonText(value);
        if (parsed !== null) {{
          return prettifyRawModelOutput(parsed);
        }}
        const parsedSuffix = tryParseJsonSuffix(value);
        if (parsedSuffix !== null) {{
          return {{
            text_prefix: parsedSuffix.prefix,
            json_suffix: prettifyRawModelOutput(parsedSuffix.parsed),
          }};
        }}
        return value;
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
          const parsedSuffix = tryParseJsonSuffix(child);
          if (parsedSuffix !== null) {{
            output[key] = {{
              text_prefix: parsedSuffix.prefix,
              json_suffix: prettifyRawModelOutput(parsedSuffix.parsed),
            }};
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
          "evidence_selection_strategy",
          "carried_evidence_max_notes",
          "latest_result_evidence_max_notes",
          "relevance_filter_stage_enabled",
          "decision_stage_enabled",
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
        const payload = step.model_payload && typeof step.model_payload === "object"
          ? step.model_payload
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
          if (Number.isInteger(stats.skipped_duplicate_query_count)) {{
            appendLine(`skipped_duplicates: ${{stats.skipped_duplicate_query_count}}`, 1);
          }}
          if (Number.isInteger(stats.skipped_invalid_expression_count)) {{
            appendLine(`skipped_invalid_expressions: ${{stats.skipped_invalid_expression_count}}`, 1);
          }}
          if (Number.isInteger(stats.skipped_unexecutable_query_count)) {{
            appendLine(`skipped_unexecutable: ${{stats.skipped_unexecutable_query_count}}`, 1);
          }}
          appendLine(`results: ${{stats.iteration_result_count}}`, 1);
          appendLine(`decision: ${{stats.decision}}`, 1);
        }}
        const plannedExpressions = payload && Array.isArray(payload.planned_expressions)
          ? payload.planned_expressions
          : [];
        if (plannedExpressions.length > 0) {{
          appendLine("Planner guesses:");
          for (let i = 0; i < plannedExpressions.length; i += 1) {{
            const expr = plannedExpressions[i];
            if (!expr || typeof expr !== "object") {{
              continue;
            }}
            const exprType = typeof expr.type === "string" ? expr.type : "expression";
            if (exprType === "phrase") {{
              appendLine(`[${{i + 1}}] phrase: "${{typeof expr.value === "string" ? expr.value : ""}}"`, 1);
              continue;
            }}
            if (exprType === "regex") {{
              const pattern = typeof expr.pattern === "string" ? expr.pattern : "";
              const flags = typeof expr.flags === "string" ? expr.flags : "";
              appendLine(`[${{i + 1}}] regex: /${{pattern}}/${{flags}}`, 1);
              continue;
            }}
            if (exprType === "near") {{
              const left = typeof expr.left === "string" ? expr.left : "";
              const right = typeof expr.right === "string" ? expr.right : "";
              const windowChars = Number.isInteger(expr.window_chars) ? expr.window_chars : "?";
              appendLine(`[${{i + 1}}] near: "${{left}}" ~ "${{right}}" @${{windowChars}}`, 1);
              continue;
            }}
            if (exprType === "tag") {{
              appendLine(`[${{i + 1}}] tag: ${{typeof expr.value === "string" ? expr.value : ""}}`, 1);
              continue;
            }}
            appendLine(`[${{i + 1}}] ${{JSON.stringify(expr)}}`, 1);
          }}
        }}
        const queries = data && Array.isArray(data.queries_executed) ? data.queries_executed : [];
        const evidenceOverview = data && data.evidence_overview && typeof data.evidence_overview === "object"
          ? data.evidence_overview
          : null;
        if (evidenceOverview) {{
          appendLine("Evidence overview:");
          if (typeof evidenceOverview.band === "string") {{
            appendLine(`band: ${{evidenceOverview.band}}`, 1);
          }}
          if (Number.isInteger(evidenceOverview.candidate_note_count)) {{
            appendLine(`candidate_notes: ${{evidenceOverview.candidate_note_count}}`, 1);
          }}
          if (Number.isInteger(evidenceOverview.queries_with_matches) && Number.isInteger(evidenceOverview.executed_query_count)) {{
            appendLine(
              `queries_with_matches: ${{evidenceOverview.queries_with_matches}}/${{evidenceOverview.executed_query_count}}`,
              1,
            );
          }}
          if (Number.isInteger(evidenceOverview.total_scoped_matches)) {{
            appendLine(`total_scoped_matches: ${{evidenceOverview.total_scoped_matches}}`, 1);
          }}
        }}
        if (typeof data.latest_result_selection_order === "string" && data.latest_result_selection_order !== "") {{
          appendLine("Latest result selection:");
          appendLine(`order: ${{data.latest_result_selection_order}}`, 1);
          if (Number.isInteger(data.latest_result_note_count_before_limit)) {{
            appendLine(`notes_before_limit: ${{data.latest_result_note_count_before_limit}}`, 1);
          }}
          if (Number.isInteger(data.latest_result_limit)) {{
            appendLine(`limit: ${{data.latest_result_limit}}`, 1);
          }}
        }}
        const latestResultNotes = data && Array.isArray(data.latest_result_notes)
          ? data.latest_result_notes
          : [];
        if (latestResultNotes.length > 0) {{
          appendLine("Interleaved evidence notes:");
          const displayCount = Math.min(latestResultNotes.length, 8);
          for (let i = 0; i < displayCount; i += 1) {{
            const note = latestResultNotes[i];
            if (!note || typeof note !== "object") {{
              continue;
            }}
            appendLine(`[${{i + 1}}]`, 1);
            let snippet = "";
            if (typeof note.snippet_excerpt === "string" && note.snippet_excerpt.trim() !== "") {{
              snippet = note.snippet_excerpt;
            }} else if (typeof note.context_excerpt === "string" && note.context_excerpt.trim() !== "") {{
              snippet = note.context_excerpt;
            }} else if (typeof note.content_excerpt === "string" && note.content_excerpt.trim() !== "") {{
              snippet = note.content_excerpt;
            }}
            snippet = snippet.replace(/\\s+/g, " ").trim();
            if (snippet !== "") {{
              appendLine(snippet.length > 220 ? snippet.slice(0, 220) + "..." : snippet, 2);
            }}
          }}
        }}
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
            if (typeof result.snippet_excerpt === "string" && result.snippet_excerpt.trim() !== "") {{
              snippet = result.snippet_excerpt;
            }} else if (typeof result.context_excerpt === "string" && result.context_excerpt.trim() !== "") {{
              snippet = result.context_excerpt;
            }} else if (typeof result.content_excerpt === "string" && result.content_excerpt.trim() !== "") {{
              snippet = result.content_excerpt;
            }} else if (typeof result.context_text === "string" && result.context_text.trim() !== "") {{
              snippet = result.context_text;
            }} else if (typeof result.content_text === "string" && result.content_text.trim() !== "") {{
              snippet = result.content_text;
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

      if (action === "evidence_relevance_filter") {{
        const data = step.tool_response && step.tool_response.data && typeof step.tool_response.data === "object"
          ? step.tool_response.data
          : null;
        const stats = step.stats && typeof step.stats === "object" ? step.stats : null;
        const appendLine = (text, indentLevel = 0) => {{
          const line = document.createElement("div");
          line.className = "stage-summary-line";
          line.textContent = text;
          if (indentLevel > 0) {{
            line.style.marginLeft = `${{indentLevel * 14}}px`;
          }}
          wrap.appendChild(line);
        }};
        if (!data) {{
          wrap.textContent = "Relevance filter complete.";
          return wrap;
        }}
        if (stats) {{
          appendLine("Stats:");
          if (Number.isInteger(stats.iteration_index)) {{
            appendLine(`iteration: ${{stats.iteration_index}}`, 1);
          }}
          if (typeof stats.relevance_ms === "number") {{
            appendLine(`relevance_ms: ${{stats.relevance_ms}}`, 1);
          }}
          if (Number.isInteger(stats.candidate_note_count)) {{
            appendLine(`candidate_notes: ${{stats.candidate_note_count}}`, 1);
          }}
          if (Number.isInteger(stats.relevant_note_count)) {{
            appendLine(`relevant_notes: ${{stats.relevant_note_count}}`, 1);
          }}
          if (Number.isInteger(stats.selected_snippet_count)) {{
            appendLine(`selected_snippets: ${{stats.selected_snippet_count}}`, 1);
          }}
        }}
        if (typeof data.reasoning === "string" && data.reasoning !== "") {{
          appendLine("Reasoning: " + data.reasoning);
        }}
        const selectedSnippets = Array.isArray(data.selected_relevant_snippets) ? data.selected_relevant_snippets : [];
        if (selectedSnippets.length > 0) {{
          appendLine("Model-selected snippets:");
          const snippetDisplayCount = Math.min(selectedSnippets.length, 12);
          for (let i = 0; i < snippetDisplayCount; i += 1) {{
            const snippetRaw = selectedSnippets[i];
            if (typeof snippetRaw !== "string") {{
              continue;
            }}
            const snippet = snippetRaw.replace(/\\s+/g, " ").trim();
            if (snippet === "") {{
              continue;
            }}
            appendLine(`[${{i + 1}}] ${{snippet.length > 280 ? snippet.slice(0, 280) + "..." : snippet}}`, 1);
          }}
        }}
        const relevantNotes = Array.isArray(data.relevant_notes) ? data.relevant_notes : [];

        const renderNoteList = (title, notes) => {{
          if (!Array.isArray(notes) || notes.length === 0) {{
            appendLine(`${{title}}: none`);
            return;
          }}
          appendLine(title + ":");
          const displayCount = Math.min(notes.length, 10);
          for (let i = 0; i < displayCount; i += 1) {{
            const note = notes[i];
            if (!note || typeof note !== "object") {{
              continue;
            }}
            appendLine(`[${{i + 1}}]`, 1);
            let snippet = "";
            if (typeof note.snippet_excerpt === "string" && note.snippet_excerpt.trim() !== "") {{
              snippet = note.snippet_excerpt;
            }} else if (typeof note.context_excerpt === "string" && note.context_excerpt.trim() !== "") {{
              snippet = note.context_excerpt;
            }} else if (typeof note.content_excerpt === "string" && note.content_excerpt.trim() !== "") {{
              snippet = note.content_excerpt;
            }}
            snippet = snippet.replace(/\\s+/g, " ").trim();
            if (snippet !== "") {{
              appendLine(snippet.length > 260 ? snippet.slice(0, 260) + "..." : snippet, 2);
            }}
          }}
        }};
        renderNoteList("Relevant notes", relevantNotes);
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
        const plannedExpressions = Array.isArray(data.planned_expressions)
          ? data.planned_expressions
          : [];
        if (plannedExpressions.length > 0) {{
          const appendLine = (text, indentLevel = 0) => {{
            const lineItem = document.createElement("div");
            lineItem.className = "stage-summary-line";
            lineItem.textContent = text;
            if (indentLevel > 0) {{
              lineItem.style.marginLeft = `${{indentLevel * 14}}px`;
            }}
            wrap.appendChild(lineItem);
          }};
          appendLine("Planner guesses:");
          for (let i = 0; i < plannedExpressions.length; i += 1) {{
            const expr = plannedExpressions[i];
            if (!expr || typeof expr !== "object") {{
              continue;
            }}
            const exprType = typeof expr.type === "string" ? expr.type : "expression";
            if (exprType === "phrase") {{
              appendLine(`[${{i + 1}}] phrase: "${{typeof expr.value === "string" ? expr.value : ""}}"`, 1);
              continue;
            }}
            if (exprType === "regex") {{
              const pattern = typeof expr.pattern === "string" ? expr.pattern : "";
              const flags = typeof expr.flags === "string" ? expr.flags : "";
              appendLine(`[${{i + 1}}] regex: /${{pattern}}/${{flags}}`, 1);
              continue;
            }}
            if (exprType === "near") {{
              const left = typeof expr.left === "string" ? expr.left : "";
              const right = typeof expr.right === "string" ? expr.right : "";
              const windowChars = Number.isInteger(expr.window_chars) ? expr.window_chars : "?";
              appendLine(`[${{i + 1}}] near: "${{left}}" ~ "${{right}}" @${{windowChars}}`, 1);
              continue;
            }}
            if (exprType === "tag") {{
              appendLine(`[${{i + 1}}] tag: ${{typeof expr.value === "string" ? expr.value : ""}}`, 1);
              continue;
            }}
            appendLine(`[${{i + 1}}] ${{JSON.stringify(expr)}}`, 1);
          }}
        }}
        const latestResultNotes = Array.isArray(data.latest_result_notes)
          ? data.latest_result_notes
          : [];
        if (latestResultNotes.length > 0) {{
          const appendLine = (text, indentLevel = 0) => {{
            const lineItem = document.createElement("div");
            lineItem.className = "stage-summary-line";
            lineItem.textContent = text;
            if (indentLevel > 0) {{
              lineItem.style.marginLeft = `${{indentLevel * 14}}px`;
            }}
            wrap.appendChild(lineItem);
          }};
          appendLine("Interleaved evidence notes:");
          const displayCount = Math.min(latestResultNotes.length, 8);
          for (let i = 0; i < displayCount; i += 1) {{
            const note = latestResultNotes[i];
            if (!note || typeof note !== "object") {{
              continue;
            }}
            appendLine(`[${{i + 1}}]`, 1);
            let snippet = "";
            if (typeof note.snippet_excerpt === "string" && note.snippet_excerpt.trim() !== "") {{
              snippet = note.snippet_excerpt;
            }} else if (typeof note.context_excerpt === "string" && note.context_excerpt.trim() !== "") {{
              snippet = note.context_excerpt;
            }} else if (typeof note.content_excerpt === "string" && note.content_excerpt.trim() !== "") {{
              snippet = note.content_excerpt;
            }}
            snippet = snippet.replace(/\\s+/g, " ").trim();
            if (snippet !== "") {{
              appendLine(snippet.length > 220 ? snippet.slice(0, 220) + "..." : snippet, 2);
            }}
          }}
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
      if (action === "evidence_relevance_filter") {{
        return `${{stepNo}}: relevance filter`;
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


def _web_html_v2(
    *,
    default_model: str,
    default_mcp_url: str,
    default_ollama_chat_url: str,
) -> str:
    model_value = json.dumps(default_model)
    mcp_url_value = json.dumps(default_mcp_url)
    ollama_chat_url_value = json.dumps(default_ollama_chat_url)
    context_window_max_chars_value = str(_DEFAULT_CONTEXT_WINDOW_MAX_CHARS)
    num_ctx_value = str(_DEFAULT_V2_NUM_CTX)
    include_tags_in_context_window_value = json.dumps(
        _DEFAULT_V2_INCLUDE_TAGS_IN_CONTEXT_WINDOW
    )
    html_template = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MetaList MCP Client v2</title>
  <style>
    :root {
      --bg: #f4f5f7;
      --panel: #ffffff;
      --line: #d7dde6;
      --ink: #182230;
      --muted: #5f6f85;
      --accent: #1f6feb;
      --assistant-bubble: #e9f2ff;
      --user-bubble: #1f6feb;
      --user-ink: #ffffff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 15% 0%, #fff8e8 0%, var(--bg) 45%, #eceffd 100%);
    }
    .wrap {
      max-width: 1380px;
      margin: 18px auto;
      padding: 0 14px;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(360px, 1fr);
      gap: 12px;
      align-items: start;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 6px 26px rgba(0,0,0,0.07);
    }
    .chat-card {
      padding: 12px;
    }
    .inspector-card {
      position: sticky;
      top: 12px;
      padding: 12px;
      max-height: calc(100vh - 24px);
      overflow: auto;
    }
    h1 {
      margin: 0 0 8px 0;
      font-size: 22px;
    }
    h2 {
      margin: 0 0 8px 0;
      font-size: 18px;
    }
    .muted {
      color: var(--muted);
      font-size: 12px;
    }
    .config-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }
    input, textarea, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 9px;
      font: inherit;
    }
    textarea {
      min-height: 90px;
      resize: vertical;
    }
    .row {
      display: flex;
      gap: 8px;
    }
    button {
      background: var(--accent);
      color: white;
      border: 0;
      font-weight: 600;
      cursor: pointer;
    }
    button.secondary {
      background: #4d5a6c;
    }
    button:disabled {
      opacity: 0.6;
      cursor: wait;
    }
    .status-row {
      margin-top: 10px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .chat-thread {
      margin-top: 10px;
      min-height: 320px;
      max-height: 56vh;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      background: #f9fbff;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .bubble-wrap {
      display: flex;
      width: 100%;
    }
    .bubble-wrap.assistant {
      justify-content: flex-start;
    }
    .bubble-wrap.user {
      justify-content: flex-end;
    }
    .bubble {
      max-width: 82%;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border-radius: 18px;
      padding: 10px 12px;
      line-height: 1.35;
      font-size: 14px;
      border: 1px solid transparent;
    }
    .bubble.assistant {
      background: var(--assistant-bubble);
      color: #1f2f47;
      border-color: #c6dcff;
      border-top-left-radius: 8px;
    }
    .bubble.user {
      background: var(--user-bubble);
      color: var(--user-ink);
      border-color: #1754b4;
      border-top-right-radius: 8px;
    }
    .composer {
      margin-top: 10px;
      display: grid;
      gap: 8px;
    }
    .turn-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 8px;
    }
    .turn-btn {
      border: 1px solid var(--line);
      background: #f4f7fc;
      color: #21314a;
      border-radius: 8px;
      padding: 6px 8px;
      font-size: 12px;
      cursor: pointer;
      max-width: 100%;
      text-align: left;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .turn-btn.active {
      border-color: #8ab2ff;
      background: #e9f2ff;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      background: #0f1c36;
      color: #d8e6ff;
      border-radius: 10px;
      padding: 10px;
      max-height: 52vh;
      overflow: auto;
      font-size: 12px;
      line-height: 1.35;
      tab-size: 2;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }
    .events {
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fbfcff;
      max-height: 180px;
      overflow: auto;
      padding: 8px;
      font-size: 12px;
      color: #21314a;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    @media (max-width: 1000px) {
      .layout { grid-template-columns: 1fr; }
      .inspector-card { position: static; max-height: none; }
      .config-grid { grid-template-columns: 1fr; }
      .bubble { max-width: 94%; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="layout">
      <section class="card chat-card">
        <h1>MetaList MCP Client v2</h1>
        <p class="muted">Context-window chat with full per-response prompt inspection.</p>
        <div class="config-grid">
          <div>
            <label for="model">Ollama model</label>
            <input id="model" />
          </div>
          <div>
            <label for="context_window_max_chars">Context window max chars</label>
            <input id="context_window_max_chars" type="number" min="1000" step="1000" />
          </div>
          <div>
            <label for="num_ctx">Ollama num_ctx</label>
            <input id="num_ctx" type="number" min="1" step="1024" />
          </div>
          <div>
            <label for="mcp_url">MCP URL</label>
            <input id="mcp_url" />
          </div>
          <div>
            <label for="ollama_chat_url">Ollama chat URL</label>
            <input id="ollama_chat_url" />
          </div>
        </div>
        <div style="margin-top:8px;">
          <label for="include_tags_in_context_window" style="display:flex;align-items:center;gap:8px;color:var(--ink);font-size:13px;">
            <input id="include_tags_in_context_window" type="checkbox" style="width:auto;" />
            Include tags in context window
          </label>
        </div>
        <div class="status-row">
          <div id="run_status" class="muted">Idle.</div>
          <div id="timing" class="muted"></div>
          <div id="runtime_verify" class="muted"></div>
        </div>
        <div id="chat_thread" class="chat-thread"></div>
        <div class="composer">
          <label for="composer">Message</label>
          <textarea id="composer" placeholder="Ask a question about your notes..."></textarea>
          <div class="row">
            <button id="send_btn">Send</button>
            <button id="models_btn" class="secondary">Load Ollama Models</button>
            <button id="reset_btn" class="secondary">Reset Chat</button>
          </div>
        </div>
        <div id="events" class="events"></div>
      </section>
      <aside class="card inspector-card">
        <h2>Prompt Inspector</h2>
        <p class="muted">Exact model input per assistant response.</p>
        <div id="turn_list" class="turn-list"></div>
        <pre id="prompt_payload">No assistant response yet.</pre>
      </aside>
    </div>
  </div>
  <script>
    const defaults = {
      model: __MODEL_VALUE__,
      mcpUrl: __MCP_URL_VALUE__,
      ollamaChatUrl: __OLLAMA_CHAT_URL_VALUE__,
      contextWindowMaxChars: __CONTEXT_WINDOW_MAX_CHARS_VALUE__,
      numCtx: __NUM_CTX_VALUE__,
      includeTagsInContextWindow: __INCLUDE_TAGS_IN_CONTEXT_WINDOW_VALUE__
    };

    const modelEl = document.getElementById("model");
    const mcpUrlEl = document.getElementById("mcp_url");
    const ollamaChatUrlEl = document.getElementById("ollama_chat_url");
    const contextWindowMaxCharsEl = document.getElementById("context_window_max_chars");
    const numCtxEl = document.getElementById("num_ctx");
    const includeTagsInContextWindowEl = document.getElementById("include_tags_in_context_window");
    const chatThreadEl = document.getElementById("chat_thread");
    const composerEl = document.getElementById("composer");
    const sendBtn = document.getElementById("send_btn");
    const resetBtn = document.getElementById("reset_btn");
    const modelsBtn = document.getElementById("models_btn");
    const runStatusEl = document.getElementById("run_status");
    const timingEl = document.getElementById("timing");
    const runtimeVerifyEl = document.getElementById("runtime_verify");
    const eventsEl = document.getElementById("events");
    const turnListEl = document.getElementById("turn_list");
    const promptPayloadEl = document.getElementById("prompt_payload");

    modelEl.value = defaults.model;
    mcpUrlEl.value = defaults.mcpUrl;
    ollamaChatUrlEl.value = defaults.ollamaChatUrl;
    contextWindowMaxCharsEl.value = String(defaults.contextWindowMaxChars);
    numCtxEl.value = String(defaults.numCtx);
    includeTagsInContextWindowEl.checked = Boolean(defaults.includeTagsInContextWindow);

    let conversation = [];
    let promptInspectors = [];
    let selectedInspectorIndex = -1;

    function setRunStatus(text) {
      runStatusEl.textContent = text;
    }

    function setTiming(text) {
      timingEl.textContent = text;
    }

    function setRuntimeVerify(text) {
      runtimeVerifyEl.textContent = text;
    }

    function appendEventLine(text) {
      const now = new Date();
      const stamp = now.toLocaleTimeString();
      const line = document.createElement("div");
      line.textContent = `[${stamp}] ${text}`;
      eventsEl.appendChild(line);
      eventsEl.scrollTop = eventsEl.scrollHeight;
    }

    function renderConversation() {
      chatThreadEl.innerHTML = "";
      if (!Array.isArray(conversation) || conversation.length === 0) {
        const empty = document.createElement("div");
        empty.className = "muted";
        empty.textContent = "No messages yet.";
        chatThreadEl.appendChild(empty);
        return;
      }
      for (const message of conversation) {
        if (!message || typeof message !== "object") {
          continue;
        }
        const role = message.role === "user" ? "user" : "assistant";
        const wrap = document.createElement("div");
        wrap.className = "bubble-wrap " + role;
        const bubble = document.createElement("div");
        bubble.className = "bubble " + role;
        bubble.textContent = typeof message.content === "string" ? message.content : "";
        wrap.appendChild(bubble);
        chatThreadEl.appendChild(wrap);
      }
      chatThreadEl.scrollTop = chatThreadEl.scrollHeight;
    }

    function formatPromptMessages(messages) {
      if (!Array.isArray(messages) || messages.length === 0) {
        return "No prompt messages recorded.";
      }
      const parts = [];
      for (const message of messages) {
        if (!message || typeof message !== "object") {
          continue;
        }
        const role = typeof message.role === "string" ? message.role.toUpperCase() : "UNKNOWN";
        const content = typeof message.content === "string"
          ? message.content
          : JSON.stringify(message.content, null, 2);
        parts.push(role + ":\n" + content);
      }
      if (parts.length === 0) {
        return "No prompt messages recorded.";
      }
      return parts.join("\n\n");
    }

    function renderPromptInspector() {
      turnListEl.innerHTML = "";
      if (!Array.isArray(promptInspectors) || promptInspectors.length === 0) {
        promptPayloadEl.textContent = "No assistant response yet.";
        return;
      }
      for (let i = 0; i < promptInspectors.length; i += 1) {
        const inspector = promptInspectors[i];
        const button = document.createElement("button");
        button.type = "button";
        button.className = "turn-btn" + (i === selectedInspectorIndex ? " active" : "");
        button.textContent = "Response " + String(i + 1);
        button.addEventListener("click", () => {
          selectedInspectorIndex = i;
          renderPromptInspector();
        });
        turnListEl.appendChild(button);
      }
      if (selectedInspectorIndex < 0 || selectedInspectorIndex >= promptInspectors.length) {
        selectedInspectorIndex = promptInspectors.length - 1;
      }
      const selected = promptInspectors[selectedInspectorIndex];
      const blocks = [];
      blocks.push("PROMPT MESSAGES");
      blocks.push(formatPromptMessages(selected.prompt_messages));
      if (selected.context_window && typeof selected.context_window === "object") {
        blocks.push("");
        blocks.push("CONTEXT WINDOW STATS");
        blocks.push(JSON.stringify({
          active_search_context_query: selected.context_window.active_search_context_query,
          universe_note_count: selected.context_window.universe_note_count,
          included_note_count: selected.context_window.included_note_count,
          omitted_note_count: selected.context_window.omitted_note_count,
          skipped_duplicate_note_count: selected.context_window.skipped_duplicate_note_count,
          include_tags_in_context_window: selected.context_window.include_tags_in_context_window,
          num_ctx: selected.context_window.num_ctx,
          budget: selected.context_window.budget
        }, null, 2));
      }
      if (selected.runtime_verification && typeof selected.runtime_verification === "object") {
        blocks.push("");
        blocks.push("RUNTIME VERIFICATION");
        blocks.push(JSON.stringify(selected.runtime_verification, null, 2));
      }
      promptPayloadEl.textContent = blocks.join("\n");
    }

    async function fetchWithTimeout(url, options, timeoutMs) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort("request-timeout"), timeoutMs);
      try {
        return await fetch(url, { ...options, signal: controller.signal });
      } finally {
        clearTimeout(timeout);
      }
    }

    async function readErrorResponse(res) {
      const text = await res.text();
      if (text === "") {
        return `HTTP ${res.status}`;
      }
      try {
        return JSON.stringify(JSON.parse(text), null, 2);
      } catch (_) {
        return text;
      }
    }

    async function sendMessage() {
      const message = composerEl.value.trim();
      if (message === "") {
        return;
      }

      const priorConversation = conversation.slice();
      conversation.push({ role: "user", content: message });
      const assistantIndex = conversation.length;
      conversation.push({ role: "assistant", content: "Running..." });
      renderConversation();

      composerEl.value = "";
      sendBtn.disabled = true;
      setRunStatus("Running...");
      setTiming("");
      setRuntimeVerify("");
      appendEventLine("Request started.");

      const payload = {
        message: message,
        conversation_history: priorConversation,
        model: modelEl.value,
        context_window_max_chars: Number(contextWindowMaxCharsEl.value),
        num_ctx: Number(numCtxEl.value),
        include_tags_in_context_window: includeTagsInContextWindowEl.checked,
        mcp_url: mcpUrlEl.value,
        ollama_chat_url: ollamaChatUrlEl.value
      };

      try {
        const res = await fetchWithTimeout("/api/chat_stream_v2", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }, 240000);

        if (!res.ok) {
          const detail = await readErrorResponse(res);
          conversation[assistantIndex] = { role: "assistant", content: "Error: " + detail };
          renderConversation();
          appendEventLine("Request failed: " + detail);
          setRunStatus("Failed.");
          return;
        }

        if (!res.body) {
          conversation[assistantIndex] = { role: "assistant", content: "Error: Streaming body missing." };
          renderConversation();
          appendEventLine("Streaming body missing.");
          setRunStatus("Failed.");
          return;
        }

        const decoder = new TextDecoder();
        const reader = res.body.getReader();
        let buffer = "";
        let sawFinal = false;

        while (true) {
          const chunk = await reader.read();
          if (chunk.done) {
            break;
          }
          buffer += decoder.decode(chunk.value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed === "") {
              continue;
            }
            let event;
            try {
              event = JSON.parse(trimmed);
            } catch (error) {
              conversation[assistantIndex] = { role: "assistant", content: "Error parsing stream event: " + String(error) };
              renderConversation();
              appendEventLine("Stream parse error.");
              setRunStatus("Failed.");
              return;
            }

            if (event.type === "status") {
              const detail = typeof event.detail === "string" ? event.detail : "Running...";
              setRunStatus(detail);
              continue;
            }

            if (event.type === "step") {
              const step = event.step && typeof event.step === "object" ? event.step : null;
              if (step && typeof step.action === "string") {
                appendEventLine("Step: " + step.action);
              } else {
                appendEventLine("Step received.");
              }
              continue;
            }

            if (event.type === "error") {
              const detail = typeof event.detail === "string" ? event.detail : "Unknown error";
              conversation[assistantIndex] = { role: "assistant", content: "Error: " + detail };
              renderConversation();
              appendEventLine("Error: " + detail);
              setRunStatus("Failed.");
              continue;
            }

            if (event.type === "final") {
              sawFinal = true;
              const result = event.result && typeof event.result === "object" ? event.result : {};
              const answer = typeof result.answer === "string" && result.answer.trim() !== ""
                ? result.answer
                : "I do not know based on the current context window.";
              conversation[assistantIndex] = { role: "assistant", content: answer };
              renderConversation();
              if (Array.isArray(result.prompt_messages)) {
                promptInspectors.push({
                  prompt_messages: result.prompt_messages,
                  context_window: result.context_window,
                  runtime_verification: result.runtime_verification
                });
                selectedInspectorIndex = promptInspectors.length - 1;
                renderPromptInspector();
              }
              const runtime = result.runtime_verification && typeof result.runtime_verification === "object"
                ? result.runtime_verification
                : null;
              if (runtime) {
                const servedModel = typeof runtime.served_model === "string" ? runtime.served_model : "";
                const effectiveCtx = typeof runtime.effective_context_window === "number"
                  ? runtime.effective_context_window
                  : null;
                const requestedCtx = typeof runtime.requested_num_ctx === "number"
                  ? runtime.requested_num_ctx
                  : null;
                const runningCtx = typeof runtime.running_num_ctx === "number"
                  ? runtime.running_num_ctx
                  : null;
                const maxCtx = typeof runtime.model_max_context_window === "number"
                  ? runtime.model_max_context_window
                  : null;
                const verifyError = typeof runtime.verify_error === "string" ? runtime.verify_error : "";
                if (verifyError !== "") {
                  setRuntimeVerify(
                    "Runtime verify: served model="
                    + servedModel
                    + ", context="
                    + String(effectiveCtx ?? requestedCtx ?? "unknown")
                    + " (verify warning: "
                    + verifyError
                    + ")"
                  );
                } else {
                  let runtimeText =
                    "Runtime verify: served model="
                    + servedModel
                    + ", context="
                    + String(effectiveCtx ?? requestedCtx ?? "unknown");
                  if (runningCtx !== null) {
                    runtimeText += " (runner " + String(runningCtx) + ")";
                  }
                  if (maxCtx !== null) {
                    runtimeText += " (model max " + String(maxCtx) + ")";
                  }
                  setRuntimeVerify(runtimeText);
                }
              } else {
                setRuntimeVerify("");
              }
              const totalMs = typeof result.total_execution_ms === "number" ? result.total_execution_ms : null;
              if (totalMs !== null && Number.isFinite(totalMs)) {
                setTiming("Total compute time: " + totalMs.toFixed(1) + " ms");
              } else {
                setTiming("");
              }
              setRunStatus("Completed.");
              appendEventLine("Request completed.");
            }
          }
        }

        if (!sawFinal) {
          if (conversation[assistantIndex] && conversation[assistantIndex].content === "Running...") {
            conversation[assistantIndex] = {
              role: "assistant",
              content: "No final answer returned. Check events and prompt inspector."
            };
            renderConversation();
          }
          setRunStatus("Finished without final answer.");
          appendEventLine("Finished without final answer.");
        }
      } catch (error) {
        const messageText = error instanceof Error ? error.message : String(error);
        conversation[assistantIndex] = { role: "assistant", content: "Error: " + messageText };
        renderConversation();
        appendEventLine("Request exception: " + messageText);
        setRunStatus("Failed.");
        setRuntimeVerify("");
      } finally {
        sendBtn.disabled = false;
      }
    }

    sendBtn.addEventListener("click", async () => {
      await sendMessage();
    });

    composerEl.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        await sendMessage();
      }
    });

    resetBtn.addEventListener("click", () => {
      conversation = [];
      promptInspectors = [];
      selectedInspectorIndex = -1;
      renderConversation();
      renderPromptInspector();
      eventsEl.innerHTML = "";
      setRunStatus("Idle.");
      setTiming("");
      setRuntimeVerify("");
      appendEventLine("Conversation reset.");
    });

    modelsBtn.addEventListener("click", async () => {
      modelsBtn.disabled = true;
      appendEventLine("Loading Ollama models...");
      try {
        const url = "/api/models?ollama_chat_url=" + encodeURIComponent(ollamaChatUrlEl.value);
        const res = await fetchWithTimeout(url, {}, 20000);
        if (!res.ok) {
          const detail = await readErrorResponse(res);
          appendEventLine("Model load failed: " + detail);
          return;
        }
        const data = await res.json();
        if (Array.isArray(data.models) && data.models.length > 0) {
          modelEl.value = data.models[0];
        }
        appendEventLine("Models loaded.");
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        appendEventLine("Model load error: " + detail);
      } finally {
        modelsBtn.disabled = false;
      }
    });

    renderConversation();
    renderPromptInspector();
  </script>
</body>
</html>
"""
    return (
        html_template
        .replace("__MODEL_VALUE__", model_value)
        .replace("__MCP_URL_VALUE__", mcp_url_value)
        .replace("__OLLAMA_CHAT_URL_VALUE__", ollama_chat_url_value)
        .replace(
            "__INCLUDE_TAGS_IN_CONTEXT_WINDOW_VALUE__",
            include_tags_in_context_window_value,
        )
        .replace("__NUM_CTX_VALUE__", num_ctx_value)
        .replace(
            "__CONTEXT_WINDOW_MAX_CHARS_VALUE__",
            context_window_max_chars_value,
        )
    )


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

    def _render_home_legacy() -> str:
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

    def _render_home_v2() -> str:
        return _web_html_v2(
            default_model=default_model,
            default_mcp_url=default_mcp_url,
            default_ollama_chat_url=default_ollama_chat_url,
        )

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _render_home_legacy()

    @app.get("/v2", response_class=HTMLResponse)
    def home_v2() -> str:
        return _render_home_v2()

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
            worker_capture = _CapturedExceptionContext(Exception)
            result: dict | None = None
            with worker_capture:
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
            if worker_capture.captured_exception is not None:
                exc = worker_capture.captured_exception
                traceback.print_exception(exc)
                event_queue.put(
                    {
                        "type": "error",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                )
            else:
                if result is None:
                    raise RuntimeError("Rewrite worker did not produce a result")
                event_queue.put(
                    {
                        "type": "final",
                        "result": result,
                    }
                )
            worker_finished.set()
            event_queue.put({"type": "end"})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def event_stream():
            yield json.dumps({"type": "status", "status": "running", "detail": "Running..."}, ensure_ascii=False) + "\n"
            while True:
                event_capture = _CapturedExceptionContext(queue.Empty)
                event: dict | None = None
                with event_capture:
                    event = event_queue.get(timeout=1.0)
                if event_capture.captured_exception is not None:
                    if worker_finished.is_set():
                        continue
                    with heartbeat_lock:
                        latest_detail = _mapping_value_or_none(mapping=heartbeat_state, key="detail")
                        run_started_at = _mapping_value_or_none(
                            mapping=heartbeat_state,
                            key="run_started_at",
                        )
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
                if event is None:
                    raise RuntimeError("Event stream did not receive an event")
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

    @app.post("/api/chat_stream_v2")
    def chat_stream_v2(payload: AgentChatV2Request) -> StreamingResponse:
        if payload.message.strip() == "":
            raise HTTPException(status_code=400, detail="message must not be empty")
        if payload.context_window_max_chars <= 0:
            raise HTTPException(status_code=400, detail="context_window_max_chars must be > 0")
        if payload.context_window_max_chars > 5_000_000:
            raise HTTPException(
                status_code=400,
                detail="context_window_max_chars must be <= 5000000",
            )
        if payload.num_ctx <= 0:
            raise HTTPException(status_code=400, detail="num_ctx must be > 0")
        history_capture = _CapturedExceptionContext(ValueError)
        normalized_history: List[dict] | None = None
        with history_capture:
            normalized_history = _validate_v2_conversation_history(
                entries=payload.conversation_history
            )
        if history_capture.captured_exception is not None:
            exc = history_capture.captured_exception
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if normalized_history is None:
            raise RuntimeError("Conversation-history normalization did not return entries")

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
            worker_capture = _CapturedExceptionContext(Exception)
            result: dict | None = None
            with worker_capture:
                result = _run_context_window_request(
                    user_message=payload.message,
                    conversation_history=normalized_history,
                    context_window_max_chars=payload.context_window_max_chars,
                    num_ctx=payload.num_ctx,
                    include_tags_in_context_window=payload.include_tags_in_context_window,
                    mcp_url=payload.mcp_url,
                    ollama_chat_url=payload.ollama_chat_url,
                    model=payload.model,
                    progress_callback=progress_callback,
                    status_callback=status_callback,
                )
            if worker_capture.captured_exception is not None:
                exc = worker_capture.captured_exception
                traceback.print_exception(exc)
                event_queue.put(
                    {
                        "type": "error",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                )
            else:
                if result is None:
                    raise RuntimeError("Context-window worker did not produce a result")
                event_queue.put(
                    {
                        "type": "final",
                        "result": result,
                    }
                )
            worker_finished.set()
            event_queue.put({"type": "end"})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def event_stream():
            yield json.dumps(
                {"type": "status", "status": "running", "detail": "Running..."},
                ensure_ascii=False,
            ) + "\n"
            while True:
                event_capture = _CapturedExceptionContext(queue.Empty)
                event: dict | None = None
                with event_capture:
                    event = event_queue.get(timeout=1.0)
                if event_capture.captured_exception is not None:
                    if worker_finished.is_set():
                        continue
                    with heartbeat_lock:
                        latest_detail = _mapping_value_or_none(mapping=heartbeat_state, key="detail")
                        run_started_at = _mapping_value_or_none(
                            mapping=heartbeat_state,
                            key="run_started_at",
                        )
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
                if event is None:
                    raise RuntimeError("Event stream did not receive an event")
                if not isinstance(event, dict):
                    continue
                event_type = _mapping_value_or_none(mapping=event, key="type")
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
