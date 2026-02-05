#!/usr/bin/env python3
"""
onefile_mcp_ollama_demo.py

Single-file demo: Ollama (model) + MCP (tools) + orchestrator loop.

Run:
  ollama serve
  ollama pull llama3.2
  python3 -m pip install mcp httpx
  python3 onefile_mcp_ollama_demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# -------------------------
# Config
# -------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
TOOL_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


# -------------------------
# MCP SERVER
# -------------------------
mcp = FastMCP("One-File MCP Demo", json_response=True)

@dataclass
class Note:
    id: str
    title: str
    body: str
    tags: List[str]
    created_at: float

NOTES: Dict[str, Note] = {}

def _new_id() -> str:
    return str(uuid.uuid4())

def _normalize_limit(limit: Optional[int]) -> int:
    """
    Normalize "limit" coming from an LLM/tool-call.
    Accepts None/0/negative/huge and turns it into 1..50.
    """
    if limit is None:
        limit = 10
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 10
    if limit_i <= 0:
        limit_i = 10
    return max(1, min(limit_i, 50))

@mcp.tool()
def add_note(title: str, body: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Create a note (in memory).

    Semantics:
    - Use this when the user asks to add/create/remember something.
    - tags are optional; omit tags if unsure.
    """
    nid = _new_id()
    NOTES[nid] = Note(
        id=nid,
        title=title.strip(),
        body=body,
        tags=[t.strip() for t in (tags or []) if t.strip()],
        created_at=time.time(),
    )
    return {"id": nid}

@mcp.tool()
def list_notes(limit: Optional[int] = None) -> Dict[str, Any]:
    """
    List notes (newest first).

    Semantics:
    - Use this when the user asks “what notes do we have?” / “show my notes”.
    - limit is optional. If omitted or null, defaults to 10.
    - limit <= 0 is treated as default.
    - limit is clamped to 1..50.
    - If user asks “how many notes?”, use count_notes() instead.
    """
    limit_n = _normalize_limit(limit)
    items = sorted(NOTES.values(), key=lambda n: n.created_at, reverse=True)[:limit_n]
    return {"notes": [{"id": n.id, "title": n.title, "tags": n.tags} for n in items]}

@mcp.tool()
def count_notes() -> Dict[str, Any]:
    """
    Return the total number of notes.

    Semantics:
    - Use this for “how many notes do we have?”
    - Do NOT use list_notes() + count; this is exact and simpler.
    """
    return {"count": len(NOTES)}

@mcp.tool()
def get_note(note_id: str) -> Dict[str, Any]:
    """
    Fetch one note by id.
    """
    note = NOTES.get(note_id)
    if not note:
        return {"error": "not_found", "note_id": note_id}
    return asdict(note)


# -------------------------
# OLLAMA HELPER
# -------------------------
async def ollama_generate(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        )
        r.raise_for_status()
        return r.json().get("response", "")

def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    m = TOOL_JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# -------------------------
# CLIENT / ORCHESTRATOR
# -------------------------
async def run_client() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.abspath(__file__), "--server"],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("✅ Connected to MCP server (same file).")
            print(f"✅ Ollama model: {OLLAMA_MODEL}")
            print("Type something, or 'quit'.\n")

            while True:
                user = input("> ").strip()
                if not user:
                    continue
                if user.lower() in {"quit", "exit"}:
                    break

                # Force one tool call per user input (demo mode).
                tool_prompt = f"""
You must choose ONE tool call.

Tools:
- count_notes()
- list_notes(limit?: number)   // limit optional; omit if unsure
- add_note(title, body, tags?)
- get_note(note_id)

User request:
{user}

Return ONLY JSON:
{{"tool": "...", "args": {{...}}}}

Rules:
- Only JSON.
- Omit args you don't know (don't use null/0 unless user explicitly gave a number).
"""

                model_out = await ollama_generate(tool_prompt)
                call = extract_json_object(model_out)

                if not call or "tool" not in call or "args" not in call:
                    print("\n❌ Model did not return valid tool JSON:")
                    print(model_out.strip(), "\n")
                    continue

                tool = call["tool"]
                args = call["args"]
                if not isinstance(args, dict):
                    args = {}

                try:
                    result = await session.call_tool(tool, args)
                except Exception as e:
                    print(f"\n❌ Tool call failed: {e}\n")
                    continue

                texts: List[str] = []
                for c in (result.content or []):
                    t = getattr(c, "text", None)
                    if t is not None:
                        texts.append(t)

                tool_payload = {"tool": tool, "args": args, "result": texts}

                print("\n--- MCP TOOL RESULT ---")
                print(json.dumps(tool_payload, indent=2))

                final_prompt = f"""
User request:
{user}

Tool result:
{json.dumps(tool_payload, indent=2)}

Reply in ONE short sentence.
"""
                final = await ollama_generate(final_prompt)
                print("\n--- MODEL FINAL ---")
                print(final.strip(), "\n")


# -------------------------
# ENTRYPOINT
# -------------------------
def main() -> None:
    if "--server" in sys.argv:
        mcp.run()
    else:
        asyncio.run(run_client())

if __name__ == "__main__":
    main()
