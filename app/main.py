from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
from mako.lookup import TemplateLookup
from sqlalchemy.orm import Session
from .api import notes
from .core.config import VERSION
from .models.database import Base, DBNote
from .core.database import engine
from .api.dependencies import get_db
from .models.linked_list import LinkedListManager

app = FastAPI()

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

templates = TemplateLookup(
    directories=[Path(__file__).parent / "templates"],
    module_directory=str(Path(__file__).parent / "__pycache__" / "mako_modules"),
    input_encoding="utf-8"
)

app.include_router(notes.router, prefix="/api/notes", tags=["notes"])

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    template = templates.get_template("index.html")
    
    def build_tree(parent_id=None):
        notes = LinkedListManager.get_ordered_child_list(db, parent_id)
        return [{
            'id': note.id,
            'content': note.content,
            'parent_id': note.parent_id,
            'children': build_tree(note.id)  # Recursively get children
        } for note in notes]
    
    # Get root level notes with their children
    notes = build_tree(None)
    
    # print("\nDisplaying notes in order:")
    # for note in notes:
    #     print(f"Note {note['id']}: content={note['content']}, children={len(note.get('children', []))}")
    
    return template.render(request=request, notes=notes, version=VERSION)