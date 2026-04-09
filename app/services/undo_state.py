from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from typing import Dict, List, Optional

from app.usecases.collapse import apply_set_collapse
from app.usecases.delete_subtree import apply_delete_subtree, apply_restore_records
from app.usecases.move import apply_move
from app.usecases.update_content import apply_update_content
from app.services.store import store, NodeRecord
from app.services.sync import generate_new_uuid


logger = logging.getLogger(__name__)


def _summarize_op(op: dict) -> str:
    if not isinstance(op, dict):
        raise TypeError(f"Undo op must be a dict, got {type(op)}")
    if "type" not in op:
        raise RuntimeError(f"Undo op missing required key 'type' | op={op}")

    op_type = op["type"]
    if not isinstance(op_type, str) or not op_type:
        raise RuntimeError(f"Undo op type must be a non-empty string | op={op}")

    if op_type == "edit_mode":
        before = op["before_editing_note_id"]
        after = op["after_editing_note_id"]
        if before is not None and (not isinstance(before, str) or not before):
            raise RuntimeError(
                f"Undo op edit_mode.before_editing_note_id must be a non-empty string or null | op={op}"
            )
        if after is not None and (not isinstance(after, str) or not after):
            raise RuntimeError(
                f"Undo op edit_mode.after_editing_note_id must be a non-empty string or null | op={op}"
            )
        return f"edit_mode({before}->{after})"

    if op_type in {"update_content", "move", "collapse", "paste_into", "join_next"}:
        note_id = op["note_id"]
        if not isinstance(note_id, str) or not note_id:
            raise RuntimeError(f"Undo op {op_type}.note_id must be a non-empty string | op={op}")
        return f"{op_type}({note_id})"

    if op_type == "create_note":
        record = op["record"]
        if not isinstance(record, dict):
            raise RuntimeError(f"Undo op create_note.record must be a dict | op={op}")
        if "id" not in record:
            raise RuntimeError(f"Undo op create_note.record missing id | op={op}")
        created_id = record["id"]
        if not isinstance(created_id, str) or not created_id:
            raise RuntimeError(
                f"Undo op create_note.record.id must be a non-empty string | op={op}"
            )
        return f"create_note({created_id})"

    if op_type in {"delete_subtree", "paste_subtree"}:
        records = op["records"]
        if not isinstance(records, list) or not records:
            raise RuntimeError(f"Undo op {op_type}.records must be a non-empty list | op={op}")
        root_id = records[0].id
        if not isinstance(root_id, str) or not root_id:
            raise RuntimeError(f"Undo op {op_type}.records[0].id must be a non-empty string | op={op}")
        return f"{op_type}({root_id})"

    return op_type


def _summarize_stack(ops: List[dict], max_items: int) -> str:
    if not isinstance(max_items, int) or max_items <= 0:
        raise ValueError("max_items must be a positive integer")
    start = max(0, len(ops) - max_items)
    return "[" + ", ".join(_summarize_op(op) for op in ops[start:]) + "]"


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

        if "anchorId" not in scroll_anchor:
            raise ValueError("viewport.scrollAnchor.anchorId is required")
        if "anchorBias" not in scroll_anchor:
            raise ValueError("viewport.scrollAnchor.anchorBias is required")
        if "intraOffset" not in scroll_anchor:
            raise ValueError("viewport.scrollAnchor.intraOffset is required")
        if "beltPrev" not in scroll_anchor:
            raise ValueError("viewport.scrollAnchor.beltPrev is required")
        if "beltNext" not in scroll_anchor:
            raise ValueError("viewport.scrollAnchor.beltNext is required")
        if "anchorSortKey" not in scroll_anchor:
            raise ValueError("viewport.scrollAnchor.anchorSortKey is required")

        anchor_id = scroll_anchor["anchorId"]
        anchor_bias = scroll_anchor["anchorBias"]
        intra_offset = scroll_anchor["intraOffset"]
        belt_prev = scroll_anchor["beltPrev"]
        belt_next = scroll_anchor["beltNext"]
        anchor_sort_key = scroll_anchor["anchorSortKey"]

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
        if "domIndex" not in anchor_sort_key:
            raise ValueError("viewport.scrollAnchor.anchorSortKey.domIndex is required")
        dom_index = anchor_sort_key["domIndex"]
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
    if "anchorId" not in scroll_anchor:
        return None
    anchor_id = scroll_anchor["anchorId"]
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

    if op_type in {"update_content", "move", "collapse", "paste_into", "join_next"}:
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
        if "id" not in record:
            raise RuntimeError(f"Undo op create_note.record missing id | op={op}")
        created_id = record["id"]
        if direction == "redo" and isinstance(created_id, str):
            return created_id
        if "parent_id" not in record:
            raise RuntimeError(f"Undo op create_note.record missing parent_id | op={op}")

        if not isinstance(created_id, str) or not created_id:
            raise RuntimeError(f"Undo op create_note.record.id must be a non-empty string | op={op}")
        parent_id = record["parent_id"]

        if "prev_id" not in record:
            raise RuntimeError(f"Undo op create_note.record missing prev_id | op={op}")
        prev_id = record["prev_id"]
        if prev_id is not None and not isinstance(prev_id, str):
            raise RuntimeError(f"Undo op create_note.record.prev_id must be a string or null | op={op}")

        if prev_id is not None and not isinstance(prev_id, str):
            raise RuntimeError(f"Undo op create_note.record.prev_id must be a string or null | op={op}")
        if parent_id is not None and not isinstance(parent_id, str):
            raise RuntimeError(f"Undo op create_note.record.parent_id must be a string or null | op={op}")

        # Undoing a create should usually return focus to:
        # - the reference note (sibling creation): prev_id is set
        # - the parent note (child creation): parent_id is set and prev_id is null
        # - nothing (root creation from empty selection): parent_id is null and prev_id is null
        if isinstance(prev_id, str) and prev_id:
            return prev_id
        if isinstance(parent_id, str) and parent_id:
            logger.info(
                "undo.create_note focus parent: created_id=%s parent_id=%s",
                created_id,
                parent_id,
            )
            return parent_id
        return ""

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
    before_tags: str,
    after_parent: Optional[str],
    after_prev: Optional[str],
    after_next: Optional[str],
    after_tags: str,
    viewport: Dict[str, object],
) -> None:
    maybe_reset_on_context(client_id, undo_context)
    ctx = _ctx(client_id)
    if not isinstance(before_tags, str):
        raise TypeError("before_tags must be a string")
    if not isinstance(after_tags, str):
        raise TypeError("after_tags must be a string")
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "move",
        "note_id": note_id,
        "before_parent": before_parent,
        "before_prev": before_prev,
        "before_next": before_next,
        "before_tags": before_tags,
        "after_parent": after_parent,
        "after_prev": after_prev,
        "after_next": after_next,
        "after_tags": after_tags,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def _assert_neighbors(note_id: str, exp_parent: Optional[str], exp_prev: Optional[str], exp_next: Optional[str]) -> None:
    parent_id = store.get(note_id).parent_id
    links_by_parent = store._links  # type: ignore[attr-defined]
    if parent_id not in links_by_parent:
        raise RuntimeError(f"Missing link scope for parent_id={parent_id}")
    links = links_by_parent[parent_id]
    if note_id not in links:
        raise RuntimeError(f"Missing note_id={note_id} in links for parent_id={parent_id}")
    cur = links[note_id]
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


def _apply_move_tags(op: dict, *, tags_key: str, token: str) -> None:
    if not isinstance(op, dict):
        raise TypeError(f"Undo op must be a dict, got {type(op)}")
    if tags_key not in op:
        return
    tags_value = op[tags_key]
    if not isinstance(tags_value, str):
        raise RuntimeError(f"Undo op move.{tags_key} must be a string | op={op}")
    note_id = op["note_id"]
    if not isinstance(note_id, str) or not note_id:
        raise RuntimeError(f"Undo op move.note_id must be a non-empty string | op={op}")
    record = store.get(note_id)
    if not isinstance(record.tags, str):
        raise RuntimeError(f"Note tags must be a string | note_id={note_id}")
    if record.tags == tags_value:
        return
    if not isinstance(record.content, str):
        raise RuntimeError(f"Note content must be a string | note_id={note_id}")
    apply_update_content(note_id, record.content, tags_value, token)


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

    # Selecting a collapsed note triggers an automatic expand request so the user can
    # see/edit its contents. That auto-expand should not consume a separate undo step;
    # instead, fold the collapse-state change into the preceding edit_mode op so a
    # single undo step both exits edit mode and restores the prior collapsed state.
    if before is True and after is False and ctx.history:
        last_op = ctx.history[-1]
        last_op_type = last_op["type"]
        if last_op_type == "edit_mode" and last_op["after_editing_note_id"] == note_id:
            last_op["auto_expand_note_id"] = note_id
            last_op["auto_expand_before_collapsed"] = True
            last_op["auto_expand_after_collapsed"] = False
            ctx.redo.clear()
            return

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


def record_paste_into(
    client_id: str,
    undo_context: str,
    *,
    note_id: str,
    before_content: str,
    before_tags: str,
    after_content: str,
    after_tags: str,
    inserted_records: List[NodeRecord],
    viewport: Dict[str, object],
) -> None:
    if not isinstance(note_id, str) or not note_id:
        raise ValueError("note_id must be a non-empty string")
    if not isinstance(before_content, str):
        raise TypeError("before_content must be a string")
    if not isinstance(before_tags, str):
        raise TypeError("before_tags must be a string")
    if not isinstance(after_content, str):
        raise TypeError("after_content must be a string")
    if not isinstance(after_tags, str):
        raise TypeError("after_tags must be a string")
    if not isinstance(inserted_records, list):
        raise TypeError("inserted_records must be a list")
    for record in inserted_records:
        if not isinstance(record, NodeRecord):
            raise TypeError("inserted_records entries must be NodeRecord objects")

    maybe_reset_on_context(client_id, undo_context)
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "paste_into",
        "note_id": note_id,
        "before_content": before_content,
        "before_tags": before_tags,
        "after_content": after_content,
        "after_tags": after_tags,
        "inserted_records": inserted_records,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    })
    ctx.redo.clear()


def record_join_next(
    client_id: str,
    undo_context: str,
    *,
    note_id: str,
    before_content: str,
    before_tags: str,
    after_content: str,
    after_tags: str,
    deleted_records: List[NodeRecord],
    viewport: Dict[str, object],
) -> None:
    if not isinstance(note_id, str) or not note_id:
        raise ValueError("note_id must be a non-empty string")
    if not isinstance(before_content, str):
        raise TypeError("before_content must be a string")
    if not isinstance(before_tags, str):
        raise TypeError("before_tags must be a string")
    if not isinstance(after_content, str):
        raise TypeError("after_content must be a string")
    if not isinstance(after_tags, str):
        raise TypeError("after_tags must be a string")
    if not isinstance(deleted_records, list):
        raise TypeError("deleted_records must be a list")
    if len(deleted_records) == 0:
        raise ValueError("deleted_records must be non-empty")
    for record in deleted_records:
        if not isinstance(record, NodeRecord):
            raise TypeError("deleted_records entries must be NodeRecord objects")

    maybe_reset_on_context(client_id, undo_context)
    ctx = _ctx(client_id)
    normalized_viewport = _normalize_viewport_snapshot(viewport)
    view_anchor_root_id = _anchor_root_id(normalized_viewport)
    ctx.history.append({
        "type": "join_next",
        "note_id": note_id,
        "before_content": before_content,
        "before_tags": before_tags,
        "after_content": after_content,
        "after_tags": after_tags,
        "deleted_records": deleted_records,
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

    if before_editing_note_id is not None and after_editing_note_id is None and ctx.history:
        last_op = ctx.history[-1]
        if "type" not in last_op:
            raise RuntimeError(f"Undo op missing required key: type | op={last_op}")
        if last_op["type"] == "edit_mode":
            if "before_editing_note_id" not in last_op:
                raise RuntimeError(
                    f"Undo op edit_mode missing required key: before_editing_note_id | op={last_op}"
                )
            if "after_editing_note_id" not in last_op:
                raise RuntimeError(
                    f"Undo op edit_mode missing required key: after_editing_note_id | op={last_op}"
                )
            previous_before = last_op["before_editing_note_id"]
            previous_after = last_op["after_editing_note_id"]
            if previous_before is None and previous_after == before_editing_note_id:
                op = {
                    "type": "edit_mode",
                    "before_editing_note_id": before_editing_note_id,
                    "after_editing_note_id": None,
                    "viewport": normalized_viewport,
                    "viewAnchorRootId": view_anchor_root_id,
                }
                for key in (
                    "auto_expand_note_id",
                    "auto_expand_before_collapsed",
                    "auto_expand_after_collapsed",
                ):
                    if key in last_op:
                        op[key] = last_op[key]
                ctx.history[-1] = op
                ctx.redo.clear()
                logger.info(
                    "undo.coalesce edit_mode enter+exit: note_id=%s history_len=%s redo_len=%s history_tail=%s",
                    before_editing_note_id,
                    len(ctx.history),
                    len(ctx.redo),
                    _summarize_stack(ctx.history, 12),
                )
                return

    # Don't record an extra undo stage when the client enters edit mode
    # immediately after creating a note. The create op already captures the
    # intended "note exists" transition, and keeping edit_mode as a separate
    # entry forces the user to press undo twice (exit edit mode, then delete).
    if before_editing_note_id is None and after_editing_note_id is not None and ctx.history:
        last_op = ctx.history[-1]
        if "type" not in last_op:
            raise RuntimeError(f"Undo op missing required key: type | op={last_op}")
        if last_op["type"] == "create_note":
            if "record" not in last_op:
                raise RuntimeError(f"Undo op create_note missing required key: record | op={last_op}")
            record = last_op["record"]
            if not isinstance(record, dict):
                raise RuntimeError(f"Undo op create_note.record must be an object | op={last_op}")
            if "id" not in record:
                raise RuntimeError(f"Undo op create_note.record missing id | op={last_op}")
            created_id = record["id"]
            if created_id == after_editing_note_id:
                return

    op = {
        "type": "edit_mode",
        "before_editing_note_id": before_editing_note_id,
        "after_editing_note_id": after_editing_note_id,
        "viewport": normalized_viewport,
        "viewAnchorRootId": view_anchor_root_id,
    }

    ctx.history.append(op)
    ctx.redo.clear()

    logger.info(
        "undo.stack record_edit_mode client=%s before=%s after=%s history_len=%s redo_len=%s history_tail=%s",
        client_id,
        before_editing_note_id,
        after_editing_note_id,
        len(ctx.history),
        len(ctx.redo),
        _summarize_stack(ctx.history, 12),
    )


def maybe_reset_on_context(client_id: str, undo_context: str) -> None:
    ctx = _ctx(client_id)
    if not isinstance(undo_context, str):
        raise TypeError("undo_context must be a string")
    if undo_context == "":
        raise ValueError("undo_context must be a non-empty string")

    if ctx.last_undo_context != undo_context:
        logger.info(
            "undo.stack reset client=%s from=%s to=%s",
            client_id,
            ctx.last_undo_context,
            undo_context,
        )
        ctx.history.clear()
        ctx.redo.clear()
        ctx.last_undo_context = undo_context


def reset_undo_stack(client_id: str, undo_context: str) -> None:
    if not isinstance(undo_context, str):
        raise TypeError('undo_context must be a string')
    if undo_context == "":
        raise ValueError('undo_context must be a non-empty string')

    ctx = _ctx(client_id)
    ctx.history.clear()
    ctx.redo.clear()
    ctx.last_undo_context = undo_context


def undo(client_id: str, token: str) -> Optional[Dict[str, object]]:
    ctx = _ctx(client_id)
    if not ctx.history:
        return None

    logger.info(
        "undo.stack undo_start client=%s history_len=%s redo_len=%s history_tail=%s redo_tail=%s",
        client_id,
        len(ctx.history),
        len(ctx.redo),
        _summarize_stack(ctx.history, 12),
        _summarize_stack(ctx.redo, 12),
    )

    op = ctx.history.pop()

    logger.info(
        "undo.stack undo_pop client=%s op=%s history_len=%s redo_len=%s",
        client_id,
        _summarize_op(op),
        len(ctx.history),
        len(ctx.redo),
    )

    if "type" not in op:
        raise RuntimeError(f"Undo op missing required key: type | op={op}")
    op_type = op["type"]

    # Coalesce a freshly-created note's auto-enter-edit-mode into the create op.
    # Without this, the user must press undo twice: once to exit edit mode and
    # again to delete the note.
    if op_type == "edit_mode" and ctx.history:
        if "before_editing_note_id" not in op:
            raise RuntimeError(f"Undo op edit_mode missing required key: before_editing_note_id | op={op}")
        if "after_editing_note_id" not in op:
            raise RuntimeError(f"Undo op edit_mode missing required key: after_editing_note_id | op={op}")
        before = op["before_editing_note_id"]
        after = op["after_editing_note_id"]
        if before is None and isinstance(after, str) and after:
            prev = ctx.history[-1]
            if "type" not in prev:
                raise RuntimeError(f"Undo op missing required key: type | op={prev}")
            if prev["type"] == "create_note":
                if "record" not in prev:
                    raise RuntimeError(f"Undo op create_note missing required key: record | op={prev}")
                record = prev["record"]
                if not isinstance(record, dict):
                    raise RuntimeError(f"Undo op create_note.record must be an object | op={prev}")
                if "id" not in record:
                    raise RuntimeError(f"Undo op create_note.record missing id | op={prev}")
                created_id = record["id"]
                if not isinstance(created_id, str) or not created_id:
                    raise RuntimeError(f"Undo op create_note.record.id must be a non-empty string | op={prev}")
                if created_id == after:
                    logger.info(
                        "undo.coalesce create_note+edit_mode: created_id=%s",
                        created_id,
                    )
                    op = ctx.history.pop()
                    if "type" not in op:
                        raise RuntimeError(f"Undo op missing required key: type | op={op}")
                    op_type = op["type"]

                    logger.info(
                        "undo.stack undo_coalesce client=%s coalesced_op=%s history_len=%s redo_len=%s history_tail=%s redo_tail=%s",
                        client_id,
                        _summarize_op(op),
                        len(ctx.history),
                        len(ctx.redo),
                        _summarize_stack(ctx.history, 12),
                        _summarize_stack(ctx.redo, 12),
                    )

    undo_viewport = op["viewport"]

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
        _apply_move_tags(op, tags_key="before_tags", token=token)
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "collapse":
        # invert collapse
        apply_set_collapse(op["note_id"], bool(op["before"]))
        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "paste_into":
        note_id = op["note_id"]
        if not isinstance(note_id, str) or not note_id:
            raise RuntimeError(f"Undo op paste_into.note_id must be a non-empty string | op={op}")
        before_content = op["before_content"]
        before_tags = op["before_tags"]
        if not isinstance(before_content, str):
            raise RuntimeError(f"Undo op paste_into.before_content must be a string | op={op}")
        if not isinstance(before_tags, str):
            raise RuntimeError(f"Undo op paste_into.before_tags must be a string | op={op}")
        inserted_records = op["inserted_records"]
        if not isinstance(inserted_records, list):
            raise RuntimeError(f"Undo op paste_into.inserted_records must be a list | op={op}")

        apply_update_content(note_id, before_content, before_tags, token)

        inserted_root_ids: list[str] = []
        for record in inserted_records:
            if not isinstance(record, NodeRecord):
                raise RuntimeError(
                    f"Undo op paste_into.inserted_records must contain NodeRecords | op={op}"
                )
            if record.parent_id == note_id:
                inserted_root_ids.append(record.id)

        for root_id in inserted_root_ids:
            apply_delete_subtree(root_id)

        ctx.redo.append(op)
        generate_new_uuid()
    elif op_type == "join_next":
        note_id = op["note_id"]
        if not isinstance(note_id, str) or not note_id:
            raise RuntimeError(f"Undo op join_next.note_id must be a non-empty string | op={op}")
        before_content = op["before_content"]
        before_tags = op["before_tags"]
        if not isinstance(before_content, str):
            raise RuntimeError(f"Undo op join_next.before_content must be a string | op={op}")
        if not isinstance(before_tags, str):
            raise RuntimeError(f"Undo op join_next.before_tags must be a string | op={op}")
        deleted_records = op["deleted_records"]
        if not isinstance(deleted_records, list) or len(deleted_records) == 0:
            raise RuntimeError(f"Undo op join_next.deleted_records must be a non-empty list | op={op}")

        apply_restore_records(deleted_records, token)
        apply_update_content(note_id, before_content, before_tags, token)

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

        if "auto_expand_note_id" in op:
            auto_expand_note_id = op["auto_expand_note_id"]
            if not isinstance(auto_expand_note_id, str) or not auto_expand_note_id:
                raise RuntimeError(f"Undo op edit_mode.auto_expand_note_id must be a non-empty string | op={op}")
            before_collapsed = op["auto_expand_before_collapsed"]
            if not isinstance(before_collapsed, bool):
                raise RuntimeError(
                    f"Undo op edit_mode.auto_expand_before_collapsed must be a bool | op={op}"
                )
            apply_set_collapse(auto_expand_note_id, bool(before_collapsed))
            generate_new_uuid()
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
    logger.info(
        "undo.finish opType=%s focusNoteId=%s viewAnchorRootId=%s",
        op_type,
        focus_note_id,
        view_anchor_root_id,
    )

    logger.info(
        "undo.stack undo_finish client=%s opType=%s focusNoteId=%s editingNoteId=%s history_len=%s redo_len=%s history_tail=%s redo_tail=%s",
        client_id,
        op_type,
        focus_note_id,
        editing_note_id,
        len(ctx.history),
        len(ctx.redo),
        _summarize_stack(ctx.history, 12),
        _summarize_stack(ctx.redo, 12),
    )
    return payload


def redo(client_id: str, token: str) -> Optional[Dict[str, object]]:
    ctx = _ctx(client_id)
    if not ctx.redo:
        return None

    logger.info(
        "undo.stack redo_start client=%s history_len=%s redo_len=%s history_tail=%s redo_tail=%s",
        client_id,
        len(ctx.history),
        len(ctx.redo),
        _summarize_stack(ctx.history, 12),
        _summarize_stack(ctx.redo, 12),
    )

    op = ctx.redo.pop()

    logger.info(
        "undo.stack redo_pop client=%s op=%s history_len=%s redo_len=%s",
        client_id,
        _summarize_op(op),
        len(ctx.history),
        len(ctx.redo),
    )
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
        apply_restore_records([SimpleNamespace(**rec)], token)
        ctx.history.append(op)
        generate_new_uuid()

        # If the client recorded an enter-edit-mode op immediately after create,
        # it is redundant: redo(create_note) already restores focus/editing.
        if ctx.redo:
            maybe_redundant = ctx.redo[-1]
            if "type" not in maybe_redundant:
                raise RuntimeError(f"Redo op missing required key: type | op={maybe_redundant}")
            if maybe_redundant["type"] == "edit_mode":
                if "before_editing_note_id" not in maybe_redundant:
                    raise RuntimeError(
                        f"Redo op edit_mode missing required key: before_editing_note_id | op={maybe_redundant}"
                    )
                if "after_editing_note_id" not in maybe_redundant:
                    raise RuntimeError(
                        f"Redo op edit_mode missing required key: after_editing_note_id | op={maybe_redundant}"
                    )
                before = maybe_redundant["before_editing_note_id"]
                after = maybe_redundant["after_editing_note_id"]
                if not isinstance(rec, dict):
                    raise RuntimeError(f"Redo op create_note.record must be an object | op={op}")
                if "id" not in rec:
                    raise RuntimeError(f"Redo op create_note.record missing id | op={op}")
                rec_id = rec["id"]
                if not isinstance(rec_id, str) or not rec_id:
                    raise RuntimeError(f"Redo op create_note.record.id must be a non-empty string | op={op}")

                if before is None and after == rec_id:
                    logger.info(
                        "redo.drop redundant edit_mode enter: note_id=%s",
                        rec_id,
                    )
                    ctx.redo.pop()
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
        _apply_move_tags(op, tags_key="after_tags", token=token)
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "collapse":
        apply_set_collapse(op["note_id"], bool(op["after"]))
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "paste_into":
        note_id = op["note_id"]
        if not isinstance(note_id, str) or not note_id:
            raise RuntimeError(f"Redo op paste_into.note_id must be a non-empty string | op={op}")
        after_content = op["after_content"]
        after_tags = op["after_tags"]
        if not isinstance(after_content, str):
            raise RuntimeError(f"Redo op paste_into.after_content must be a string | op={op}")
        if not isinstance(after_tags, str):
            raise RuntimeError(f"Redo op paste_into.after_tags must be a string | op={op}")
        inserted_records = op["inserted_records"]
        if not isinstance(inserted_records, list):
            raise RuntimeError(f"Redo op paste_into.inserted_records must be a list | op={op}")

        apply_update_content(note_id, after_content, after_tags, token)
        if inserted_records:
            apply_restore_records(inserted_records, token)
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "join_next":
        note_id = op["note_id"]
        if not isinstance(note_id, str) or not note_id:
            raise RuntimeError(f"Redo op join_next.note_id must be a non-empty string | op={op}")
        after_content = op["after_content"]
        after_tags = op["after_tags"]
        if not isinstance(after_content, str):
            raise RuntimeError(f"Redo op join_next.after_content must be a string | op={op}")
        if not isinstance(after_tags, str):
            raise RuntimeError(f"Redo op join_next.after_tags must be a string | op={op}")
        deleted_records = op["deleted_records"]
        if not isinstance(deleted_records, list) or len(deleted_records) == 0:
            raise RuntimeError(f"Redo op join_next.deleted_records must be a non-empty list | op={op}")
        deleted_root_id = deleted_records[0].id
        if not isinstance(deleted_root_id, str) or not deleted_root_id:
            raise RuntimeError(f"Redo op join_next.deleted_records[0].id must be a non-empty string | op={op}")

        apply_update_content(note_id, after_content, after_tags, token)
        apply_delete_subtree(deleted_root_id)

        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "paste_subtree":
        # restore the subtree
        apply_restore_records(op["records"], token)
        ctx.history.append(op)
        generate_new_uuid()
    elif op_type == "edit_mode":
        ctx.history.append(op)

        if "auto_expand_note_id" in op:
            auto_expand_note_id = op["auto_expand_note_id"]
            if not isinstance(auto_expand_note_id, str) or not auto_expand_note_id:
                raise RuntimeError(f"Redo op edit_mode.auto_expand_note_id must be a non-empty string | op={op}")
            after_collapsed = op["auto_expand_after_collapsed"]
            if not isinstance(after_collapsed, bool):
                raise RuntimeError(
                    f"Redo op edit_mode.auto_expand_after_collapsed must be a bool | op={op}"
                )
            apply_set_collapse(auto_expand_note_id, bool(after_collapsed))
            generate_new_uuid()
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
    logger.info(
        "redo.finish opType=%s focusNoteId=%s viewAnchorRootId=%s",
        op_type,
        focus_note_id,
        view_anchor_root_id,
    )

    logger.info(
        "undo.stack redo_finish client=%s opType=%s focusNoteId=%s editingNoteId=%s history_len=%s redo_len=%s history_tail=%s redo_tail=%s",
        client_id,
        op_type,
        focus_note_id,
        editing_note_id,
        len(ctx.history),
        len(ctx.redo),
        _summarize_stack(ctx.history, 12),
        _summarize_stack(ctx.redo, 12),
    )
    return payload
