from pydantic import BaseModel


class UpdateNoteContent(BaseModel):
    content: str
