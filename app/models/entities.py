from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Note(BaseModel):
    id: str
    content: str
    next_id: Optional[str] = None
    prev_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Tag(BaseModel):
    id: str
    name: str
    next_id: Optional[str] = None
    prev_id: Optional[str] = None