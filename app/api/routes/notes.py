from __future__ import annotations

import logging
import urllib.parse
from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.api.transactions import transactional_route
from app.services.snapshot import build_view_state
from app.services.snapshot import resolve_search_scope
from app.services.note_store import store as note_store
from app.services.exception_capture import CapturedExceptionContext
from app.usecases.create_note import CmdCreateNote
from app.usecases.create_sibling import CmdCreateSibling
from app.usecases.create_child import CmdCreateChild
from app.usecases.update_content import CmdUpdateContent
from app.usecases.delete_subtree import CmdDeleteSubtree
from app.usecases.move import CmdMove
from app.usecases.move_to_top import CmdMoveToTop
from app.usecases.prioritize import CmdPrioritize
from app.usecases.indent import CmdIndent
from app.usecases.outdent import CmdOutdent
from app.usecases.collapse import CmdCollapse
from app.usecases.expand import CmdExpand
from app.usecases.set_collapse_bulk import CmdSetCollapseBulk
from app.usecases.set_collapse_in_context import CmdSetCollapseInContext
from app.usecases.copy_note import CmdCopyNote
from app.usecases.toggle_todo_done import CmdToggleTodoDone
from app.usecases.run_shell import CmdRunShellStart
from app.usecases.run_shell import CmdRunShellStatus
from app.usecases.paste_sibling import CmdPasteSibling
from app.usecases.paste_child import CmdPasteChild
from app.usecases.join_next_sibling import CmdJoinNextSibling
from app.usecases.toggle_reference_mode import CmdToggleReferenceMode
from app.usecases.unformat_content import CmdUnformatContent
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
    is_first_search_tag_suggestion_context,
    list_recent_search_tags,
    prioritize_first_search_tag_suggestions,
    record_search_interaction,
)
from app.services.root_sorting import is_root_reorder_locked
from app.services.root_sorting import normalize_sort_mode
from app.services.html_export import build_notes_export_document
from app.services.html_export import build_notes_export_filename
from app.services.search_index import search_index
from app.services.tag_suggestions import suggest_tags_for_note
from app.services.undo_state import reset_undo_stack
from app.usecases.prioritize import list_prioritize_tag_suggestions
from app.api.request_auth import require_request_auth_token


logger = logging.getLogger(__name__)


router = APIRouter()
RECENT_SEARCH_TAG_CANDIDATE_LIMIT = 50
RECENT_SEARCH_TAG_PRIORITY_SLOTS = 3


def _require_note_present(note_id: str, *, context: str) -> None:
    if not isinstance(context, str) or not context:
        raise ValueError("context must be a non-empty string")
    if not isinstance(note_id, str) or not note_id:
        raise TypeError("note_id must be a non-empty string")

    if note_store.has_note(note_id):
        return

    raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")


def _resolve_tab_sort_mode(tab_id: object) -> str:
    if tab_id is not None and (not isinstance(tab_id, str) or tab_id == ""):
        raise TypeError("tabId must be a non-empty string")

    capture = CapturedExceptionContext(ValueError)
    sort_mode: str | None = None
    with capture:
        sort_mode = tab_state_store.get_sort_mode(tab_id=tab_id)
    if capture.captured_exception is not None:
        exc = capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if sort_mode is None:
        raise RuntimeError("tab_state_store.get_sort_mode returned no value")
    return sort_mode


def _block_root_reorder_when_sorted(note_id: str, *, tab_id: object, new_parent_id: object) -> None:
    sort_mode = _resolve_tab_sort_mode(tab_id)
    if not is_root_reorder_locked(sort_mode):
        return

    record = note_store.get_note(note_id)
    if record.parent_id is not None:
        return
    if new_parent_id is not None:
        return

    raise HTTPException(
        status_code=409,
        detail=(
            "Root-note reordering is unavailable while sort order is "
            f"{normalize_sort_mode(sort_mode)!r}"
        ),
    )


def _block_root_prioritization_when_sorted(*, tab_id: object) -> None:
    sort_mode = _resolve_tab_sort_mode(tab_id)
    if not is_root_reorder_locked(sort_mode):
        return
    raise HTTPException(
        status_code=409,
        detail=(
            "Root-note reordering is unavailable while sort order is "
            f"{normalize_sort_mode(sort_mode)!r}"
        ),
    )


@router.post("/notes/view")
@transactional_route
def view_diff(payload: dict):
    # Strict: require keys, let FastAPI raise if invalid
    client_id = payload["clientId"]
    editing_note_id = payload["editingNoteId"]
    search = payload["search"]
    tab_id = payload["tabId"]
    undo_context = payload["undoContext"]
    client_note_uuid_hashes = payload["clientNoteUuidHashes"]
    anchor_root_id = payload["visibleRootAnchorId"]

    sort_mode = _resolve_tab_sort_mode(tab_id)
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
        "sort_mode": sort_mode,
    }
    cached_state = view_cache.get(**cache_key)
    if not anchor_root_id and cached_state:
        last_roots = list(cached_state.children_by_parent.get(None, []))
        if last_roots:
            anchor_root_id = last_roots[-1]

    state = build_view_state(
        editing_note_id=normalized_editing_note_id,
        search=normalized_search,
        sort_mode=sort_mode,
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
                "sortMode": sort_mode,
                "rootCountTotal": root_count_total,
                "searchRootCountTotal": search_root_count_total,
                "rootSortBuckets": state.metadata["rootSortBuckets"],
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
            "sortMode": sort_mode,
            "rootCountTotal": root_count_total,
            "searchRootCountTotal": search_root_count_total,
            "rootSortBuckets": state.metadata["rootSortBuckets"],
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
            "sortMode": sort_mode,
            "rootCountTotal": root_count_total,
            "searchRootCountTotal": search_root_count_total,
            "rootSortBuckets": state.metadata["rootSortBuckets"],
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
        "sortMode": sort_mode,
        "rootCountTotal": root_count_total,
        "searchRootCountTotal": search_root_count_total,
        "rootSortBuckets": state.metadata["rootSortBuckets"],
        "editingNoteId": normalized_editing_note_id,
    }
    return {"snapshot": response_snapshot, "updateUUID": update_uuid}


@router.get("/notes/tab-state")
def get_tab_state() -> Dict[str, object]:
    return tab_state_store.snapshot()


@router.post("/notes/tab-state")
@transactional_route
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


@router.post("/notes/tab-state/sort-mode")
@transactional_route
def update_tab_sort_mode(payload: dict) -> Dict[str, object]:
    if "tabId" not in payload:
        raise HTTPException(status_code=400, detail="tabId is required")
    if "sortMode" not in payload:
        raise HTTPException(status_code=400, detail="sortMode is required")

    tab_id = payload["tabId"]
    sort_mode = payload["sortMode"]
    client_id = payload["clientId"]
    undo_context = payload["undoContext"]

    capture = CapturedExceptionContext(TypeError, ValueError)
    response: Dict[str, object] | None = None
    with capture:
        response = tab_state_store.set_sort_mode(tab_id=tab_id, sort_mode=sort_mode)
    if capture.captured_exception is not None:
        exc = capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response is None:
        raise RuntimeError("tab_state_store.set_sort_mode returned no value")
    if response["changed"] is True:
        reset_undo_stack(client_id, undo_context)
    return response


@router.post("/notes/tab-state/new-tab")
@transactional_route
def create_new_tab(payload: dict) -> Dict[str, object]:
    if "copyFromTabId" not in payload:
        raise HTTPException(status_code=400, detail="copyFromTabId is required")
    copy_from_tab_id = payload["copyFromTabId"]
    return tab_state_store.create_tab(copy_from_tab_id=copy_from_tab_id)


@router.post("/notes/tab-state/delete-tab")
@transactional_route
def delete_tab(payload: dict) -> Dict[str, object]:
    if "tabId" not in payload:
        raise HTTPException(status_code=400, detail="tabId is required")
    tab_id = payload["tabId"]
    return tab_state_store.delete_tab(tab_id=tab_id)


@router.post("/notes/search-suggestions")
@transactional_route
def search_suggestions(request: Request, payload: dict) -> Dict[str, object]:
    query = payload["query"]
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    suggestions = search_index.suggest_tag_completions(query=query, limit=20)
    if is_first_search_tag_suggestion_context(query):
        token = _require_bearer_token(request)
        recent_tags = list_recent_search_tags(limit=RECENT_SEARCH_TAG_CANDIDATE_LIMIT, token=token)
        suggestions = prioritize_first_search_tag_suggestions(
            query=query,
            base_suggestions=suggestions,
            recent_tags=recent_tags,
            priority_slots=RECENT_SEARCH_TAG_PRIORITY_SLOTS,
        )
    return {"suggestions": suggestions}


@router.post("/notes/prioritize-tag-suggestions")
@transactional_route
def prioritize_tag_suggestions(payload: dict) -> Dict[str, object]:
    query = payload["query"]
    search_query = payload["search_query"]

    if not isinstance(query, str):
        raise TypeError("query must be a string")
    normalized_search: str | None = search_query
    if isinstance(normalized_search, str) and normalized_search == "":
        normalized_search = None
    if normalized_search is not None and not isinstance(normalized_search, str):
        raise TypeError("search_query must be a string or null")

    suggestions = list_prioritize_tag_suggestions(
        search_query=normalized_search,
        query=query,
        limit=20,
    )
    return {"suggestions": suggestions}


@router.post("/notes/search-interactions")
@transactional_route
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
@transactional_route
def tag_suggestions(payload: dict) -> Dict[str, object]:
    note_id = payload["note_id"]
    anchors = payload["anchors"]
    explicit_tags = payload["explicit_tags"]
    prefix = payload["prefix"]
    content_html = payload["content_html"]

    if not isinstance(note_id, str) or not note_id:
        raise TypeError("note_id must be a non-empty string")
    if not isinstance(anchors, list):
        raise TypeError("anchors must be a list")
    if not isinstance(explicit_tags, list):
        raise TypeError("explicit_tags must be a list")
    if not isinstance(prefix, str):
        raise TypeError("prefix must be a string")
    if not isinstance(content_html, str):
        raise TypeError("content_html must be a string")

    _require_note_present(note_id, context="notes.tag-suggestions")

    suggestions = suggest_tags_for_note(
        note_id=note_id,
        anchors=anchors,
        explicit_tags=explicit_tags,
        prefix=prefix,
        content_html=content_html,
    )
    return {"suggestions": suggestions}


@router.get("/notes/export-html")
def export_notes_html(request: Request) -> Response:
    token = _require_bearer_token(request)
    search_query = request.query_params.get("search_query")
    if search_query is None:
        raise HTTPException(status_code=400, detail="search_query query parameter is required")
    theme = request.query_params.get("theme")
    if theme is None:
        raise HTTPException(status_code=400, detail="theme query parameter is required")

    if not isinstance(search_query, str):
        raise TypeError("search_query query parameter must be a string")
    if not isinstance(theme, str):
        raise TypeError("theme query parameter must be a string")

    normalized_search = search_query
    if normalized_search == "":
        normalized_search = None

    normalized_theme = theme.strip().lower()
    if normalized_theme not in {"dark", "light"}:
        raise HTTPException(status_code=400, detail="theme must be 'light' or 'dark'")

    document = build_notes_export_document(
        search=normalized_search,
        theme=normalized_theme,
        token=token,
    )
    filename = build_notes_export_filename()
    quoted_filename = urllib.parse.quote(filename)
    return Response(
        content=document,
        media_type="text/html",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
            "X-MetaList-Export": "notes-html-v1",
        },
    )


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
            sort_mode="normal",
            ordered_root_ids=None,
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
@transactional_route
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
@transactional_route
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
@transactional_route
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
@transactional_route
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
@transactional_route
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
@transactional_route
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


@router.post("/notes/{note_id}/unformat")
@transactional_route
def unformat_note_content(request: Request, note_id: str, body: dict):
    client_id = body["clientId"]
    viewport = _require_viewport(body)
    token = _require_bearer_token(request)
    _require_note_present(note_id, context="notes.unformat")
    cmd = CmdUnformatContent(
        note_id=note_id,
        token=token,
        client_id=client_id,
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/run-shell")
@transactional_route
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
    run_capture = CapturedExceptionContext(RuntimeError, TypeError, ValueError)
    result: Dict[str, object] | None = None
    with run_capture:
        cmd = CmdRunShellStatus(
            note_id=note_id,
            run_id=run_id,
        )
        result = cmd.execute()
    if run_capture.captured_exception is not None:
        exc = run_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise RuntimeError("Shell status command did not return a result")
    return result


@router.post("/notes/{note_id}/join-next")
@transactional_route
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
@transactional_route
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
@transactional_route
def move_note_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.move")
    if "tab_id" in body:
        tab_id = body["tab_id"]
    else:
        tab_id = None
    _block_root_reorder_when_sorted(
        note_id,
        tab_id=tab_id,
        new_parent_id=body["new_parent_id"],
    )
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


@router.post("/notes/{note_id}/move-to-top")
@transactional_route
def move_note_to_top_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.move-to-top")

    search_query = body["search_query"]
    normalized_search: str | None = search_query
    if isinstance(normalized_search, str) and normalized_search == "":
        normalized_search = None
    if normalized_search is not None and not isinstance(normalized_search, str):
        raise TypeError("search_query must be a string or null")

    if "tab_id" in body:
        tab_id = body["tab_id"]
    else:
        tab_id = None
    _block_root_reorder_when_sorted(
        note_id,
        tab_id=tab_id,
        new_parent_id=None,
    )

    cmd = CmdMoveToTop(
        note_id=note_id,
        search_query=normalized_search,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.post("/notes/{note_id}/indent")
@transactional_route
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
@transactional_route
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
@transactional_route
def collapse_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.collapse")
    cmd = CmdCollapse(note_id=note_id, client_id=body["clientId"], undo_context=body["undoContext"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/{note_id}/expand")
@transactional_route
def expand_endpoint(note_id: str, body: dict):
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.expand")
    cmd = CmdExpand(note_id=note_id, client_id=body["clientId"], undo_context=body["undoContext"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/set-collapsed-bulk")
@transactional_route
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
@transactional_route
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


@router.post("/notes/prioritize")
@transactional_route
def prioritize_in_view_endpoint(body: dict):
    viewport = _require_viewport(body)
    tag = body["tag"]
    direction = body["direction"]
    search_query = body["search_query"]
    if "tab_id" in body:
        tab_id = body["tab_id"]
    else:
        tab_id = None

    if not isinstance(tag, str):
        raise TypeError("tag must be a string")
    if not isinstance(direction, str):
        raise TypeError("direction must be a string")

    normalized_search: str | None = search_query
    if isinstance(normalized_search, str) and normalized_search == "":
        normalized_search = None
    if normalized_search is not None and not isinstance(normalized_search, str):
        raise TypeError("search_query must be a string or null")
    _block_root_prioritization_when_sorted(tab_id=tab_id)

    cmd = CmdPrioritize(
        tag=tag,
        direction=direction,
        search_query=normalized_search,
        client_id=body["clientId"],
        undo_context=body["undoContext"],
        viewport=viewport,
    )
    return cmd.execute()


@router.delete("/notes/{note_id}")
@transactional_route
def delete_note(note_id: str, body: dict):
    client_id = body["clientId"]
    viewport = _require_viewport(body)
    _require_note_present(note_id, context="notes.delete")
    cmd = CmdDeleteSubtree(note_id=note_id, client_id=client_id, undo_context=body["undoContext"], viewport=viewport)
    return cmd.execute()


@router.post("/notes/{note_id}/copy")
@transactional_route
def copy_note_endpoint(note_id: str, body: dict):
    cmd = CmdCopyNote(note_id=note_id, client_id=body["clientId"])  
    return cmd.execute()


@router.post("/notes/paste-sibling/{target_note_id}")
@transactional_route
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
@transactional_route
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
    return require_request_auth_token(request)


@router.post("/notes/undo")
@transactional_route
def undo_endpoint(request: Request, client_id: str, undoContext: str):
    token = _require_bearer_token(request)
    return CmdUndo(client_id=client_id, token=token, undo_context=undoContext).execute()


@router.post("/notes/redo")
@transactional_route
def redo_endpoint(request: Request, client_id: str, undoContext: str):
    token = _require_bearer_token(request)
    return CmdRedo(client_id=client_id, token=token, undo_context=undoContext).execute()


@router.post("/notes/edit-mode")
@transactional_route
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
