from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from server_v2.endpoints.view import CmdView
from server_v2.snapshot import build_view_snapshot
from server_v2.endpoints.create_note import CmdCreateNote
from server_v2.endpoints.create_drop import CmdCreateDrop
from server_v2.endpoints.create_sibling import CmdCreateSibling
from server_v2.endpoints.create_child import CmdCreateChild
from server_v2.endpoints.update_content import CmdUpdateContent
from server_v2.endpoints.delete_subtree import CmdDeleteSubtree
from server_v2.endpoints.move import CmdMove
from server_v2.endpoints.collapse import CmdCollapse
from server_v2.endpoints.expand import CmdExpand
from server_v2.endpoints.copy_note import CmdCopyNote
from server_v2.endpoints.export_html import CmdExportHtml
from server_v2.endpoints.paste_sibling import CmdPasteSibling
from server_v2.endpoints.paste_child import CmdPasteChild
from server_v2.endpoints.undo import CmdUndo
from server_v2.endpoints.redo import CmdRedo
from server_v2.sync import get_current_sync_uuid
from server_v2.endpoints.check_updates import CmdCheckUpdates
from server_v2.endpoints.lock import CmdAcquireLock, CmdReleaseLock
from app.core.config import VERSION


router = APIRouter()


@router.post("/notes/view")
def view_diff(payload: dict):
    # Strict: require keys, let FastAPI raise if invalid
    client_id = payload["clientId"]
    editing_note_id = payload["editingNoteId"]
    search = payload["search"]
    _ = payload["clientNoteUuidHashes"]
    _ = payload["clientSeenRootIds"]

    cmd = CmdView(client_id=client_id, editing_note_id=editing_note_id or None, search=search or None)
    # Known hashes and seen roots from client to drive windowing + diff
    client_hashes = {
        k: v for k, v in (payload.get("clientNoteUuidHashes") or {}).items() if k
    }
    seen_roots = set(payload.get("clientSeenRootIds") or [])
    structure, notes, locks = build_view_snapshot(
        editing_note_id=editing_note_id or None,
        search=search or None,
        client_known_note_ids=set(client_hashes.keys()),
        client_seen_root_ids=seen_roots,
    )

    # Send only changed notes: compare client hashes to computed hashes
    filtered_notes = {
        note_id: data
        for note_id, data in notes.items()
        if client_hashes.get(note_id) != data.get("hash")
    }

    response = {
        "snapshot": {
            "structure": structure,
            "notes": filtered_notes,
            "locks": locks,
            "updateUUID": "",
            "version": VERSION,
            "currentClientId": client_id,
            "searchQuery": search,
            "editingNoteId": editing_note_id,
        },
        "updateUUID": "",
    }
    return response


@router.post("/notes/check-updates")
def check_updates(payload: dict):
    cmd = CmdCheckUpdates(client_id=payload["clientId"], last_update_uuid=payload["lastUpdateUUID"])
    return cmd.execute()


@router.post("/notes/acquire-lock")
def acquire_lock(payload: dict):
    cmd = CmdAcquireLock(note_id=payload["noteId"], client_id=payload["clientId"]) 
    result = cmd.execute()
    if not result.get("success") and result.get("conflict"):
        raise HTTPException(status_code=409, detail="Note is locked by another client")
    return result


@router.post("/notes/release-lock")
def release_lock(payload: dict):
    cmd = CmdReleaseLock(note_id=payload["noteId"], client_id=payload["clientId"]) 
    return cmd.execute()


# Stub endpoints for the rest of the notes API (501 Not Implemented)

def _not_impl(exc: Exception) -> None:
    # Turn NotImplementedError into HTTP 501; re-raise anything else
    if isinstance(exc, NotImplementedError):
        raise HTTPException(status_code=501, detail=str(exc))
    raise exc


@router.post("/notes/new")
def create_note_top(body: dict):
    cmd = CmdCreateNote(
        first_visible_note_id=body.get("first_visible_note_id"),
        search_query=body.get("search_query"),
        client_id=body["clientId"],
    )
    return cmd.execute()


@router.post("/notes/new-drop")
def create_drop_stub(body: dict):
    try:
        return CmdCreateDrop().execute()
    except Exception as e:
        _not_impl(e)


@router.post("/notes/new-sibling/{note_id}")
def create_sibling(note_id: str, body: dict):
    cmd = CmdCreateSibling(
        reference_note_id=note_id,
        search_query=body.get("search_query"),
        client_id=body["clientId"],
    )
    return cmd.execute()


@router.post("/notes/new-child/{note_id}")
def create_child(note_id: str, body: dict):
    cmd = CmdCreateChild(parent_note_id=note_id, client_id=body["clientId"]) 
    return cmd.execute()


@router.put("/notes/{note_id}")
def update_note(note_id: str, body: dict):
    # Required fields; let KeyError surface for missing keys
    client_id = body["clientId"]
    content = body["content"]
    cmd = CmdUpdateContent(note_id=note_id, content=content, client_id=client_id)
    return cmd.execute()


@router.put("/notes/{note_id}/save")
def save_note(note_id: str, body: dict):
    client_id = body["clientId"]
    content = body["content"]
    cmd = CmdUpdateContent(note_id=note_id, content=content, client_id=client_id)
    return cmd.execute()


@router.post("/notes/{note_id}/move")
def move_note_endpoint(note_id: str, body: dict):
    cmd = CmdMove(
        note_id=note_id,
        sibling_id=body.get("sibling_id"),
        position=body.get("position"),
        new_parent_id=body.get("new_parent_id"),
        client_id=body["clientId"],
    )
    return cmd.execute()


@router.post("/notes/{note_id}/collapse")
def collapse_endpoint(note_id: str, body: dict):
    cmd = CmdCollapse(note_id=note_id, client_id=body["clientId"])
    return cmd.execute()


@router.post("/notes/{note_id}/expand")
def expand_endpoint(note_id: str, body: dict):
    cmd = CmdExpand(note_id=note_id, client_id=body["clientId"])
    return cmd.execute()


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, body: dict):
    client_id = body["clientId"]
    cmd = CmdDeleteSubtree(note_id=note_id, client_id=client_id)
    return cmd.execute()


@router.post("/notes/{note_id}/copy")
def copy_note_endpoint(note_id: str, body: dict):
    cmd = CmdCopyNote(note_id=note_id, client_id=body["clientId"])  
    return cmd.execute()


@router.get("/notes/{note_id}/export-html")
def export_html_stub(note_id: str):
    try:
        return CmdExportHtml().execute()
    except Exception as e:
        _not_impl(e)


@router.post("/notes/paste-sibling/{target_note_id}")
def paste_sibling_endpoint(target_note_id: str, body: dict):
    cmd = CmdPasteSibling(target_note_id=target_note_id, client_id=body["clientId"]) 
    return cmd.execute()


@router.post("/notes/paste-child/{target_note_id}")
def paste_child_endpoint(target_note_id: str, body: dict):
    cmd = CmdPasteChild(target_note_id=target_note_id, client_id=body["clientId"]) 
    return cmd.execute()


@router.post("/notes/undo")
def undo_endpoint(client_id: str, searchContext: str = Query(...)):
    return CmdUndo(client_id=client_id, search_context=searchContext).execute()


@router.post("/notes/redo")
def redo_endpoint(client_id: str, searchContext: str = Query(...)):
    return CmdRedo(client_id=client_id, search_context=searchContext).execute()
