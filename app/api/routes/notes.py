from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException, Query

from app.services.snapshot import build_view_state
from app.usecases.create_note import CmdCreateNote
from app.usecases.create_sibling import CmdCreateSibling
from app.usecases.create_child import CmdCreateChild
from app.usecases.update_content import CmdUpdateContent
from app.usecases.delete_subtree import CmdDeleteSubtree
from app.usecases.move import CmdMove
from app.usecases.collapse import CmdCollapse
from app.usecases.expand import CmdExpand
from app.usecases.copy_note import CmdCopyNote
from app.usecases.paste_sibling import CmdPasteSibling
from app.usecases.paste_child import CmdPasteChild
from app.usecases.undo import CmdUndo
from app.usecases.redo import CmdRedo
from app.services.sync import get_current_sync_uuid
from app.config import VERSION
from app.services.view_cache import view_cache
from app.services.view_diff import generate_diff_ops
from app.services.tab_state import tab_state_store


router = APIRouter()


@router.post("/notes/view")
def view_diff(payload: dict):
    # Strict: require keys, let FastAPI raise if invalid
    client_id = payload["clientId"]
    editing_note_id = payload["editingNoteId"]
    search = payload["search"]
    tab_id = payload["tabId"]
    client_note_uuid_hashes = payload["clientNoteUuidHashes"]
    anchor_root_id = payload.get("visibleRootAnchorId")

    if not isinstance(client_note_uuid_hashes, dict):
        raise TypeError("clientNoteUuidHashes must be an object")

    # Known hashes plus a viewport anchor so the server can extend the window
    client_hashes = {
        k: v for k, v in client_note_uuid_hashes.items() if k
    }
    # Fallback: if client didn't provide an anchor, use the last known root from cached state
    cache_key = {
        "client_id": client_id,
        "tab_id": tab_id,
        "search": search or None,
    }
    cached_state = view_cache.get(**cache_key)
    if not anchor_root_id and cached_state:
        last_roots = list(cached_state.children_by_parent.get(None, []))
        if last_roots:
            anchor_root_id = last_roots[-1]

    state = build_view_state(
        editing_note_id=editing_note_id or None,
        search=search or None,
        client_known_note_ids=set(client_hashes.keys()),
        client_seen_root_ids=set(),
        anchor_root_id=anchor_root_id,
    )
    update_uuid = get_current_sync_uuid()
    root_ids = list(state.children_by_parent.get(None, []))

    cached_state = view_cache.get(**cache_key)
    client_has_state = bool(client_hashes)

    if not cached_state:
        view_cache.set(state=state, **cache_key)
        filtered_notes = {
            note_id: data
            for note_id, data in state.payloads.items()
            if client_hashes.get(note_id) != data.get("hash")
        }

        # Optimization: when the server cache is cold but the client already has a
        # complete, matching hash map for the visible window, avoid resending the
        # full structure + note payloads. This is common when a new tab is created
        # by cloning the existing DOM.
        if client_has_state and not filtered_notes:
            response_snapshot = {
                "diffOps": [],
                "notes": {},
                "locks": state.locks,
                "rootIds": root_ids,
                "lockDiffs": {},
                "updateUUID": update_uuid,
                "version": VERSION,
                "currentClientId": client_id,
                "searchQuery": search,
                "editingNoteId": editing_note_id,
            }
            return {"snapshot": response_snapshot, "updateUUID": update_uuid}

        response_snapshot = {
            "structure": state.structure,
            "notes": filtered_notes,
            "locks": state.locks,
            "rootIds": root_ids,
            "updateUUID": update_uuid,
            "version": VERSION,
            "currentClientId": client_id,
            "searchQuery": search,
            "editingNoteId": editing_note_id,
        }
        return {"snapshot": response_snapshot, "updateUUID": update_uuid}

    if not client_has_state:
        view_cache.set(state=state, **cache_key)
        filtered_notes = {
            note_id: data
            for note_id, data in state.payloads.items()
            if client_hashes.get(note_id) != data.get("hash")
        }
        response_snapshot = {
            "structure": state.structure,
            "notes": filtered_notes,
            "locks": state.locks,
            "rootIds": root_ids,
            "updateUUID": update_uuid,
            "version": VERSION,
            "currentClientId": client_id,
            "searchQuery": search,
            "editingNoteId": editing_note_id,
        }
        return {"snapshot": response_snapshot, "updateUUID": update_uuid}

    diff_ops = generate_diff_ops(cached_state, state)
    note_updates = {
        note_id: payload
        for note_id, payload in state.payloads.items()
        if cached_state.hash_by_id.get(note_id) != payload.get("hash")
    }

    view_cache.set(state=state, **cache_key)

    lock_diff = _compute_lock_diff(cached_state.locks, state.locks)

    response_snapshot = {
        "diffOps": diff_ops,
        "notes": note_updates,
        "locks": state.locks,
        "rootIds": root_ids,
        "lockDiffs": lock_diff,
        "updateUUID": update_uuid,
        "version": VERSION,
        "currentClientId": client_id,
        "searchQuery": search,
        "editingNoteId": editing_note_id,
    }
    return {"snapshot": response_snapshot, "updateUUID": update_uuid}


@router.get("/notes/tab-state")
def get_tab_state() -> Dict[str, object]:
    return tab_state_store.snapshot()


@router.post("/notes/tab-state")
def update_tab_state(payload: dict) -> Dict[str, object]:
    if "activeTabId" not in payload or "tabs" not in payload or "tabOrder" not in payload:
        raise HTTPException(status_code=400, detail="activeTabId, tabs, and tabOrder are required")
    active_tab_id = payload["activeTabId"]
    tabs = payload["tabs"]
    tab_order = payload["tabOrder"]
    try:
        if not isinstance(tab_order, list):
            raise ValueError("tabOrder must be a list")
        tab_order_list = [str(entry) for entry in tab_order]
        return tab_state_store.update(active_tab_id=active_tab_id, tabs=tabs, tab_order=tab_order_list)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/notes/tab-state/new-tab")
def create_new_tab(payload: dict) -> Dict[str, object]:
    if "copyFromTabId" not in payload:
        raise HTTPException(status_code=400, detail="copyFromTabId is required")
    copy_from_tab_id = payload["copyFromTabId"]
    try:
        return tab_state_store.create_tab(copy_from_tab_id=copy_from_tab_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/notes/tab-state/delete-tab")
def delete_tab(payload: dict) -> Dict[str, object]:
    if "tabId" not in payload:
        raise HTTPException(status_code=400, detail="tabId is required")
    tab_id = payload["tabId"]
    try:
        return tab_state_store.delete_tab(tab_id=tab_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _compute_lock_diff(previous: Dict[str, str], current: Dict[str, str]) -> Dict[str, str]:
    diff: Dict[str, str] = {}
    for note_id, owner in current.items():
        if previous.get(note_id) != owner:
            diff[note_id] = owner
    for note_id in previous:
        if note_id not in current:
            diff[note_id] = ""
    return diff


# Stub endpoints for the rest of the notes API (501 Not Implemented)

def _not_impl(exc: Exception) -> None:
    # Turn NotImplementedError into HTTP 501; re-raise anything else
    if isinstance(exc, NotImplementedError):
        raise HTTPException(status_code=501, detail=str(exc))
    raise exc


@router.post("/notes/new")
def create_note_top(body: dict):
    viewport = _require_viewport(body)
    cmd = CmdCreateNote(
        first_visible_note_id=body.get("first_visible_note_id"),
        search_query=body.get("search_query"),
        client_id=body["clientId"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/new-sibling/{note_id}")
def create_sibling(note_id: str, body: dict):
    viewport = _require_viewport(body)
    cmd = CmdCreateSibling(
        reference_note_id=note_id,
        search_query=body.get("search_query"),
        client_id=body["clientId"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/new-child/{note_id}")
def create_child(note_id: str, body: dict):
    viewport = _require_viewport(body)
    cmd = CmdCreateChild(parent_note_id=note_id, client_id=body["clientId"], viewport=viewport)
    return cmd.execute()


@router.put("/notes/{note_id}")
def update_note(note_id: str, body: dict):
    # Required fields; let KeyError surface for missing keys
    client_id = body["clientId"]
    content = body["content"]
    tags = body["tags"]
    viewport = _require_viewport(body)
    cmd = CmdUpdateContent(note_id=note_id, content=content, tags=tags, client_id=client_id, viewport=viewport)
    return cmd.execute()


@router.put("/notes/{note_id}/save")
def save_note(note_id: str, body: dict):
    client_id = body["clientId"]
    content = body["content"]
    tags = body["tags"]
    viewport = _require_viewport(body)
    cmd = CmdUpdateContent(note_id=note_id, content=content, tags=tags, client_id=client_id, viewport=viewport)
    return cmd.execute()


@router.post("/notes/{note_id}/move")
def move_note_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    cmd = CmdMove(
        note_id=note_id,
        sibling_id=body.get("sibling_id"),
        position=body.get("position"),
        new_parent_id=body.get("new_parent_id"),
        client_id=body["clientId"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/collapse")
def collapse_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    cmd = CmdCollapse(note_id=note_id, client_id=body["clientId"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/{note_id}/expand")
def expand_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    cmd = CmdExpand(note_id=note_id, client_id=body["clientId"], viewport=viewport)
    return cmd.execute()


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, body: dict):
    client_id = body["clientId"]
    viewport = _require_viewport(body)
    cmd = CmdDeleteSubtree(note_id=note_id, client_id=client_id, viewport=viewport)
    return cmd.execute()


@router.post("/notes/{note_id}/copy")
def copy_note_endpoint(note_id: str, body: dict):
    cmd = CmdCopyNote(note_id=note_id, client_id=body["clientId"])  
    return cmd.execute()


@router.post("/notes/paste-sibling/{target_note_id}")
def paste_sibling_endpoint(target_note_id: str, body: dict):
    viewport = _require_viewport(body)
    cmd = CmdPasteSibling(target_note_id=target_note_id, client_id=body["clientId"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/paste-child/{target_note_id}")
def paste_child_endpoint(target_note_id: str, body: dict):
    viewport = _require_viewport(body)
    cmd = CmdPasteChild(target_note_id=target_note_id, client_id=body["clientId"], viewport=viewport)
    return cmd.execute()


def _require_viewport(body: dict) -> dict:
    viewport = body.get("viewport")
    if not isinstance(viewport, dict):
        raise HTTPException(status_code=400, detail="viewport is required")
    return viewport


@router.post("/notes/undo")
def undo_endpoint(client_id: str, searchContext: str = Query(...)):
    return CmdUndo(client_id=client_id, search_context=searchContext).execute()


@router.post("/notes/redo")
def redo_endpoint(client_id: str, searchContext: str = Query(...)):
    return CmdRedo(client_id=client_id, search_context=searchContext).execute()
