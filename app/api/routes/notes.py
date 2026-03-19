from __future__ import annotations

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, Request

from app.services.snapshot import build_view_state
from app.services.snapshot import resolve_search_scope
from app.services.note_store import store as note_store
from app.usecases.create_note import CmdCreateNote
from app.usecases.create_sibling import CmdCreateSibling
from app.usecases.create_child import CmdCreateChild
from app.usecases.update_content import CmdUpdateContent
from app.usecases.delete_subtree import CmdDeleteSubtree
from app.usecases.move import CmdMove
from app.usecases.indent import CmdIndent
from app.usecases.outdent import CmdOutdent
from app.usecases.collapse import CmdCollapse
from app.usecases.expand import CmdExpand
from app.usecases.set_collapse_bulk import CmdSetCollapseBulk
from app.usecases.set_collapse_in_context import CmdSetCollapseInContext
from app.usecases.copy_note import CmdCopyNote
from app.usecases.toggle_todo_done import CmdToggleTodoDone
from app.usecases.run_shell import CmdRunShellInput
from app.usecases.run_shell import CmdRunShellStart
from app.usecases.run_shell import CmdRunShellStatus
from app.usecases.paste_sibling import CmdPasteSibling
from app.usecases.paste_child import CmdPasteChild
from app.usecases.join_next_sibling import CmdJoinNextSibling
from app.usecases.toggle_reference_mode import CmdToggleReferenceMode
from app.usecases.undo import CmdUndo
from app.usecases.redo import CmdRedo
from app.usecases.record_edit_mode import CmdRecordEditMode
from app.services.sync import get_current_sync_uuid
from app.config import VERSION
from app.services.view_cache import view_cache
from app.services.view_diff import generate_diff_ops
from app.services.tab_state import tab_state_store
from app.services.backlinks import list_backlinks_for_note
from app.services.undo_state import maybe_reset_on_context
from app.services.search_history import (
    list_recent_search_tags,
    prioritize_blank_search_suggestions,
    record_search_interaction,
)
from app.services.search_index import search_index
from app.services.tag_suggestions import suggest_tags_for_note


logger = logging.getLogger(__name__)


router = APIRouter()


def _require_note_present(note_id: str, *, context: str) -> None:
    if not isinstance(context, str) or not context:
        raise ValueError("context must be a non-empty string")
    if not isinstance(note_id, str) or not note_id:
        raise TypeError("note_id must be a non-empty string")

    if note_store.has_note(note_id):
        return

    raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")


@router.post("/notes/view")
def view_diff(payload: dict):
    # Strict: require keys, let FastAPI raise if invalid
    client_id = payload["clientId"]
    editing_note_id = payload["editingNoteId"]
    search = payload["search"]
    tab_id = payload["tabId"]
    undo_context = payload["undoContext"]
    client_note_uuid_hashes = payload["clientNoteUuidHashes"]
    anchor_root_id = payload["visibleRootAnchorId"]

    maybe_reset_on_context(client_id, undo_context)

    if not isinstance(client_note_uuid_hashes, dict):
        raise TypeError("clientNoteUuidHashes must be an object")

    normalized_search = search
    if isinstance(normalized_search, str) and normalized_search == "":
        normalized_search = None

    normalized_editing_note_id = editing_note_id
    if isinstance(normalized_editing_note_id, str) and normalized_editing_note_id == "":
        normalized_editing_note_id = None

    # The client can send a stale editingNoteId (e.g. after a delete/undo or a tab clone).
    # Treat it as "not editing" so /notes/view doesn't 500.
    if normalized_editing_note_id is not None:
        if not isinstance(normalized_editing_note_id, str):
            raise TypeError("editingNoteId must be a string or null")
        if not note_store.has_note(normalized_editing_note_id):
            normalized_editing_note_id = None

    # Known hashes plus a viewport anchor so the server can extend the window
    client_hashes = {
        k: v for k, v in client_note_uuid_hashes.items() if k
    }
    # Fallback: if client didn't provide an anchor, use the last known root from cached state
    cache_key = {
        "client_id": client_id,
        "tab_id": tab_id,
        "search": normalized_search,
    }
    cached_state = view_cache.get(**cache_key)
    if not anchor_root_id and cached_state:
        last_roots = list(cached_state.children_by_parent.get(None, []))
        if last_roots:
            anchor_root_id = last_roots[-1]

    state = build_view_state(
        editing_note_id=normalized_editing_note_id,
        search=normalized_search,
        client_known_note_ids=set(client_hashes.keys()),
        client_seen_root_ids=set(),
        anchor_root_id=anchor_root_id,
    )
    update_uuid = get_current_sync_uuid()
    root_ids = list(state.children_by_parent.get(None, []))
    root_count_total = state.metadata["rootCountTotal"]
    search_root_count_total = state.metadata["searchRootCountTotal"]

    extra_client_ids = set(client_hashes.keys()) - set(state.hash_by_id.keys())
    force_full_snapshot = bool(extra_client_ids)
    if force_full_snapshot:
        logger.info(
            "notes.view forcing full snapshot (client has unknown ids): extra_count=%s",
            len(extra_client_ids),
        )

    cached_state = view_cache.get(**cache_key)
    client_has_state = bool(client_hashes)

    if not cached_state or force_full_snapshot:
        view_cache.set(state=state, **cache_key)
        if force_full_snapshot:
            filtered_notes = dict(state.payloads)
        else:
            filtered_notes = {
                note_id: data
                for note_id, data in state.payloads.items()
                if client_hashes.get(note_id) != data.get("hash")
            }

        # Optimization: when the server cache is cold but the client already has a
        # complete, matching hash map for the visible window, avoid resending the
        # full structure + note payloads. This is common when a new tab is created
        # by cloning the existing DOM.
        if client_has_state and not filtered_notes and not force_full_snapshot:
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
                "rootCountTotal": root_count_total,
                "searchRootCountTotal": search_root_count_total,
                "editingNoteId": normalized_editing_note_id,
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
            "rootCountTotal": root_count_total,
            "searchRootCountTotal": search_root_count_total,
            "editingNoteId": normalized_editing_note_id,
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
            "rootCountTotal": root_count_total,
            "searchRootCountTotal": search_root_count_total,
            "editingNoteId": normalized_editing_note_id,
        }
        return {"snapshot": response_snapshot, "updateUUID": update_uuid}

    diff_ops = generate_diff_ops(cached_state, state)
    note_updates = {
        note_id: payload
        for note_id, payload in state.payloads.items()
        if cached_state.hash_by_id.get(note_id) != payload["hash"]
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
        "rootCountTotal": root_count_total,
        "searchRootCountTotal": search_root_count_total,
        "editingNoteId": normalized_editing_note_id,
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
    if not isinstance(tab_order, list):
        raise HTTPException(status_code=400, detail="tabOrder must be a list")
    tab_order_list = [str(entry) for entry in tab_order]
    return tab_state_store.update(active_tab_id=active_tab_id, tabs=tabs, tab_order=tab_order_list)


@router.post("/notes/tab-state/new-tab")
def create_new_tab(payload: dict) -> Dict[str, object]:
    if "copyFromTabId" not in payload:
        raise HTTPException(status_code=400, detail="copyFromTabId is required")
    copy_from_tab_id = payload["copyFromTabId"]
    return tab_state_store.create_tab(copy_from_tab_id=copy_from_tab_id)


@router.post("/notes/tab-state/delete-tab")
def delete_tab(payload: dict) -> Dict[str, object]:
    if "tabId" not in payload:
        raise HTTPException(status_code=400, detail="tabId is required")
    tab_id = payload["tabId"]
    return tab_state_store.delete_tab(tab_id=tab_id)


@router.post("/notes/search-suggestions")
def search_suggestions(request: Request, payload: dict) -> Dict[str, object]:
    query = payload["query"]
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    suggestions = search_index.suggest_tag_completions(query=query, limit=20)
    if query.strip() == "":
        token = _require_bearer_token(request)
        recent_tags = list_recent_search_tags(limit=3, token=token)
        suggestions = prioritize_blank_search_suggestions(
            base_suggestions=suggestions,
            recent_tags=recent_tags,
            priority_slots=3,
        )
    return {"suggestions": suggestions}


@router.post("/notes/search-interactions")
def search_interactions(request: Request, payload: dict) -> Dict[str, object]:
    token = _require_bearer_token(request)
    query = payload["query"]
    interaction_type = payload["interactionType"]
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if not isinstance(interaction_type, str):
        raise TypeError("interactionType must be a string")
    credited = record_search_interaction(
        query=query,
        interaction_type=interaction_type,
        token=token,
    )
    return {"credited": credited}


@router.post("/notes/tag-suggestions")
def tag_suggestions(payload: dict) -> Dict[str, object]:
    note_id = payload["note_id"]
    anchors = payload["anchors"]
    prefix = payload["prefix"]
    content_html = payload["content_html"]

    if not isinstance(note_id, str) or not note_id:
        raise TypeError("note_id must be a non-empty string")
    if not isinstance(anchors, list):
        raise TypeError("anchors must be a list")
    if not isinstance(prefix, str):
        raise TypeError("prefix must be a string")
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")

    _require_note_present(note_id, context="notes.tag-suggestions")

    suggestions = suggest_tags_for_note(
        note_id=note_id,
        anchors=anchors,
        prefix=prefix,
        content_html=content_html,
    )
    return {"suggestions": suggestions}


@router.get("/notes/{note_id}/backlinks")
def backlinks(request: Request, note_id: str) -> Dict[str, object]:
    _require_note_present(note_id, context="notes.backlinks")

    normalized_search = None
    if "search" in request.query_params:
        raw_search = request.query_params["search"]
        if not isinstance(raw_search, str):
            raise TypeError("search query parameter must be a string")
        normalized_search = raw_search
    if normalized_search == "":
        normalized_search = None

    source_note_ids = None
    if normalized_search is not None:
        search_scope = resolve_search_scope(
            search=normalized_search,
            editing_note_id=None,
        )
        source_note_ids = search_scope.allowed_note_ids

    backlinks = list_backlinks_for_note(note_id, source_note_ids=source_note_ids)
    return {
        "targetNoteId": note_id,
        "backlinks": backlinks,
    }


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
def create_note_top(request: Request, body: dict):
    token = _require_bearer_token(request)
    viewport = _require_viewport(body)
    cmd = CmdCreateNote(
        first_visible_note_id=body["first_visible_note_id"],
        search_query=body["search_query"],
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/new-sibling/{note_id}")
def create_sibling(request: Request, note_id: str, body: dict):
    token = _require_bearer_token(request)
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.new-sibling")
    cmd = CmdCreateSibling(
        reference_note_id=note_id,
        search_query=body["search_query"],
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/new-child/{note_id}")
def create_child(request: Request, note_id: str, body: dict):
    token = _require_bearer_token(request)
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.new-child")
    cmd = CmdCreateChild(
        parent_note_id=note_id,
        search_query=body["search_query"],
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.put("/notes/{note_id}")
def update_note(request: Request, note_id: str, body: dict):
    # Required fields; let KeyError surface for missing keys
    client_id = body["clientId"]
    content = body["content"]
    tags = body["tags"]
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    _require_note_present(note_id, context="notes.update")
    cmd = CmdUpdateContent(
        note_id=note_id,
        content=content,
        tags=tags,
        token=token,
        client_id=client_id,
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.put("/notes/{note_id}/save")
def save_note(request: Request, note_id: str, body: dict):
    client_id = body["clientId"]
    content = body["content"]
    tags = body["tags"]
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    _require_note_present(note_id, context="notes.save")
    cmd = CmdUpdateContent(
        note_id=note_id,
        content=content,
        tags=tags,
        token=token,
        client_id=client_id,
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/toggle-todo")
def toggle_todo_done(request: Request, note_id: str, body: dict):
    client_id = body["clientId"]
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    _require_note_present(note_id, context="notes.toggle-todo")
    cmd = CmdToggleTodoDone(
        note_id=note_id,
        token=token,
        client_id=client_id,
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/run-shell")
def run_shell_endpoint(note_id: str, body: dict) -> Dict[str, object]:
    _require_note_present(note_id, context="notes.run-shell")
    timeout_seconds = body["timeoutSeconds"]
    cmd = CmdRunShellStart(
        note_id=note_id,
        timeout_seconds=timeout_seconds,
    )
    return cmd.execute()


@router.get("/notes/{note_id}/run-shell/{run_id}")
def run_shell_status_endpoint(note_id: str, run_id: str) -> Dict[str, object]:
    try:
        cmd = CmdRunShellStatus(
            note_id=note_id,
            run_id=run_id,
        )
        return cmd.execute()
    except (RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/notes/{note_id}/run-shell/{run_id}/input")
def run_shell_input_endpoint(note_id: str, run_id: str, body: dict) -> Dict[str, object]:
    try:
        cmd = CmdRunShellInput(
            note_id=note_id,
            run_id=run_id,
            text=body["text"],
            append_newline=body["appendNewline"],
        )
        return cmd.execute()
    except (RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/notes/{note_id}/join-next")
def join_next_endpoint(request: Request, note_id: str, body: dict):
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    _require_note_present(note_id, context="notes.join-next")
    cmd = CmdJoinNextSibling(
        note_id=note_id,
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/reference-mode")
def toggle_reference_mode_endpoint(request: Request, note_id: str, body: dict):
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    _require_note_present(note_id, context="notes.reference-mode")
    cmd = CmdToggleReferenceMode(
        note_id=note_id,
        reference_note_id=body["reference_note_id"],
        occurrence_index=body["occurrence_index"],
        mode=body["mode"],
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/move")
def move_note_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.move")
    cmd = CmdMove(
        note_id=note_id,
        sibling_id=body["sibling_id"],
        position=body["position"],
        new_parent_id=body["new_parent_id"],
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/indent")
def indent_note_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.indent")
    cmd = CmdIndent(
        note_id=note_id,
        visible_prev_id=body["visible_prev_id"],
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/outdent")
def outdent_note_endpoint(request: Request, note_id: str, body: dict):
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    _require_note_present(note_id, context="notes.outdent")
    cmd = CmdOutdent(
        note_id=note_id,
        search_query=body["search_query"],
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/collapse")
def collapse_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.collapse")
    cmd = CmdCollapse(note_id=note_id, client_id=body["clientId"], undo_context=body["undoContext"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/{note_id}/expand")
def expand_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.expand")
    cmd = CmdExpand(note_id=note_id, client_id=body["clientId"], undo_context=body["undoContext"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/set-collapsed-bulk")
def set_collapsed_bulk_endpoint(body: dict):
    viewport = _require_viewport(body)
    note_ids = body["note_ids"]
    collapsed = body["collapsed"]

    if not isinstance(note_ids, list) or len(note_ids) == 0:
        raise TypeError("note_ids must be a non-empty list")
    if not isinstance(collapsed, bool):
        raise TypeError("collapsed must be a bool")

    for note_id in note_ids:
        if not isinstance(note_id, str) or not note_id:
            raise TypeError("note_ids must be non-empty strings")
        _require_note_present(note_id, context="notes.set_collapsed_bulk")

    cmd = CmdSetCollapseBulk(
        note_ids=note_ids,
        collapsed=collapsed,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/set-collapsed-in-context")
def set_collapsed_in_context_endpoint(body: dict):
    viewport = _require_viewport(body)
    search_query = body["search_query"]
    collapsed = body["collapsed"]

    if not isinstance(collapsed, bool):
        raise TypeError("collapsed must be a bool")

    normalized_search: str | None = search_query
    if isinstance(normalized_search, str) and normalized_search == "":
        normalized_search = None

    if normalized_search is not None and not isinstance(normalized_search, str):
        raise TypeError("search_query must be a string or null")

    cmd = CmdSetCollapseInContext(
        search_query=normalized_search,
        collapsed=collapsed,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, body: dict):
    client_id = body["clientId"]
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.delete")
    cmd = CmdDeleteSubtree(note_id=note_id, client_id=client_id, undo_context=body["undoContext"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/{note_id}/copy")
def copy_note_endpoint(note_id: str, body: dict):
    cmd = CmdCopyNote(note_id=note_id, client_id=body["clientId"])  
    return cmd.execute()


@router.post("/notes/paste-sibling/{target_note_id}")
def paste_sibling_endpoint(request: Request, target_note_id: str, body: dict):
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    search_query = body["search_query"]
    cmd = CmdPasteSibling(
        target_note_id=target_note_id,
        search_query=search_query,
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/paste-child/{target_note_id}")
def paste_child_endpoint(request: Request, target_note_id: str, body: dict):
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    search_query = body["search_query"]
    cmd = CmdPasteChild(
        target_note_id=target_note_id,
        search_query=search_query,
        token=token,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


def _require_viewport(body: dict) -> dict:
    viewport = body["viewport"]
    if not isinstance(viewport, dict):
        raise HTTPException(status_code=400, detail="viewport is required")
    return viewport


def _require_bearer_token(request: Request) -> str:
    if "authorization" not in request.headers:
        raise HTTPException(status_code=401, detail="Authentication required")
    authorization = request.headers["authorization"]
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    return parts[1]


@router.post("/notes/undo")
def undo_endpoint(request: Request, client_id: str, undoContext: str):
    token = _require_bearer_token(request)
    return CmdUndo(client_id=client_id, token=token, undo_context=undoContext).execute()


@router.post("/notes/redo")
def redo_endpoint(request: Request, client_id: str, undoContext: str):
    token = _require_bearer_token(request)
    return CmdRedo(client_id=client_id, token=token, undo_context=undoContext).execute()


@router.post("/notes/edit-mode")
def record_edit_mode_endpoint(request: Request, body: dict) -> Dict[str, object]:
    token = _require_bearer_token(request)
    viewport = _require_viewport(body)
    executed_search_query = body["executedSearchQuery"]
    if not isinstance(executed_search_query, str):
        raise HTTPException(status_code=400, detail="executedSearchQuery must be a string")
    cmd = CmdRecordEditMode(
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        before_editing_note_id=body["beforeEditingNoteId"],
        after_editing_note_id=body["afterEditingNoteId"],
        viewport=viewport,
    )
    result = cmd.execute()
    after_editing_note_id = body["afterEditingNoteId"]
    if isinstance(after_editing_note_id, str) and after_editing_note_id != "" and executed_search_query != "":
        record_search_interaction(
            query=executed_search_query,
            interaction_type="edit",
            token=token,
        )
    return result
