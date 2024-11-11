from pydantic import BaseModel
from typing import Set
from datetime import datetime

class Note(BaseModel):
    id: str
    content: str
    tags: Set[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True 