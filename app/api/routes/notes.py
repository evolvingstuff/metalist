from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.usecases.view import CmdView
from app.services.snapshot import build_view_snapshot
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

    update_uuid = get_current_sync_uuid()

    response = {
        "snapshot": {
            "structure": structure,
            "notes": filtered_notes,
            "locks": locks,
            "updateUUID": update_uuid,
            "version": VERSION,
            "currentClientId": client_id,
            "searchQuery": search,
            "editingNoteId": editing_note_id,
        },
        "updateUUID": update_uuid,
    }
    return response


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
