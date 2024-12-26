from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..models.database import DBNote
from ..models.entities import Note
from ..models.commands import UpdateNoteContent
from ..models.linked_list import LinkedListManager, MovePosition
from .dependencies import get_db
import uuid
from pydantic import BaseModel, Field
from typing import Optional
from ..decorators import api_transaction_decorator, db_transaction_decorator
from ..global_state_mod import global_state
from ..core.config import ENABLE_UNDO_REDO

router = APIRouter()


class MoveNoteCommand(BaseModel):
    new_parent_id: Optional[str] = Field(default=None)
    sibling_id: Optional[str] = None
    position: Optional[str] = None  # "BEFORE" or "AFTER"


@router.post("/undo")
@db_transaction_decorator
def undo(db: Session = Depends(get_db)):
    if not ENABLE_UNDO_REDO:
        return {"status": "noop", "message": "Undo and redo are turned off"}
    # command_stack = global_state["command_stack"]
    # if command_stack.current_index >= 0:
    #     command_stack.undo(db)
    undid = LinkedListManager.undo(db)
    if undid:
        return {"status": "success", "message": "Undo successful"}
    else:
        return {"status": "noop", "message": "No actions to undo"}

@router.post("/redo")
@db_transaction_decorator
def redo(db: Session = Depends(get_db)):
    if not ENABLE_UNDO_REDO:
        return {"status": "noop", "message": "Undo and redo are turned off"}
    # command_stack = global_state["command_stack"]
    # if command_stack.current_index < len(command_stack.stack) - 1:
    #     command_stack.redo(db)
    redid = LinkedListManager.redo(db)
    if redid:
        return {"status": "success", "message": "Redo successful"}
    else:
        return {"status": "noop", "message": "No actions to redo"}


@router.post("/new")
@db_transaction_decorator
@api_transaction_decorator
def create_note_top(db: Session = Depends(get_db), parent_id: str = None):
    note_id = str(uuid.uuid4())
    LinkedListManager.create_note_top(db, note_id, parent_id)
    return {"id": note_id}

@router.put("/{note_id}")
@db_transaction_decorator
@api_transaction_decorator
def update_note(note_id: str, command: UpdateNoteContent, db: Session = Depends(get_db)):
    print(f"DEBUG: Updating note {note_id} with content: {command.content}")
    # TODO refactor this into
    #  LinkedListManager.update_note(db, note_id)
    db_note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    db_note.content = command.content
    return Note.from_orm(db_note)



@router.post("/{note_id}/move")
@db_transaction_decorator
@api_transaction_decorator
def move_note(
    note_id: str, 
    command: MoveNoteCommand, 
    db: Session = Depends(get_db)
):
    """Move a note to a new position"""
    
    def print_tree(parent_id=None, level=0):
        notes = LinkedListManager.get_ordered_child_list(db, parent_id)
        result = ""
        for note in notes:
            result += "    " * level + f"{note.content}\n"
            result += print_tree(note.id, level + 1)
        return result
    
    # Validate notes exist
    note = db.get(DBNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    if command.sibling_id:
        sibling = db.get(DBNote, command.sibling_id)
        if not sibling:
            raise HTTPException(status_code=404, detail="Sibling note not found")

        # Check if both notes will be at the same level (both root or both under same parent)
        if command.new_parent_id != sibling.parent_id:
            raise HTTPException(status_code=400, detail="Sibling must be at the same level")
    
    # Convert string position to enum
    position = None
    if command.position:
        try:
            position = MovePosition[command.position.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid position value")

    try:
        LinkedListManager.move_note(
            db=db,
            note_id=note_id,
            new_parent_id=command.new_parent_id,
            sibling_id=command.sibling_id,
            position=MovePosition[command.position] if command.position else None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"status": "success"}

@router.delete("/{note_id}")
@db_transaction_decorator
@api_transaction_decorator
# @api_transaction_decorator
def delete_note(note_id: str, db: Session = Depends(get_db)):
    note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    LinkedListManager.delete_note(db, note_id)
    return {"status": "success"}


@router.post("/new-drop")
@db_transaction_decorator
@api_transaction_decorator
# @api_transaction_decorator
def create_note_with_position(
    command: MoveNoteCommand,
    db: Session = Depends(get_db)
):
    note_id = str(uuid.uuid4())
    LinkedListManager.create_note_drop(
        db, 
        note_id, 
        command.new_parent_id,
        sibling_id=command.sibling_id,
        position=MovePosition[command.position] if command.position else None
    )
    return {"id": note_id}

@router.post("/new-sibling/{note_id}")
@db_transaction_decorator
@api_transaction_decorator
# @api_transaction_decorator
def create_new_sibling(note_id: str, db: Session = Depends(get_db)):
    # Generate a new note ID
    new_note_id = str(uuid.uuid4())
    
    # Create the new note at the top level
    LinkedListManager.create_note_top(db, new_note_id)
    
    # Find the parent of the specified note
    note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Move the new note to be a sibling of the specified note
    LinkedListManager.move_note(
        db=db,
        note_id=new_note_id,
        new_parent_id=note.parent_id,  # Use the same parent as the sibling
        sibling_id=note_id,
        position=MovePosition.AFTER
    )
    
    return {"id": new_note_id}

@router.post("/new-child/{note_id}")
@db_transaction_decorator
@api_transaction_decorator
def create_new_child(note_id: str, db: Session = Depends(get_db)):
    # Generate a new note ID
    new_note_id = str(uuid.uuid4())
    
    # Create the new note at the top level
    LinkedListManager.create_note_top(db, new_note_id)
    
    # Move the new note to be a child of the specified note
    LinkedListManager.move_note(
        db=db,
        note_id=new_note_id,
        new_parent_id=note_id,
        sibling_id=None,
        position=None
    )
    
    return {"id": new_note_id}
