from __future__ import annotations

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
    scroll_anchor = viewport["scrollAnchor"]
    if not isinstance(scroll_anchor, dict):
        return None
    anchor_id = scroll_anchor.get("anchorId")
    if isinstance(anchor_id, str) and anchor_id:
        return anchor_id
    return None


def _root_ancestor_id(note_id: str) -> str:
    current = store.get(note_id)
    while current.parent_id:
        current = store.get(current.parent_id)
    return current.id


def _pick_focus_neighbor(prev_id: Optional[str], next_id: Optional[str]) -> str:
    for candidate in (next_id, prev_id):
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def _compute_focus_note_id(op: dict, *, direction: str) -> str:
    if "type" not in op:
        raise RuntimeError(f"Redo op missing required key: type | op={op}")
    op_type = op["type"]

    if op_type in {"update_content", "move", "collapse"}:
        if "note_id" not in op:
            raise RuntimeError(f"Undo op missing required key: note_id | op={op}")
        note_id = op["note_id"]
        if not isinstance(note_id, str) or not note_id:
            raise RuntimeError(f"Undo op note_id must be a non-empty string | op={op}")
        return note_id

    if op_type == "edit_mode":
        if "before_editing_note_id" not in op:
            raise RuntimeError(f"Undo op edit_mode missing required key: before_editing_note_id | op={op}")
        if "after_editing_note_id" not in op:
            raise RuntimeError(f"Undo op edit_mode missing required key: after_editing_note_id | op={op}")
        before_editing_note_id = op["before_editing_note_id"]
        after_editing_note_id = op["after_editing_note_id"]
        if before_editing_note_id is not None and not isinstance(before_editing_note_id, str):
            raise RuntimeError(f"Undo op edit_mode.before_editing_note_id must be a string or null | op={op}")
        if after_editing_note_id is not None and not isinstance(after_editing_note_id, str):
            raise RuntimeError(f"Undo op edit_mode.after_editing_note_id must be a string or null | op={op}")

        if direction == "undo":
            if isinstance(before_editing_note_id, str) and before_editing_note_id:
                return before_editing_note_id
            if isinstance(after_editing_note_id, str) and after_editing_note_id:
                return after_editing_note_id
            return ""

        if isinstance(after_editing_note_id, str) and after_editing_note_id:
            return after_editing_note_id
        if isinstance(before_editing_note_id, str) and before_editing_note_id:
            return before_editing_note_id
        return ""

    if op_type == "create_note":
        record = op["record"]
        if not isinstance(record, dict):
            raise RuntimeError(f"Undo op create_note.record must be an object | op={op}")
        created_id = record.get("id")
        if direction == "redo" and isinstance(created_id, str):
            return created_id
        return _pick_focus_neighbor(record.get("prev_id"), record.get("next_id"))

    if op_type in {"delete_subtree", "paste_subtree"}:
        records = op["records"]
        if not isinstance(records, list) or not records:
            raise RuntimeError(f"Undo op {op_type}.records must be a non-empty list | op={op}")
        first = records[0]
        root_id = getattr(first, "id", None)
        if root_id is None:
            raise RuntimeError(f"Undo op {op_type}.records[0] missing id | op={op}")
        if not isinstance(root_id, str) or not root_id:
            raise RuntimeError(f"Undo op {op_type}.records[0].id must be a non-empty string | op={op}")
        if direction == "redo" and op_type == "delete_subtree":
            return _pick_focus_neighbor(getattr(first, "prev_id", None), getattr(first, "next_id", None))
        if direction == "undo" and op_type == "paste_subtree":
            prev_id = getattr(first, "prev_id", None)
            if isinstance(prev_id, str) and prev_id:
                return prev_id
            parent_id = getattr(first, "parent_id", None)
            if isinstance(parent_id, str) and parent_id:
                return parent_id
            next_id = getattr(first, "next_id", None)
            if isinstance(next_id, str) and next_id:
                return next_id
            return ""
        return root_id

    return ""


class _ClientUndo:
    __slots__ = ("history", "redo", "last_undo_context")

    def __init__(self) -> None:
        self.history: List[dict] = []
        self.redo: List[dict] = []
        self.last_undo_context: str = ""


_clients: Dict[str, _ClientUndo] = {}


def _ctx(client_id: str) -> _ClientUndo:
    if client_id not in _clients:
        _clients[client_id] = _ClientUndo()
    return _clients[client_id]


def record_update(
    client_id: str,
    undo_context: str,
    note_id: str,
    *,
    before: str,
    after: str,
    before_tags: str,
    after_tags: str,
    viewport: Dict[str, object],
) -> None:
    maybe_reset_on_context(client_id, undo_context)
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "update_content",
        "note_id": note_id,
        "before": before,
        "after": after,
        "before_tags": before_tags,
        "after_tags": after_tags,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def record_create(client_id: str, undo_context: str, record: dict, *, viewport: Dict[str, object]) -> None:
    maybe_reset_on_context(client_id, undo_context)
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


def record_delete(
    client_id: str,
    undo_context: str,
    records: List[NodeRecord],
    *,
    viewport: Dict[str, object],
) -> None:
    maybe_reset_on_context(client_id, undo_context)
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
    undo_context: str,
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
    maybe_reset_on_context(client_id, undo_context)
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
    links = store._links.get(parent_id)  # type: ignore[attr-defined]
    if links is None:
        raise RuntimeError(f"Missing link scope for parent_id={parent_id}")
    cur = links.get(note_id)
    if cur is None:
        raise RuntimeError(f"Missing note_id={note_id} in links for parent_id={parent_id}")
    if 'prev' not in cur or 'next' not in cur:
        raise RuntimeError(f"Malformed link entry for note_id={note_id} parent_id={parent_id}: {cur}")
    prev_id = cur['prev']
    next_id = cur['next']
    if parent_id != exp_parent or prev_id != exp_prev or next_id != exp_next:
        logging.error(
            "FATAL: undo/redo move invariant failed for %s | expected parent=%s prev=%s next=%s | actual parent=%s prev=%s next=%s",
            note_id, exp_parent, exp_prev, exp_next, parent_id, prev_id, next_id,
        )
        os._exit(1)


def record_collapse(
    client_id: str,
    undo_context: str,
    note_id: str,
    *,
    before: bool,
    after: bool,
    viewport: Dict[str, object],
) -> None:
    maybe_reset_on_context(client_id, undo_context)
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


def record_paste(
    client_id: str,
    undo_context: str,
    records: List[NodeRecord],
    *,
    viewport: Dict[str, object],
) -> None:
    maybe_reset_on_context(client_id, undo_context)
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


def record_edit_mode(
    client_id: str,
    undo_context: str,
    *,
    before_editing_note_id: Optional[str],
    after_editing_note_id: Optional[str],
    viewport: Dict[str, object],
) -> None:
    if before_editing_note_id is not None and (not isinstance(before_editing_note_id, str) or not before_editing_note_id):
        raise ValueError("before_editing_note_id must be a non-empty string or null")
    if after_editing_note_id is not None and (not isinstance(after_editing_note_id, str) or not after_editing_note_id):
        raise ValueError("after_editing_note_id must be a non-empty string or null")

    maybe_reset_on_context(client_id, undo_context)
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "edit_mode",
        "before_editing_note_id": before_editing_note_id,
        "after_editing_note_id": after_editing_note_id,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def maybe_reset_on_context(client_id: str, undo_context: str) -> None:
    ctx = _ctx(client_id)
    if not isinstance(undo_context, str):
        raise TypeError("undo_context must be a string")
    if undo_context == "":
        raise ValueError("undo_context must be a non-empty string")

    if ctx.last_undo_context != undo_context:
        ctx.history.clear()
        ctx.redo.clear()
        ctx.last_undo_context = undo_context


def undo(client_id: str, token: str) -> Optional[Dict[str, object]]:
    ctx = _ctx(client_id)
    if not ctx.history:
        return None
    op = ctx.history.pop()
    undo_viewport = op["viewport"]

    if "type" not in op:
        raise RuntimeError(f"Undo op missing required key: type | op={op}")
    op_type = op["type"]

    if op_type == "update_content":
        apply_update_content(op["note_id"], op["before"], op["before_tags"], token)  # apply inverse
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "create_note":
        rec = op["record"]
        apply_delete_subtree(rec["id"])  # delete the created note
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "delete_subtree":
        records = op["records"]
        apply_restore_records(records, token)
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "move":
        apply_move(
            op["note_id"],
            op["before_parent"],
            op["before_prev"],
            op["before_next"],
        )
        _assert_neighbors(op["note_id"], op["before_parent"], op["before_prev"], op["before_next"]) 
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "collapse":
        # invert collapse
        from app.usecases.collapse import apply_set_collapse
        apply_set_collapse(op["note_id"], bool(op["before"]))
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "paste_subtree":
        # delete the pasted subtree
        if op["records"]:
            root_id = op["records"][0].id
        else:
            root_id = None
        if not root_id:
            print("FATAL: paste_subtree undo missing root record")
            os._exit(1)
        apply_delete_subtree(root_id)
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "edit_mode":
        ctx.redo.append(op)
    else:
        raise RuntimeError(f"Unsupported undo op: {op_type}")

    editing_note_id = None
    if op_type == "edit_mode":
        editing_note_id = op["before_editing_note_id"]
        if editing_note_id is not None and (not isinstance(editing_note_id, str) or not editing_note_id):
            raise RuntimeError(f"Undo op edit_mode.before_editing_note_id must be a non-empty string or null | op={op}")

    focus_note_id = _compute_focus_note_id(op, direction="undo")
    if focus_note_id:
        view_anchor_root_id = _root_ancestor_id(focus_note_id)
    else:
        view_anchor_root_id = op["viewAnchorRootId"]
    payload = {
        **undo_viewport,
        "opType": op_type,
        "viewAnchorRootId": view_anchor_root_id,
        "focusNoteId": focus_note_id,
    }
    if op_type == "edit_mode":
        payload["editingNoteId"] = editing_note_id
    return payload


def redo(client_id: str, token: str) -> Optional[Dict[str, object]]:
    ctx = _ctx(client_id)
    if not ctx.redo:
        return None
    op = ctx.redo.pop()
    redo_viewport = op["viewport"]

    if "type" not in op:
        raise RuntimeError(f"Undo op missing required key: type | op={op}")
    op_type = op["type"]

    if op_type == "update_content":
        apply_update_content(op["note_id"], op["after"], op["after_tags"], token)  # reapply
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "create_note":
        # recreate
        rec = op["record"]
        from app.services.store import NodeRecord
        apply_restore_records([NodeRecord(**rec)], token)
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "delete_subtree":
        # re-delete
        first = op["records"][0]
        apply_delete_subtree(first.id)
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "move":
        apply_move(
            op["note_id"],
            op["after_parent"],
            op["after_prev"],
            op["after_next"],
        )
        _assert_neighbors(op["note_id"], op["after_parent"], op["after_prev"], op["after_next"]) 
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "collapse":
        from app.usecases.collapse import apply_set_collapse
        apply_set_collapse(op["note_id"], bool(op["after"]))
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "paste_subtree":
        # restore the subtree
        apply_restore_records(op["records"], token)
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "edit_mode":
        ctx.history.append(op)
    else:
        raise RuntimeError(f"Unsupported redo op: {op_type}")

    editing_note_id = None
    if op_type == "edit_mode":
        editing_note_id = op["after_editing_note_id"]
        if editing_note_id is not None and (not isinstance(editing_note_id, str) or not editing_note_id):
            raise RuntimeError(f"Redo op edit_mode.after_editing_note_id must be a non-empty string or null | op={op}")

    focus_note_id = _compute_focus_note_id(op, direction="redo")
    if focus_note_id:
        view_anchor_root_id = _root_ancestor_id(focus_note_id)
    else:
        view_anchor_root_id = op["viewAnchorRootId"]
    payload = {
        **redo_viewport,
        "opType": op_type,
        "viewAnchorRootId": view_anchor_root_id,
        "focusNoteId": focus_note_id,
    }
    if op_type == "edit_mode":
        payload["editingNoteId"] = editing_note_id
    return payload
