from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.usecases.update_content import apply_update_content
from app.usecases.delete_subtree import apply_delete_subtree, apply_restore_records
from app.usecases.move import apply_move
from app.services.store import store
import os
import logging
from app.services.sync import generate_new_uuid


def _normalize_viewport_snapshot(viewport: Dict[str, object]) -> Dict[str, object]:
    if not isinstance(viewport, dict):
        raise ValueError("viewport must be an object")
    if "scrollY" not in viewport:
        raise ValueError("viewport.scrollY is required")
    scroll_y = viewport["scrollY"]
    if not isinstance(scroll_y, int) or scroll_y < 0:
        raise ValueError("viewport.scrollY must be a non-negative integer")

    if "scrollAnchor" not in viewport:
        raise ValueError("viewport.scrollAnchor is required")
    scroll_anchor = viewport["scrollAnchor"]
    normalized_scroll_anchor: Optional[Dict[str, object]] = None
    if scroll_anchor is not None:
        if not isinstance(scroll_anchor, dict):
            raise ValueError("viewport.scrollAnchor must be an object or null")

        anchor_id = scroll_anchor.get("anchorId")
        anchor_bias = scroll_anchor.get("anchorBias")
        intra_offset = scroll_anchor.get("intraOffset")
        belt_prev = scroll_anchor.get("beltPrev")
        belt_next = scroll_anchor.get("beltNext")
        anchor_sort_key = scroll_anchor.get("anchorSortKey")

        if not isinstance(anchor_id, str) or not anchor_id:
            raise ValueError("viewport.scrollAnchor.anchorId must be a non-empty string")
        if anchor_bias not in ("center", "top"):
            raise ValueError("viewport.scrollAnchor.anchorBias must be 'center' or 'top'")
        if not isinstance(intra_offset, int) or intra_offset < 0:
            raise ValueError("viewport.scrollAnchor.intraOffset must be a non-negative integer")
        if not isinstance(belt_prev, list) or not isinstance(belt_next, list):
            raise ValueError("viewport.scrollAnchor belt arrays must be lists")

        def _normalize_belt(payload: List[object]) -> List[str]:
            return [entry for entry in payload if isinstance(entry, str) and entry]

        normalized_prev = _normalize_belt(belt_prev)
        normalized_next = _normalize_belt(belt_next)

        if not isinstance(anchor_sort_key, dict):
            raise ValueError("viewport.scrollAnchor.anchorSortKey must be an object")
        dom_index = anchor_sort_key.get("domIndex")
        if not isinstance(dom_index, int) or dom_index < 0:
            raise ValueError("viewport.scrollAnchor.anchorSortKey.domIndex must be a non-negative integer")

        normalized_scroll_anchor = {
            "anchorId": anchor_id,
            "anchorBias": anchor_bias,
            "intraOffset": intra_offset,
            "beltPrev": normalized_prev,
            "beltNext": normalized_next,
            "anchorSortKey": {"domIndex": dom_index},
        }

    return {"scrollY": scroll_y, "scrollAnchor": normalized_scroll_anchor}


def _anchor_root_id(viewport: Dict[str, object]) -> Optional[str]:
    scroll_anchor = viewport.get("scrollAnchor")
    if not isinstance(scroll_anchor, dict):
        return None
    anchor_id = scroll_anchor.get("anchorId")
    if isinstance(anchor_id, str) and anchor_id:
        return anchor_id
    return None


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


def record_update(client_id: str, note_id: str, *, before: str, after: str, viewport: Dict[str, object]) -> None:
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "update_content",
        "note_id": note_id,
        "before": before,
        "after": after,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def record_create(client_id: str, record: dict, *, viewport: Dict[str, object]) -> None:
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "create_note",
        "record": record,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def record_delete(client_id: str, records: List[NodeRecord], *, viewport: Dict[str, object]) -> None:
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "delete_subtree",
        "records": records,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
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
    viewport: Dict[str, object],
) -> None:
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "move",
        "note_id": note_id,
        "before_parent": before_parent,
        "before_prev": before_prev,
        "before_next": before_next,
        "after_parent": after_parent,
        "after_prev": after_prev,
        "after_next": after_next,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
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


def record_collapse(
    client_id: str,
    note_id: str,
    *,
    before: bool,
    after: bool,
    viewport: Dict[str, object],
) -> None:
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "collapse",
        "note_id": note_id,
        "before": bool(before),
        "after": bool(after),
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def record_paste(client_id: str, records: List[NodeRecord], *, viewport: Dict[str, object]) -> None:
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "paste_subtree",
        "records": records,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def maybe_reset_on_context(client_id: str, search_context: Optional[str]) -> None:
    ctx = _ctx(client_id)
    sc = search_context or ""
    if ctx.last_search_context != sc:
        ctx.history.clear()
        ctx.redo.clear()
        ctx.last_search_context = sc


def undo(client_id: str) -> Optional[Dict[str, object]]:
    ctx = _ctx(client_id)
    if not ctx.history:
        return None
    op = ctx.history.pop()
    undo_viewport = op["viewport"]
    view_anchor_root_id = op.get("viewAnchorRootId")
    if op.get("type") == "update_content":
        apply_update_content(op["note_id"], op["before"])  # apply inverse
        ctx.redo.append(op)
        generate_new_uuid()
        return {**undo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "create_note":
        rec = op["record"]
        apply_delete_subtree(rec["id"])  # delete the created note
        ctx.redo.append(op)
        generate_new_uuid()
        return {**undo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "delete_subtree":
        records = op["records"]
        apply_restore_records(records)
        ctx.redo.append(op)
        generate_new_uuid()
        return {**undo_viewport, "viewAnchorRootId": view_anchor_root_id}
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
        return {**undo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "collapse":
        # invert collapse
        from app.usecases.collapse import apply_set_collapse
        apply_set_collapse(op["note_id"], bool(op["before"]))
        ctx.redo.append(op)
        generate_new_uuid()
        return {**undo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "paste_subtree":
        # delete the pasted subtree
        root_id = op["records"][0].id if op["records"] else None
        if not root_id:
            print("FATAL: paste_subtree undo missing root record")
            os._exit(1)
        apply_delete_subtree(root_id)
        ctx.redo.append(op)
        generate_new_uuid()
        return {**undo_viewport, "viewAnchorRootId": view_anchor_root_id}
    raise RuntimeError(f"Unsupported undo op: {op.get('type')}")


def redo(client_id: str) -> Optional[Dict[str, object]]:
    ctx = _ctx(client_id)
    if not ctx.redo:
        return None
    op = ctx.redo.pop()
    redo_viewport = op["viewport"]
    view_anchor_root_id = op.get("viewAnchorRootId")
    if op.get("type") == "update_content":
        apply_update_content(op["note_id"], op["after"])  # reapply
        ctx.history.append(op)
        generate_new_uuid()
        return {**redo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "create_note":
        # recreate
        rec = op["record"]
        from app.services.store import NodeRecord
        apply_restore_records([NodeRecord(**rec)])
        ctx.history.append(op)
        generate_new_uuid()
        return {**redo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "delete_subtree":
        # re-delete
        first = op["records"][0]
        apply_delete_subtree(first.id)
        ctx.history.append(op)
        generate_new_uuid()
        return {**redo_viewport, "viewAnchorRootId": view_anchor_root_id}
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
        return {**redo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "collapse":
        from app.usecases.collapse import apply_set_collapse
        apply_set_collapse(op["note_id"], bool(op["after"]))
        ctx.history.append(op)
        generate_new_uuid()
        return {**redo_viewport, "viewAnchorRootId": view_anchor_root_id}
    if op.get("type") == "paste_subtree":
        # restore the subtree
        apply_restore_records(op["records"])  
        ctx.history.append(op)
        generate_new_uuid()
        return {**redo_viewport, "viewAnchorRootId": view_anchor_root_id}
    raise RuntimeError(f"Unsupported redo op: {op.get('type')}")
