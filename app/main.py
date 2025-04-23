from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from mako.lookup import TemplateLookup
from sqlalchemy.orm import Session
from .api import notes, dev
from .core.config import VERSION, CACHE_BUSTER
from .models.database import Base, SafeSession
from .api.dependencies import get_db
from .models.linked_list import LinkedListManager
import logging

logger = logging.getLogger(__name__)

app = FastAPI()

Base.metadata.create_all(bind=SafeSession.get_engine())

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

templates = TemplateLookup(
    directories=[Path(__file__).parent / "templates"],
    module_directory=str(Path(__file__).parent / "__pycache__" / "mako_modules"),
    input_encoding="utf-8"
)

app.include_router(notes.router, prefix="/api/notes", tags=["notes"])
app.include_router(dev.router, prefix="/dev", tags=["dev"])

@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            logger.error(f"Request failed: {request.method} {request.url} - Status: {response.status_code}")
        return response
    except Exception as e:
        logger.exception(f"Unhandled error in request: {request.method} {request.url}")
        return JSONResponse(
            status_code=500,
            content={"detail": str(e)}
        )

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    try:
        # TODO: remove eventually?
        valid = LinkedListManager.validate_list(db, None)
        if not valid:
            logger.error("List validation failed")
            raise HTTPException(status_code=500, detail="Database list validation failed")

        template = templates.get_template("index.html")
        
        def build_tree(parent_id=None):
            try:
                notes = LinkedListManager.get_ordered_child_list(db, parent_id)
                return [{
                    'id': note.id,
                    'content': note.content,
                    'parent_id': note.parent_id or '',
                    'children': build_tree(note.id),
                    'flags': {
                        'isEditing': False,
                        'isCollapsed': False,
                        'isHighlighted': False,
                        'isRendered': False
                    }
                } for note in notes]
            except Exception as e:
                logger.exception("Error building note tree")
                raise
        
        notes = build_tree(None)
        return template.render(request=request, notes=notes, version=VERSION, cache_buster=CACHE_BUSTER)
    except Exception as e:
        logger.exception("Error in home route")
        raise