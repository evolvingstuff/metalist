from pydantic import BaseModel
from typing import Optional


class UpdateNoteContent(BaseModel):
    content: str
    clientId: Optional[str] = None
