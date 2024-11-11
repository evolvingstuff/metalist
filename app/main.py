from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from mako.lookup import TemplateLookup
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from typing import Optional, Set, List
from datetime import datetime
import uuid

VERSION = "0.1.3"

# FastAPI setup
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Setup Mako templates
templates = TemplateLookup(
    directories=[Path(__file__).parent / "templates"],
    module_directory=str(Path(__file__).parent / "__pycache__" / "mako_modules"),
    input_encoding="utf-8"
)

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./notes.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class DBNote(Base):
    __tablename__ = "notes"
    
    id = Column(String, primary_key=True)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DBTag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(String, ForeignKey("notes.id"))
    name = Column(String)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic Models
class NoteCreate(BaseModel):
    content: str = ""
    tags: Set[str] = set()

class NoteUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[Set[str]] = None

class Note(BaseModel):
    id: str
    content: str
    tags: Set[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# Dependencies
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    template = templates.get_template("index.html")
    notes = db.query(DBNote).order_by(DBNote.created_at.desc()).all()
    
    notes_with_tags = []
    for note in notes:
        tags = {tag.name for tag in db.query(DBTag).filter(DBTag.note_id == note.id)}
        notes_with_tags.append({
            "id": note.id,
            "content": note.content,
            "tags": tags,
            "created_at": note.created_at,
            "updated_at": note.updated_at
        })
    
    return template.render(
        notes=notes_with_tags, 
        version=VERSION,
        timestamp=datetime.now().strftime("%H:%M:%S")
    )

@app.post("/notes/new")
async def create_note_form(
    request: Request,
    content: str = Form(""),
    tags: str = Form(""),
    db: Session = Depends(get_db)
):
    # Convert comma-separated tags to a set
    tag_set = {tag.strip() for tag in tags.split(",") if tag.strip()}
    
    # Create note
    db_note = DBNote(
        id=str(uuid.uuid4()),
        content=content
    )
    db.add(db_note)
    
    # Add tags
    for tag_name in tag_set:
        db_tag = DBTag(note_id=db_note.id, name=tag_name)
        db.add(db_tag)
    
    db.commit()
    
    # Redirect back to home page
    return RedirectResponse(url="/", status_code=303)

@app.put("/api/notes/{note_id}", response_model=Note)
async def update_note(note_id: str, note_update: NoteUpdate, db: Session = Depends(get_db)):
    db_note = db.query(DBNote).filter(DBNote.id == note_id).first()
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    if note_update.content is not None:
        db_note.content = note_update.content
    
    if note_update.tags is not None:
        # Remove existing tags
        db.query(DBTag).filter(DBTag.note_id == note_id).delete()
        
        # Add new tags
        for tag_name in note_update.tags:
            db_tag = DBTag(note_id=note_id, name=tag_name)
            db.add(db_tag)
    
    db.commit()
    db.refresh(db_note)
    
    # Get tags for response
    tags = {tag.name for tag in db.query(DBTag).filter(DBTag.note_id == db_note.id)}
    
    return Note(
        id=db_note.id,
        content=db_note.content,
        tags=tags,
        created_at=db_note.created_at,
        updated_at=db_note.updated_at
    )

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str, db: Session = Depends(get_db)):
    # Delete tags first (due to foreign key constraint)
    db.query(DBTag).filter(DBTag.note_id == note_id).delete()
    
    # Delete note
    result = db.query(DBNote).filter(DBNote.id == note_id).delete()
    if not result:
        raise HTTPException(status_code=404, detail="Note not found")
    
    db.commit()
    return {"status": "success"}

@app.get("/api/notes/")
async def get_notes(db: Session = Depends(get_db)):
    notes = db.query(DBNote).order_by(DBNote.created_at.desc()).all()
    return [{
        "id": note.id,
        "content": note.content,
        "updated_at": note.updated_at.isoformat()
    } for note in notes]

@app.post("/api/notes/new")
async def create_blank_note(db: Session = Depends(get_db)):
    db_note = DBNote(
        id=str(uuid.uuid4()),
        content=""
    )
    db.add(db_note)
    db.commit()
    
    return {"id": db_note.id}