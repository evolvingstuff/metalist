from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pathlib import Path
from mako.lookup import TemplateLookup
from .api import notes, dev, auth, memory
from .api.middleware import AuthMiddleware
from .core.config import VERSION
from .db.engine import begin_writer, enable_read_guard
from .db.schema import initialize_schema
from .db.settings_sql import fetch_settings, insert_default_settings
from .api.dependencies import get_db
from .services.content_cache import populate_cache_from_db
from .services.note_store import store as note_store
from .core.config import CRASH_SERVER_ON_FAIL
from .models.database import SafeSession
import logging
import time
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from fastapi.middleware.gzip import GZipMiddleware
import mimetypes

logger = logging.getLogger(__name__)

app = FastAPI()

# CRASH SERVER ON VALIDATION ERRORS - FAIL FAST AND LOUD
@app.exception_handler(RequestValidationError)
async def crash_on_validation_error(request: Request, exc: RequestValidationError):
    if CRASH_SERVER_ON_FAIL:
        logger.error(f"🚨 FATAL: Validation error on {request.method} {request.url}")
        logger.error(f"🚨 Validation errors: {exc.errors()}")
        logger.error(f"🚨 CRASHING SERVER IMMEDIATELY")
        raise RuntimeError(f"VALIDATION FAILED - CRASHING: {request.method} {request.url}: {exc.errors()}") from exc
    else:
        # Normal behavior - return 422
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

_startup_timing_enabled = True


def _log_startup_step(step: str, elapsed: float) -> None:
    if not _startup_timing_enabled:
        return
    message = f"[startup] {step} took {elapsed:.2f}s"
    print(message)
    logger.info(message)


try:
    overall_start = time.perf_counter()

    schema_start = time.perf_counter()
    with begin_writer() as connection:
        initialize_schema(connection.raw_connection)
        settings = fetch_settings(connection)
        if not settings:
            insert_default_settings(connection)
    _log_startup_step("schema + settings bootstrap", time.perf_counter() - schema_start)
except Exception as e:
    # FAIL FAST AND LOUD - NO SILENT FAILURES
    logger.error(f"🚨 FATAL: Failed to initialize app settings: {e}")
    logger.error(f"🚨 Cannot start application with broken settings!")
    logger.error(f"🚨 CRASHING IMMEDIATELY")
    raise RuntimeError(f"Application startup failed: Could not initialize app settings: {e}") from e

# Populate content cache on startup
try:
    cache_start = time.perf_counter()
    populate_cache_from_db()
    _log_startup_step("cache population", time.perf_counter() - cache_start)

    store_start = time.perf_counter()
    note_store.load_from_db(None)
    _log_startup_step("note store hydration", time.perf_counter() - store_start)

    guard_start = time.perf_counter()
    enable_read_guard()
    _log_startup_step("read guard enable", time.perf_counter() - guard_start)

    _log_startup_step("total startup", time.perf_counter() - overall_start)
except Exception as e:
    # FAIL FAST AND LOUD - NO SILENT FAILURES
    logger.error(f"🚨 FATAL: Failed to populate content cache on startup: {e}")
    logger.error(f"🚨 Cannot start application with broken cache system!")
    logger.error(f"🚨 CRASHING IMMEDIATELY")
    raise RuntimeError(f"Application startup failed: Could not populate content cache: {e}") from e

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

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Mount static files with no-cache headers
app.mount("/static", NoCacheStaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

templates = TemplateLookup(
    directories=[Path(__file__).parent / "templates"],
    module_directory=str(Path(__file__).parent / "__pycache__" / "mako_modules"),
    input_encoding="utf-8"
)

app.include_router(auth.router)
app.include_router(notes.router, prefix="/api/notes", tags=["notes"])
app.include_router(dev.router, prefix="/dev", tags=["dev"])
app.include_router(memory.router, prefix="/api")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            logger.error(f"Request failed: {request.method} {request.url} - Status: {response.status_code}")
        return response
    except Exception as e:
        # FAIL FAST AND LOUD - NO SILENT FAILURES
        logger.error(f"🚨 FATAL: Unhandled error in request: {request.method} {request.url}")
        logger.error(f"🚨 Request processing failed catastrophically!")
        logger.error(f"🚨 CRASHING IMMEDIATELY")
        raise RuntimeError(f"Request processing failed: {request.method} {request.url}: {e}") from e

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: SafeSession = Depends(get_db)):
    try:
        from .services.auth import AuthService
        
        template = templates.get_template("index.html")
        
        # Check if authentication is required
        auth = AuthService(db)
        needs_auth = auth.has_password()
        
        # If authentication is required, don't send any notes data
        if needs_auth:
            return template.render(
                request=request, 
                version=VERSION,
                needs_auth=True
            )
        else:
            # No password required - send empty notes (JavaScript will load them)
            return template.render(
                request=request, 
                notes=[], 
                version=VERSION,
                needs_auth=False
            )
    except Exception as e:
        logger.exception("Error in home route")
        raise


@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    """Maintenance mode page shown during bulk operations."""
    try:
        template = templates.get_template("maintenance.html")
        return template.render(request=request)
    except Exception as e:
        # FAIL FAST AND LOUD - NO SILENT FAILURES
        logger.error(f"🚨 FATAL: Failed to render maintenance template: {e}")
        logger.error(f"🚨 Cannot display maintenance page!")
        logger.error(f"🚨 CRASHING IMMEDIATELY")
        raise RuntimeError(f"Maintenance page failed: Could not render template: {e}") from e
