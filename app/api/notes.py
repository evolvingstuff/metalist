from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import logging
import time

from .dependencies import get_db
from ..models.database import SafeSession
from ..db.notes_sql import fetch_children_ordered, update_links
from types import SimpleNamespace
from ..models.commands import UpdateNoteContent
from ..models.enums import MovePosition
from ..services.dependencies import (
    get_note_service, 
    get_query_service, 
    get_undo_service,
    apply_delay
)
from ..services.transaction_manager import get_transaction_manager, TransactionManager
from ..services.sync_state import (
    get_current_sync_uuid, acquire_note_lock, release_note_lock, generate_new_uuid, set_server_sync_uuid,
    get_client_clipboard, set_client_clipboard, cleanup_expired_locks
)
from ..models.utils import (
    copy_note_in_memory,
    count_serialized_note_tree,
    note_data_to_html,
    note_data_to_plain_text,
    render_note_data_read_only,
)
from ..core.config import VERSION

logger = logging.getLogger(__name__)
router = APIRouter()


class MoveNoteCommand(BaseModel):
    new_parent_id: Optional[str] = Field(default=None)
    sibling_id: Optional[str] = None
    position: Optional[str] = None  # "BEFORE" or "AFTER"
    clientId: str


class CreateNoteCommand(BaseModel):
    first_visible_note_id: Optional[str] = Field(default=None)
    search_query: Optional[str] = Field(default=None)
    clientId: str


class CreateSiblingCommand(BaseModel):
    search_query: Optional[str] = Field(default=None)
    clientId: str


class CreateChildCommand(BaseModel):
    clientId: str


class SyncCheckRequest(BaseModel):
    clientId: str
    lastUpdateUUID: Optional[str] = Field(default=None)


class NoteLockRequest(BaseModel):
    noteId: str
    clientId: str
    lastUpdateUUID: Optional[str] = Field(default=None)


class CopyNoteRequest(BaseModel):
    clientId: str
    lastUpdateUUID: Optional[str] = Field(default=None)


class NoteStateCommand(BaseModel):
    clientId: str
    lastUpdateUUID: Optional[str] = Field(default=None)


class ViewDiffRequest(BaseModel):
    client_id: Optional[str] = Field(default=None, alias="clientId")
    editing_note_id: Optional[str] = Field(default=None, alias="editingNoteId")
    search: Optional[str] = None
    client_note_uuid_hashes: Dict[str, str] = Field(default_factory=dict, alias="clientNoteUuidHashes")

    class Config:
        populate_by_name = True


@router.post("/check-updates")
def check_updates(request: SyncCheckRequest):
    """Check if client needs to refresh based on sync UUID"""
    # Clean up any expired locks and generate new UUID if any were removed
    if cleanup_expired_locks():
        new_uuid = generate_new_uuid()
        set_server_sync_uuid(new_uuid)
    
    current_uuid = get_current_sync_uuid()
    previous_uuid = request.lastUpdateUUID

    needs_update = bool(previous_uuid) and previous_uuid != current_uuid

    return {
        "needsUpdate": needs_update,
        "currentUpdateUUID": current_uuid
    }


@router.post("/acquire-lock")
def acquire_lock(request: NoteLockRequest):
    """Acquire an edit lock on a note"""
    success, expired_lock_removed = acquire_note_lock(request.noteId, request.clientId)
    
    if success:
        # Generate sync event when lock is acquired or when expired lock was removed
        new_uuid = generate_new_uuid()
        set_server_sync_uuid(new_uuid)
        
        return {
            "success": True,
            "updateUUID": new_uuid
        }
    else:
        raise HTTPException(status_code=409, detail="Note is locked by another client")


@router.post("/release-lock")  
def release_lock(request: NoteLockRequest):
    """Release an edit lock on a note"""
    release_note_lock(request.noteId, request.clientId)
    
    # Generate sync event when lock is released
    new_uuid = generate_new_uuid()
    set_server_sync_uuid(new_uuid)
    
    return {
        "success": True,
        "updateUUID": new_uuid
    }


@router.post("/undo")
def undo(
    client_id: Optional[str] = None,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Undo the last operation"""
    apply_delay("undo")
    
    with get_undo_service(db, transaction_manager) as service:
        return service.undo(client_id)


@router.post("/redo")
def redo(
    client_id: Optional[str] = None,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Redo the last undone operation"""
    apply_delay("redo")
    
    with get_undo_service(db, transaction_manager) as service:
        return service.redo(client_id)


@router.post("/{note_id}/copy")
def copy_note(
    note_id: str,
    request: CopyNoteRequest,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Copy a note to the server-side clipboard as serialized data"""
    apply_delay("copy_note")
    
    with get_note_service(db, transaction_manager, request.clientId) as service:
        try:
            # Serialize the note tree to pure data (no database writes)
            with SafeSession.allow_reads("copy_note"):
                note_data = copy_note_in_memory(db, note_id)

            # Store the serialized data in the client's server-side clipboard
            set_client_clipboard(request.clientId, note_data)

            # Produce rendered variants for the system clipboard
            rendered_tree = render_note_data_read_only(note_data)
            rendered_html = note_data_to_html(rendered_tree)
            rendered_plain_text = note_data_to_plain_text(rendered_tree)

            return {
                "status": "success",
                "html": rendered_html,
                "plain_text": rendered_plain_text
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.get("/{note_id}/export-html")
def export_note_as_html(
    note_id: str,
    client_id: str,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Export a note and all its children as HTML"""
    apply_delay("export_note_html")
    
    with get_note_service(db, transaction_manager, client_id) as service:
        try:
            # Serialize the note tree to pure data
            with SafeSession.allow_reads("export_note"):
                note_data = copy_note_in_memory(db, note_id)
            
            rendered_tree = render_note_data_read_only(note_data)
            html = note_data_to_html(rendered_tree)
            plain_text = note_data_to_plain_text(rendered_tree)
            
            return {"html": html, "plain_text": plain_text}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.post("/new")
def create_note_top(
    command: CreateNoteCommand,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Create a new note at the top of the list (or before first visible note)"""
    apply_delay("create_note_top")
    
    with get_note_service(db, transaction_manager, command.clientId) as service:
        result = service.create_note(None, command.first_visible_note_id, command.search_query)
        return {"id": result["id"]}


@router.put("/{note_id}")
def update_note(
    note_id: str,
    command: UpdateNoteContent,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Update a note's content"""
    apply_delay("update_note")
    
    with get_note_service(db, transaction_manager, command.clientId) as service:
        try:
            result = service.update_note(note_id, command.content)
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Note not found")


@router.put("/{note_id}/save")
def save_note(
    note_id: str,
    command: UpdateNoteContent,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Save a note's content (same as update_note)"""
    apply_delay("save_note")
    
    # Reuse update_note logic
    return update_note(note_id, command, db, transaction_manager)


@router.post("/{note_id}/move")
def move_note(
    note_id: str,
    command: MoveNoteCommand,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Move a note to a new position"""
    apply_delay("move_note")
    
    # Convert string position to enum
    position = None
    if command.position:
        try:
            position = MovePosition[command.position.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid position value")
    
    with get_note_service(db, transaction_manager, command.clientId) as service:
        try:
            service.move_note(
                note_id=note_id,
                new_parent_id=command.new_parent_id,
                sibling_id=command.sibling_id,
                position=position
            )
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


class PasteRequest(BaseModel):
    clientId: str
    lastUpdateUUID: Optional[str] = Field(default=None)


@router.post("/paste-sibling/{target_note_id}")
def paste_sibling(
    target_note_id: str,
    request: PasteRequest,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Paste clipboard content as a sibling after target_note"""
    apply_delay("paste_sibling")
    
    # Get the current clipboard content
    clipboard_data = get_client_clipboard(request.clientId)
    if not clipboard_data:
        raise HTTPException(status_code=400, detail="Nothing in clipboard to paste")
    
    with get_note_service(db, transaction_manager, request.clientId) as service:
        service._set_operation("paste_sibling")
        service.expect_note_delta(count_serialized_note_tree(clipboard_data))
        try:
            # Get target note first
            from ..models.linked_list import LinkedListManager
            with SafeSession.allow_reads("paste_sibling:target"):
                target_note = LinkedListManager.get_note(db, target_note_id)

            # Deserialize clipboard data into real database notes positioned as sibling
            from ..models.utils import paste_note_from_memory
            with SafeSession.allow_reads("paste_sibling:deserialize"):
                new_note_id = paste_note_from_memory(db, clipboard_data, target_note.parent_id)

            from ..services.note_store import store as note_store
            if note_store.loaded:
                with SafeSession.allow_reads("paste_sibling:refresh_store_before_move"):
                    note_store.load_from_db(db)
                try:
                    note_store.get_note(new_note_id)
                except KeyError as exc:
                    raise RuntimeError(
                        f"NoteStore failed to register new sibling {new_note_id} before move: {exc}"
                    ) from exc

            # Reuse linked list manager to position after the target
            from ..models.enums import MovePosition
            LinkedListManager.move_note(
                db,
                note_id=new_note_id,
                new_parent_id=target_note.parent_id,
                sibling_id=target_note_id,
                position=MovePosition.AFTER,
            )
            
            if note_store.loaded:
                with SafeSession.allow_reads("paste_sibling:refresh_store"):
                    note_store.load_from_db(db)

                try:
                    note_store.get_note(new_note_id)
                except KeyError as exc:
                    raise RuntimeError(
                        f"NoteStore did not load newly pasted note {new_note_id}: {exc}"
                    ) from exc

            return {"id": new_note_id}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.post("/paste-child/{target_note_id}")
def paste_child(
    target_note_id: str,
    request: PasteRequest,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Paste clipboard content as first child of target_note"""
    apply_delay("paste_child")
    
    # Get the current clipboard content
    clipboard_data = get_client_clipboard(request.clientId)
    if not clipboard_data:
        raise HTTPException(status_code=400, detail="Nothing in clipboard to paste")
    
    with get_note_service(db, transaction_manager, request.clientId) as service:
        service._set_operation("paste_child")
        service.expect_note_delta(count_serialized_note_tree(clipboard_data))
        try:
            # Deserialize clipboard data into real database notes as child of target
            from ..models.utils import paste_note_from_memory
            with SafeSession.allow_reads("paste_child:deserialize"):
                new_note_id = paste_note_from_memory(db, clipboard_data, target_note_id)
            
            # Position as first child (the paste_note_from_memory already sets the parent)
            # We need to ensure it's positioned as the first child
            # Find existing first child of target
            with SafeSession.allow_reads("paste_child:first_child"):
                existing_children = fetch_children_ordered(db.connection(), target_note_id)
            existing_first_child = existing_children[0] if existing_children else None

            if existing_first_child and existing_first_child["id"] != new_note_id:
                update_links(
                    db.connection(),
                    new_note_id,
                    parent_id=target_note_id,
                    prev_id=None,
                    next_id=existing_first_child["id"],
                )
                update_links(
                    db.connection(),
                    existing_first_child["id"],
                    prev_id=new_note_id,
                )
            else:
                update_links(
                    db.connection(),
                    new_note_id,
                    parent_id=target_note_id,
                    prev_id=None,
                )

            from ..services.note_store import store as note_store
            if note_store.loaded:
                # TODO: Replace with targeted store update once ORM sunset is complete.
                with SafeSession.allow_reads("paste_child:refresh_store"):
                    note_store.load_from_db(db)

                try:
                    note_store.get_note(new_note_id)
                except KeyError as exc:
                    raise RuntimeError(
                        f"NoteStore did not load newly pasted child {new_note_id}: {exc}"
                    ) from exc

            return {"id": new_note_id}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.post("/{note_id}/collapse")
def collapse_note(
    note_id: str,
    request: NoteStateCommand,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Set a note's collapsed state to true"""
    apply_delay("collapse_note")

    with get_note_service(db, transaction_manager, request.clientId) as service:
        try:
            return service.set_note_collapse(note_id, True)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.post("/{note_id}/expand")
def expand_note(
    note_id: str,
    request: NoteStateCommand,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Set a note's collapsed state to false"""
    apply_delay("expand_note")

    with get_note_service(db, transaction_manager, request.clientId) as service:
        try:
            return service.set_note_collapse(note_id, False)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


class DeleteNoteRequest(BaseModel):
    clientId: str


@router.delete("/{note_id}")
def delete_note(
    note_id: str,
    request: DeleteNoteRequest,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Delete a note and all its descendants"""
    apply_delay("delete_note")
    
    with get_note_service(db, transaction_manager, request.clientId) as service:
        try:
            result = service.delete_note(note_id)
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Note not found")


@router.post("/new-drop")
def create_note_with_position(
    command: MoveNoteCommand,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Create a new note at a specific position"""
    apply_delay("create_note_drop")
    
    # Convert string position to enum
    position = None
    if command.position:
        try:
            position = MovePosition[command.position.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid position value")

    with get_note_service(db, transaction_manager, command.clientId) as service:
        result = service.create_note_with_position(
            new_parent_id=command.new_parent_id,
            sibling_id=command.sibling_id,
            position=position
        )
        return {"id": result["id"]}


@router.post("/new-sibling/{note_id}")
def create_new_sibling(
    note_id: str,
    command: CreateSiblingCommand,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Create a new note as sibling after the specified note"""
    apply_delay("create_new_sibling")
    
    with get_note_service(db, transaction_manager, command.clientId) as service:
        result = service.create_sibling_note(note_id, command.search_query)
        return {"id": result["id"]}


@router.post("/new-child/{note_id}")
def create_new_child(
    note_id: str,
    command: CreateChildCommand,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Create a new note as first child of the specified note"""
    apply_delay("create_new_child")
    
    logger.debug(f"Creating new child for note {note_id}")
    
    with get_note_service(db, transaction_manager, command.clientId) as service:
        result = service.create_child_note(note_id)
        return {"id": result["id"]}


@router.post("/view")
def get_notes_view_diff(
    request: ViewDiffRequest,
    db: SafeSession = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Return structural deltas for the notes view."""
    start_time = time.perf_counter()
    apply_delay("get_notes_view")

    transaction_manager.check_context_change(request.search)

    client_hashes = {
        note_id: note_hash
        for note_id, note_hash in request.client_note_uuid_hashes.items()
        if note_id
    }

    with get_query_service(db) as service:
        structure, payloads, locks = service.build_view_snapshot(
            editing_note_id=request.editing_note_id,
            search=request.search,
            client_id=request.client_id,
        )

    updated_notes = {
        note_id: payload
        for note_id, payload in payloads.items()
        if client_hashes.get(note_id) != payload['hash']
    }

    update_uuid = get_current_sync_uuid()
    response = {
        "snapshot": {
            "structure": structure,
            "notes": updated_notes,
            "locks": locks,
            "updateUUID": update_uuid,
            "version": VERSION,
            "currentClientId": request.client_id,
            "searchQuery": request.search,
            "editingNoteId": request.editing_note_id,
        },
        "updateUUID": update_uuid,
    }

    duration_ms = (time.perf_counter() - start_time) * 1000
    print(f"[notes.view] response_time_ms={duration_ms:.2f}")
    return response
