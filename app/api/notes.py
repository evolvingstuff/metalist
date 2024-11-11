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
    db_note = DBNote(id=note_id, content="")
    db.add(db_note)
    db.commit()
    
    tail = db.query(DBNote).filter(DBNote.next_id == None).first()
    if tail and tail.id != note_id:
        tail.next_id = note_id
        db_note.prev_id = tail.id
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
    LinkedListManager.insert_after(db, DBNote, note_id, command.target_id)
    return {"status": "success"}

@router.get("/")
async def get_notes(db: Session = Depends(get_db)):
    notes = LinkedListManager.get_ordered_list(db, DBNote)
    return [Note.from_orm(note) for note in notes]
