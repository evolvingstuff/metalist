from pydantic import BaseModel
from typing import Optional, Set
from datetime import datetime

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
        from_attributes = True
