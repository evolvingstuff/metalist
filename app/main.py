from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from mako.lookup import TemplateLookup
from sqlalchemy.orm import Session
from .api import notes, dev
from .core.config import VERSION
from .models.database import Base, SafeSession
from .api.dependencies import get_db
from .models.linked_list import LinkedListManager
import logging
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from fastapi.middleware.gzip import GZipMiddleware
import mimetypes

logger = logging.getLogger(__name__)

app = FastAPI()

Base.metadata.create_all(bind=SafeSession.get_engine())

# Custom StaticFiles class that disables caching
class NoCacheStaticFiles(StarletteStaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            # Set no-cache headers for all static files
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            
            # Log when JavaScript files are served
            if path.endswith('.js'):
                logger.debug(f"JS file served with no-cache headers: {path}")
                
        return response

# Add GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount static files with no-cache headers
app.mount("/static", NoCacheStaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

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
        template = templates.get_template("index.html")
        
        # Start with empty notes - JavaScript will load them based on localStorage
        notes = []
        
        return template.render(request=request, notes=notes, version=VERSION)
    except Exception as e:
        logger.exception("Error in home route")
        raise