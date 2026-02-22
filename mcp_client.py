from __future__ import annotations

import argparse
import difflib
import html
import json
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

    marker = f"... [truncated {len(collapsed) - max_chars} chars] ..."
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
    planner_seed_tag_limit: int
    planner_tag_count_mode: str
    mcp_url: str
    ollama_chat_url: str


def _web_html(
    *,
    default_model: str,
    default_max_steps: int,
    default_planner_seed_tag_limit: int,
    default_planner_tag_count_mode: str,
    default_mcp_url: str,
    default_ollama_chat_url: str,
) -> str:
    model_value = json.dumps(default_model)
    mcp_url_value = json.dumps(default_mcp_url)
    ollama_chat_url_value = json.dumps(default_ollama_chat_url)
    max_steps_value = str(default_max_steps)
    planner_seed_tag_limit_value = str(default_planner_seed_tag_limit)
    planner_tag_count_mode_raw_selected = "selected" if default_planner_tag_count_mode == "raw" else ""
    planner_tag_count_mode_effective_selected = (
        "selected" if default_planner_tag_count_mode == "effective" else ""
    )
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
      background: #0f1c36;
      color: #d8e6ff;
      border-radius: 8px;
      padding: 10px;
      margin: 0;
      max-height: 240px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.35;
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
          <label for="planner_seed_tag_limit">Planner seed tags (N)</label>
          <input id="planner_seed_tag_limit" type="number" min="1" value="{planner_seed_tag_limit_value}" />
        </div>
        <div>
          <label for="planner_tag_count_mode">Planner tag count mode</label>
          <select id="planner_tag_count_mode">
            <option value="raw" {planner_tag_count_mode_raw_selected}>raw (explicit only)</option>
            <option value="effective" {planner_tag_count_mode_effective_selected}>effective (inherited+implied)</option>
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
      <label for="prompt">Request</label>
      <textarea id="prompt" placeholder="Ask something, e.g. summarize top project notes tagged work..."></textarea>
      <div class="row">
        <button id="run_btn">Run Agent</button>
        <button id="models_btn" class="secondary">Load Ollama Models</button>
      </div>
      <p id="run_status" class="muted">Idle.</p>
      <h3>Final Answer</h3>
      <div id="final_answer" class="answer">No result yet.</div>
      <h3>Stages</h3>
      <div id="stage_list" class="stage-list">
        <p class="muted">No stages yet.</p>
      </div>
    </div>
  </div>
  <script>
    const finalAnswer = document.getElementById("final_answer");
    const runBtn = document.getElementById("run_btn");
    const modelsBtn = document.getElementById("models_btn");
    const runStatus = document.getElementById("run_status");
    const stageList = document.getElementById("stage_list");
    const promptEl = document.getElementById("prompt");
    const modelEl = document.getElementById("model");
    const maxStepsEl = document.getElementById("max_steps");
    const plannerSeedTagLimitEl = document.getElementById("planner_seed_tag_limit");
    const plannerTagCountModeEl = document.getElementById("planner_tag_count_mode");
    const mcpUrlEl = document.getElementById("mcp_url");
    const ollamaChatUrlEl = document.getElementById("ollama_chat_url");

    function print(obj) {{
      void obj;
    }}

    function setFinalAnswer(text) {{
      finalAnswer.textContent = text;
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
      if (step.model_payload && typeof step.model_payload === "object") {{
        const payload = step.model_payload;
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
          content = message.content;
        }} else {{
          content = JSON.stringify(message.content, null, 2);
        }}
        sections.push(`${{role}}:\\n${{content}}`);
      }}
      return sections.join("\\n\\n");
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
        promptPre.className = "stage-json";
        promptPre.textContent = formatPromptMessages(promptMessages);
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
      detail.textContent = JSON.stringify(step, null, 2);
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
      setRunStatus("Running...");
      resetStages();
      print({{ status: "running" }});
      try {{
        const payload = {{
          message: promptEl.value,
          model: modelEl.value,
          max_steps: Number(maxStepsEl.value),
          planner_seed_tag_limit: Number(plannerSeedTagLimitEl.value),
          planner_tag_count_mode: plannerTagCountModeEl.value,
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
              if (event.result && typeof event.result === "object") {{
                if (typeof event.result.answer === "string" && event.result.answer !== "") {{
                  answerText = event.result.answer;
                }}
              }}
              setFinalAnswer(answerText);
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
              setRunStatus("Failed.");
              continue;
            }}
            if (event.type === "status") {{
              runningState.status = event.status;
              if (event.status === "running") {{
                setFinalAnswer("Running...");
                setRunStatus("Running...");
              }}
              print(runningState);
            }}
          }}
        }}
        if (!sawFinal && !sawError) {{
          setFinalAnswer("No final answer returned. Check Stages for details.");
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
    default_planner_seed_tag_limit: int,
    default_planner_tag_count_mode: str,
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
            default_planner_seed_tag_limit=default_planner_seed_tag_limit,
            default_planner_tag_count_mode=default_planner_tag_count_mode,
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
        if payload.planner_seed_tag_limit <= 0:
            raise HTTPException(status_code=400, detail="planner_seed_tag_limit must be > 0")
        if payload.planner_tag_count_mode not in _ALLOWED_PLANNER_TAG_COUNT_MODES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "planner_tag_count_mode must be one of: "
                    + ", ".join(sorted(_ALLOWED_PLANNER_TAG_COUNT_MODES))
                ),
            )
        result = _run_agentic_request(
            user_message=payload.message,
            mcp_url=payload.mcp_url,
            ollama_chat_url=payload.ollama_chat_url,
            model=payload.model,
            max_steps=payload.max_steps,
            planner_only=True,
            planner_seed_tag_limit=payload.planner_seed_tag_limit,
            planner_tag_count_mode=payload.planner_tag_count_mode,
            progress_callback=None,
        )
        return result

    @app.post("/api/chat_stream")
    def chat_stream(payload: AgentChatRequest) -> StreamingResponse:
        if payload.message.strip() == "":
            raise HTTPException(status_code=400, detail="message must not be empty")
        if payload.max_steps <= 0:
            raise HTTPException(status_code=400, detail="max_steps must be > 0")
        if payload.planner_seed_tag_limit <= 0:
            raise HTTPException(status_code=400, detail="planner_seed_tag_limit must be > 0")
        if payload.planner_tag_count_mode not in _ALLOWED_PLANNER_TAG_COUNT_MODES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "planner_tag_count_mode must be one of: "
                    + ", ".join(sorted(_ALLOWED_PLANNER_TAG_COUNT_MODES))
                ),
            )

        event_queue: queue.Queue[dict] = queue.Queue()

        def progress_callback(step_record: dict) -> None:
            event_queue.put(
                {
                    "type": "step",
                    "step": step_record,
                }
            )

        def worker() -> None:
            try:
                result = _run_agentic_request(
                    user_message=payload.message,
                    mcp_url=payload.mcp_url,
                    ollama_chat_url=payload.ollama_chat_url,
                    model=payload.model,
                    max_steps=payload.max_steps,
                    planner_only=True,
                    planner_seed_tag_limit=payload.planner_seed_tag_limit,
                    planner_tag_count_mode=payload.planner_tag_count_mode,
                    progress_callback=progress_callback,
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
                event_queue.put({"type": "end"})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def event_stream():
            yield json.dumps({"type": "status", "status": "running"}, ensure_ascii=False) + "\n"
            while True:
                event = event_queue.get()
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
    planner_seed_tag_limit: int,
    planner_tag_count_mode: str,
) -> None:
    app = create_web_app(
        default_model=model,
        default_max_steps=max_steps,
        default_planner_seed_tag_limit=planner_seed_tag_limit,
        default_planner_tag_count_mode=planner_tag_count_mode,
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
    web_parser.add_argument("--planner-seed-tag-limit", type=int)
    web_parser.add_argument("--planner-tag-count-mode")

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

    if args.planner_seed_tag_limit is None:
        planner_seed_tag_limit = _DEFAULT_PLANNER_SEED_TAG_LIMIT
    else:
        planner_seed_tag_limit = args.planner_seed_tag_limit

    if args.planner_tag_count_mode is None:
        planner_tag_count_mode = _DEFAULT_PLANNER_TAG_COUNT_MODE
    else:
        planner_tag_count_mode = args.planner_tag_count_mode.casefold()
    if planner_tag_count_mode not in _ALLOWED_PLANNER_TAG_COUNT_MODES:
        raise ValueError(
            "planner-tag-count-mode must be one of: "
            + ", ".join(sorted(_ALLOWED_PLANNER_TAG_COUNT_MODES))
        )

    _run_web(
        host=host,
        port=port,
        mcp_url=mcp_url,
        ollama_chat_url=ollama_chat_url,
        model=model,
        max_steps=max_steps,
        planner_seed_tag_limit=planner_seed_tag_limit,
        planner_tag_count_mode=planner_tag_count_mode,
    )


if __name__ == "__main__":
    main()
