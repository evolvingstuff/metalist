from pydantic import BaseModel
from datetime import datetime
from typing import List

class Note(BaseModel):
    id: str
    content: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True