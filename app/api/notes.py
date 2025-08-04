from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
import logging

from .dependencies import get_db
from ..models.commands import UpdateNoteContent
from ..models.enums import MovePosition
from ..services.dependencies import (
    get_note_service, 
    get_query_service, 
    get_undo_service,
    apply_delay
)
from ..services.transaction_manager import get_transaction_manager, TransactionManager

logger = logging.getLogger(__name__)
router = APIRouter()


class MoveNoteCommand(BaseModel):
    new_parent_id: Optional[str] = Field(default=None)
    sibling_id: Optional[str] = None
    position: Optional[str] = None  # "BEFORE" or "AFTER"


@router.post("/undo")
def undo(
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Undo the last operation"""
    apply_delay("undo")
    
    with get_undo_service(db, transaction_manager) as service:
        return service.undo()


@router.post("/redo")
def redo(
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Redo the last undone operation"""
    apply_delay("redo")
    
    with get_undo_service(db, transaction_manager) as service:
        return service.redo()


@router.post("/new")
def create_note_top(
    parent_id: Optional[str] = None,
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Create a new note at the top of the list"""
    apply_delay("create_note_top")
    
    with get_note_service(db, transaction_manager) as service:
        result = service.create_note(parent_id)
        return {"id": result["id"]}


@router.put("/{note_id}")
def update_note(
    note_id: str,
    command: UpdateNoteContent,
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Update a note's content"""
    apply_delay("update_note")
    
    with get_note_service(db, transaction_manager) as service:
        try:
            result = service.update_note(note_id, command.content)
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Note not found")


@router.put("/{note_id}/save")
def save_note(
    note_id: str,
    command: UpdateNoteContent,
    db: Session = Depends(get_db)
):
    """Save a note's content (same as update_note)"""
    apply_delay("save_note")
    
    # Reuse update_note logic
    return update_note(note_id, command, db)


@router.post("/{note_id}/move")
def move_note(
    note_id: str,
    command: MoveNoteCommand,
    db: Session = Depends(get_db),
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
    
    with get_note_service(db, transaction_manager) as service:
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


@router.post("/{source_note_id}/paste-sibling/{target_note_id}")
def paste_sibling(
    source_note_id: str,
    target_note_id: str,
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Paste a copy of source_note as a sibling after target_note"""
    apply_delay("paste_sibling")
    
    with get_note_service(db, transaction_manager) as service:
        result = service.paste_note_as_sibling(source_note_id, target_note_id)
        return {"id": result["id"]}


@router.post("/{source_note_id}/paste-child/{target_note_id}")
def paste_child(
    source_note_id: str,
    target_note_id: str,
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Paste a copy of source_note as first child of target_note"""
    apply_delay("paste_child")
    
    with get_note_service(db, transaction_manager) as service:
        result = service.paste_note_as_child(source_note_id, target_note_id)
        return {"id": result["id"]}


@router.delete("/{note_id}")
def delete_note(
    note_id: str,
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Delete a note and all its descendants"""
    apply_delay("delete_note")
    
    with get_note_service(db, transaction_manager) as service:
        try:
            result = service.delete_note(note_id)
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Note not found")


@router.post("/new-drop")
def create_note_with_position(
    command: MoveNoteCommand,
    db: Session = Depends(get_db),
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
    
    with get_note_service(db, transaction_manager) as service:
        result = service.create_note_with_position(
            new_parent_id=command.new_parent_id,
            sibling_id=command.sibling_id,
            position=position
        )
        return {"id": result["id"]}


@router.post("/new-sibling/{note_id}")
def create_new_sibling(
    note_id: str,
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Create a new note as sibling after the specified note"""
    apply_delay("create_new_sibling")
    
    with get_note_service(db, transaction_manager) as service:
        result = service.create_sibling_note(note_id)
        return {"id": result["id"]}


@router.post("/new-child/{note_id}")
def create_new_child(
    note_id: str,
    db: Session = Depends(get_db),
    transaction_manager: TransactionManager = Depends(get_transaction_manager)
):
    """Create a new note as first child of the specified note"""
    apply_delay("create_new_child")
    
    logger.debug(f"Creating new child for note {note_id}")
    
    with get_note_service(db, transaction_manager) as service:
        result = service.create_child_note(note_id)
        return {"id": result["id"]}


@router.get("/fragment")
def get_notes_fragment(
    editing_note_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get the HTML fragment for the notes list"""
    apply_delay("get_notes_fragment")
    
    with get_query_service(db) as service:
        return service.get_notes_fragment(editing_note_id)