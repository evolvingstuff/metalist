from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..models.schemas import Note, NoteCreate, NoteUpdate
from ..models.database import DBNote, DBTag
from .dependencies import get_db
from mako.lookup import TemplateLookup
import uuid

router = APIRouter()

@router.get("/")
async def get_notes(db: Session = Depends(get_db)):
    notes = db.query(DBNote).order_by(DBNote.created_at.desc()).all()
    return [{
        "id": note.id,
        "content": note.content,
        "updated_at": note.updated_at.isoformat()
    } for note in notes]

@router.post("/new")
async def create_note(db: Session = Depends(get_db)):
    db_note = DBNote(
        id=str(uuid.uuid4()),
        content=""
    )
    db.add(db_note)
    db.commit()
    return {"id": db_note.id}

@router.put("/{note_id}")
async def update_note(note_id: str, note_update: NoteUpdate, db: Session = Depends(get_db)):
    db_note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    if note_update.content is not None:
        db_note.content = note_update.content
    
    db.commit()
    db.refresh(db_note)
    
    return {
        "id": db_note.id,
        "content": db_note.content,
        "updated_at": db_note.updated_at.isoformat()
    }
