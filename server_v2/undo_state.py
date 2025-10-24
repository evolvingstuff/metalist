from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from server_v2.endpoints.update_content import apply_update_content
from server_v2.endpoints.delete_subtree import apply_delete_subtree, apply_restore_records
from server_v2.endpoints.move import apply_move
from server_v2.store import store
import os
import logging
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


def record_create(client_id: str, record: dict) -> None:
    ctx = _ctx(client_id)
    ctx.history.append({
        "type": "create_note",
        "record": record,
    })
    ctx.redo.clear()


def record_delete(client_id: str, records: List[NodeRecord]) -> None:
    ctx = _ctx(client_id)
    ctx.history.append({
        "type": "delete_subtree",
        "records": records,
    })
    ctx.redo.clear()


def record_move(
    client_id: str,
    note_id: str,
    *,
    before_parent: Optional[str],
    before_prev: Optional[str],
    before_next: Optional[str],
    after_parent: Optional[str],
    after_prev: Optional[str],
    after_next: Optional[str],
) -> None:
    ctx = _ctx(client_id)
    ctx.history.append({
        "type": "move",
        "note_id": note_id,
        "before_parent": before_parent,
        "before_prev": before_prev,
        "before_next": before_next,
        "after_parent": after_parent,
        "after_prev": after_prev,
        "after_next": after_next,
    })
    ctx.redo.clear()


def _assert_neighbors(note_id: str, exp_parent: Optional[str], exp_prev: Optional[str], exp_next: Optional[str]) -> None:
    parent_id = store.get(note_id).parent_id
    links = store._links.get(parent_id) or {}  # type: ignore[attr-defined]
    cur = links.get(note_id, {})
    prev_id = cur.get('prev')
    next_id = cur.get('next')
    if parent_id != exp_parent or prev_id != exp_prev or next_id != exp_next:
        logging.error(
            "FATAL: undo/redo move invariant failed for %s | expected parent=%s prev=%s next=%s | actual parent=%s prev=%s next=%s",
            note_id, exp_parent, exp_prev, exp_next, parent_id, prev_id, next_id,
        )
        os._exit(1)


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
    if op.get("type") == "create_note":
        rec = op["record"]
        apply_delete_subtree(rec["id"])  # delete the created note
        ctx.redo.append(op)
        generate_new_uuid()
        return True
    if op.get("type") == "delete_subtree":
        records = op["records"]
        apply_restore_records(records)
        ctx.redo.append(op)
        generate_new_uuid()
        return True
    if op.get("type") == "move":
        apply_move(
            op["note_id"],
            op["before_parent"],
            op["before_prev"],
            op["before_next"],
        )
        _assert_neighbors(op["note_id"], op["before_parent"], op["before_prev"], op["before_next"]) 
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
    if op.get("type") == "create_note":
        # recreate
        rec = op["record"]
        from server_v2.store import NodeRecord
        apply_restore_records([NodeRecord(**rec)])
        ctx.history.append(op)
        generate_new_uuid()
        return True
    if op.get("type") == "delete_subtree":
        # re-delete
        first = op["records"][0]
        apply_delete_subtree(first.id)
        ctx.history.append(op)
        generate_new_uuid()
        return True
    if op.get("type") == "move":
        apply_move(
            op["note_id"],
            op["after_parent"],
            op["after_prev"],
            op["after_next"],
        )
        _assert_neighbors(op["note_id"], op["after_parent"], op["after_prev"], op["after_next"]) 
        ctx.history.append(op)
        generate_new_uuid()
        return True
    raise RuntimeError(f"Unsupported redo op: {op.get('type')}")
