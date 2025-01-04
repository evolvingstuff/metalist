from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Note(BaseModel):
    id: str
    content: str
    
    # Old fields for linked list implementation
    parent_id: Optional[str] = None
    prev_id: Optional[str] = None
    next_id: Optional[str] = None
    
    # New fields for position-based implementation
    position: Optional[str] = None  # Lexicographically ordered position string
    indent: Optional[int] = None    # Indentation level, derived from tree structure
    
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True