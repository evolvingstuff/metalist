from pydantic import BaseModel
from typing import Optional

class UpdateNoteContent(BaseModel):
    content: str

class MoveNote(BaseModel):
    target_id: str  # Move this note after target_id (or to start if None)

class AddTag(BaseModel):
    name: str

class MoveTag(BaseModel):
    tag_id: str
    target_id: Optional[str]  # Move this tag after target_id (or to start if None) 