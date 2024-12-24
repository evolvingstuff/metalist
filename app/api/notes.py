from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..models.database import DBNote
from ..models.entities import Note
from ..models.commands import UpdateNoteContent, MoveNote
from ..models.linked_list import LinkedListManager, Position
from .dependencies import get_db
import uuid
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()

@router.post("/new")
def create_note_top(db: Session = Depends(get_db), parent_id: str = None):
    note_id = str(uuid.uuid4())
    LinkedListManager.create_note_top(db, note_id, parent_id)
    return {"id": note_id}

@router.put("/{note_id}")
def update_note(note_id: str, command: UpdateNoteContent, db: Session = Depends(get_db)):
    db_note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    db_note.content = command.content
    db.commit()
    return Note.from_orm(db_note)

class MoveNoteCommand(BaseModel):
    new_parent_id: Optional[str] = Field(default=None)
    sibling_id: Optional[str] = None
    position: Optional[str] = None  # "BEFORE" or "AFTER"

@router.post("/{note_id}/move")
def move_note(
    note_id: str, 
    command: MoveNoteCommand, 
    db: Session = Depends(get_db)
):
    """Move a note to a new position"""
    # print("\nMove note request:")
    # print(f"note_id: {note_id}")
    # print(f"Raw command data:", command.model_dump())
    
    def print_tree(parent_id=None, level=0):
        notes = LinkedListManager.get_ordered_child_list(db, parent_id)
        result = ""
        for note in notes:
            result += "    " * level + f"{note.content}\n"
            result += print_tree(note.id, level + 1)
        return result

    # print("\nBEFORE MOVE:")
    # print(print_tree())
    
    # Validate notes exist
    note = db.query(DBNote).get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    if command.sibling_id:
        sibling = db.query(DBNote).get(command.sibling_id)
        if not sibling:
            raise HTTPException(status_code=404, detail="Sibling note not found")
        
        # print(f"\nNote parent_id: {note.parent_id}")
        # print(f"Sibling parent_id: {sibling.parent_id}")
        # print(f"New parent_id: {command.new_parent_id}")
        # print(f"Types - Sibling parent_id: {type(sibling.parent_id)}, New parent_id: {type(command.new_parent_id)}")
        # print(f"Raw values - Sibling: {repr(sibling.parent_id)}, New: {repr(command.new_parent_id)}")

        # Check if both notes will be at the same level (both root or both under same parent)
        if command.new_parent_id != sibling.parent_id:
            raise HTTPException(status_code=400, detail="Sibling must be at the same level")
    
    # Convert string position to enum
    position = None
    if command.position:
        try:
            position = Position[command.position.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid position value")

    try:
        LinkedListManager.move_note(
            db=db,
            note_id=note_id,
            new_parent_id=command.new_parent_id,
            sibling_id=command.sibling_id,
            position=Position[command.position] if command.position else None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # print("\nAFTER MOVE:")
    # print(print_tree())
    
    return {"status": "success"}

@router.delete("/{note_id}")
def delete_note(note_id: str, db: Session = Depends(get_db)):
    note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    LinkedListManager.delete_note(db, note_id)
    return {"status": "success"}

@router.get("/")
def get_notes(db: Session = Depends(get_db)):
    notes = LinkedListManager.get_ordered_child_list(db)
    return [Note.from_orm(note) for note in notes]

@router.get("/debug")
def debug_notes(db: Session = Depends(get_db)):
    notes = db.query(DBNote).all()
    return [{
        'id': note.id,
        'content': note.content,
        'prev_id': note.prev_id,
        'next_id': note.next_id,
        'created_at': note.created_at.isoformat()
    } for note in notes]

@router.post("/new-drop")
def create_note_with_position(
    command: MoveNoteCommand,
    db: Session = Depends(get_db)
):
    # print("\nNew note drop request:")
    # print(f"new_parent_id: {command.new_parent_id}")
    # print(f"sibling_id: {command.sibling_id}")
    # print(f"position: {command.position}")
    
    note_id = str(uuid.uuid4())
    LinkedListManager.create_note_drop(
        db, 
        note_id, 
        command.new_parent_id,
        sibling_id=command.sibling_id,
        position=Position[command.position] if command.position else None
    )
    return {"id": note_id}
