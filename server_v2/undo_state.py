from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from server_v2.endpoints.update_content import apply_update_content
from server_v2.sync import generate_new_uuid


@dataclass
class _ClientUndo:
    history: List[dict] = field(default_factory=list)  # list of ops
    redo: List[dict] = field(default_factory=list)
    last_search_context: str = ""


_clients: Dict[str, _ClientUndo] = {}


def _ctx(client_id: str) -> _ClientUndo:
    if client_id not in _clients:
        _clients[client_id] = _ClientUndo()
    return _clients[client_id]


def record_update(client_id: str, note_id: str, *, before: str, after: str) -> None:
    ctx = _ctx(client_id)
    ctx.history.append({
        "type": "update_content",
        "note_id": note_id,
        "before": before,
        "after": after,
    })
    ctx.redo.clear()


def maybe_reset_on_context(client_id: str, search_context: Optional[str]) -> None:
    ctx = _ctx(client_id)
    sc = search_context or ""
    if ctx.last_search_context != sc:
        ctx.history.clear()
        ctx.redo.clear()
        ctx.last_search_context = sc


def undo(client_id: str) -> bool:
    ctx = _ctx(client_id)
    if not ctx.history:
        return False
    op = ctx.history.pop()
    if op.get("type") == "update_content":
        apply_update_content(op["note_id"], op["before"])  # apply inverse
        ctx.redo.append(op)
        generate_new_uuid()
        return True
    raise RuntimeError(f"Unsupported undo op: {op.get('type')}")


def redo(client_id: str) -> bool:
    ctx = _ctx(client_id)
    if not ctx.redo:
        return False
    op = ctx.redo.pop()
    if op.get("type") == "update_content":
        apply_update_content(op["note_id"], op["after"])  # reapply
        ctx.history.append(op)
        generate_new_uuid()
        return True
    raise RuntimeError(f"Unsupported redo op: {op.get('type')}")

