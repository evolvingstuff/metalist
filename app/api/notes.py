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
async def create_note(db: Session = Depends(get_db)):
    note_id = str(uuid.uuid4())
    print(f"Creating new note with id: {note_id}")
    
    db_note = DBNote(id=note_id, content="")
    db.add(db_note)
    
    # Find the current head (note with no prev_id)
    head = db.query(DBNote).filter(DBNote.prev_id == None).first()
    print(f"Current head: {head.id if head else None}")
    
    if head and head.id != note_id:
        print(f"Linking new note as new head")
        head.prev_id = note_id
        db_note.next_id = head.id
    
    db.commit()
    print(f"Note created successfully")
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
    LinkedListManager.insert_after(db, DBNote, note_id, command.target_id)
    return {"status": "success"}

@router.get("/")
async def get_notes(db: Session = Depends(get_db)):
    notes = LinkedListManager.get_ordered_list(db, DBNote)
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
