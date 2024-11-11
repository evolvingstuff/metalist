from pydantic import BaseModel
from typing import Optional

class UpdateNoteContent(BaseModel):
    content: Optional[str] = None

class AddNoteTag(BaseModel):
    tag: str

class RemoveNoteTag(BaseModel):
    tag: str 