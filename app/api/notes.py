from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..models.database import DBNote
from ..models.entities import Note
from ..models.commands import UpdateNoteContent, MoveNote
from ..models.linked_list import LinkedListManager, Position
from .dependencies import get_db
import uuid
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()

@router.post("/new")
async def create_note(db: Session = Depends(get_db), parent_id: str = None):
    note_id = str(uuid.uuid4())
    
    # Create new note
    db_note = DBNote(id=note_id, content="", parent_id=parent_id)
    db.add(db_note)
    
    # Find the current head (note with no prev_id)
    current_head = db.query(DBNote).filter(
        DBNote.prev_id == None,
        DBNote.parent_id == parent_id
    ).first()
    
    if current_head:
        # Make new note the head
        current_head.prev_id = note_id
        db_note.next_id = current_head.id
    
    db.commit()
    return {"id": note_id}

@router.put("/{note_id}")
async def update_note(note_id: str, command: UpdateNoteContent, db: Session = Depends(get_db)):
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
async def move_note(
    note_id: str, 
    command: MoveNoteCommand, 
    db: Session = Depends(get_db)
):
    """Move a note to a new position"""
    print("\nMove note request:")
    print(f"note_id: {note_id}")
    print(f"Raw command data:", command.model_dump())
    
    def print_tree(parent_id=None, level=0):
        notes = LinkedListManager.get_ordered_child_list(db, DBNote, parent_id)
        result = ""
        for note in notes:
            result += "    " * level + f"{note.content}\n"
            result += print_tree(note.id, level + 1)
        return result

    print("\nBEFORE MOVE:")
    print(print_tree())
    
    # Validate notes exist
    note = db.query(DBNote).get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    if command.sibling_id:
        sibling = db.query(DBNote).get(command.sibling_id)
        if not sibling:
            raise HTTPException(status_code=404, detail="Sibling note not found")
        
        print(f"\nNote parent_id: {note.parent_id}")
        print(f"Sibling parent_id: {sibling.parent_id}")
        print(f"New parent_id: {command.new_parent_id}")
        print(f"Types - Sibling parent_id: {type(sibling.parent_id)}, New parent_id: {type(command.new_parent_id)}")
        print(f"Raw values - Sibling: {repr(sibling.parent_id)}, New: {repr(command.new_parent_id)}")
        
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
            model_class=DBNote,
            note_id=note_id,
            new_parent_id=command.new_parent_id,
            sibling_id=command.sibling_id,
            position=Position[command.position] if command.position else None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    print("\nAFTER MOVE:")
    print(print_tree())
    
    return {"status": "success"}

@router.delete("/{note_id}")
async def delete_note(note_id: str, db: Session = Depends(get_db)):
    note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Update links
    if note.prev_id:
        prev_note = db.query(DBNote).get(note.prev_id)
        prev_note.next_id = note.next_id
    if note.next_id:
        next_note = db.query(DBNote).get(note.next_id)
        next_note.prev_id = note.prev_id
        
    # Recursively delete children
    children = db.query(DBNote).filter(DBNote.parent_id == note_id).all()
    for child in children:
        await delete_note(child.id, db)
    
    db.delete(note)
    db.commit()
    return {"status": "success"}

@router.get("/")
async def get_notes(db: Session = Depends(get_db)):
    notes = LinkedListManager.get_ordered_child_list(db, DBNote)
    return [Note.from_orm(note) for note in notes]

@router.get("/debug")
async def debug_notes(db: Session = Depends(get_db)):
    notes = db.query(DBNote).all()
    return [{
        'id': note.id,
        'content': note.content,
        'prev_id': note.prev_id,
        'next_id': note.next_id,
        'created_at': note.created_at.isoformat()
    } for note in notes]
