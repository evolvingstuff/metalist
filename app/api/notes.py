from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..models.database import DBNote
from ..models.entities import Note
from ..models.commands import UpdateNoteContent, MoveNote
from ..models.linked_list import LinkedListManager
from .dependencies import get_db
import uuid

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

@router.post("/{note_id}/move")
async def move_note(note_id: str, command: MoveNote, db: Session = Depends(get_db)):
    print(f"Moving note {note_id} relative to {command.target_id}, insert_before: {command.insert_before}, new_parent: {command.new_parent_id}")
    
    # Get both notes
    note = db.query(DBNote).get(note_id)
    target = db.query(DBNote).get(command.target_id)
    
    if not note or not target:
        raise HTTPException(status_code=404, detail="Note or target not found")
    
    # Prevent invalid moves
    if command.new_parent_id:
        # Check if target would be moved into its own descendant
        current = db.query(DBNote).get(command.new_parent_id)
        while current:
            if current.id == note_id:
                raise HTTPException(status_code=400, detail="Cannot move a note into its own descendant")
            current = db.query(DBNote).get(current.parent_id)
    
    LinkedListManager.move_note(
        db, 
        DBNote, 
        note_id, 
        command.target_id, 
        command.insert_before,
        command.new_parent_id
    )
    
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
