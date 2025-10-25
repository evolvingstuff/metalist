import os
os.environ.setdefault("DISABLE_UNDO_SNAPSHOT", "1")

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pathlib import Path
from mako.lookup import TemplateLookup
from .api import dev
from .api.middleware.auth import AuthMiddleware
from .core.config import VERSION
from .db.session import begin_writer, enable_read_guard
from .db.schema import initialize_schema
from .db.settings_sql import fetch_settings, insert_default_settings
from .api.deps import get_db
from .services.content_cache import populate_cache_from_db
from .services.note_store import store as note_store
from app.services.store import hydrate_from_prefetched as v2_hydrate
from app.api.routes.notes import router as api2_router
from app.api.routes.auth import router as api2_auth_router
from app.api.routes.memory import router as api2_memory_router
from app.core.config import API_PREFIX, V1_API_PREFIX
from .core.config import CRASH_SERVER_ON_FAIL
from .models.database import SafeSession
from loguru import logger
import logging
import time
import sys
import uuid
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from fastapi.middleware.gzip import GZipMiddleware
import os

logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    backtrace=False,
    diagnose=False,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message} | {extra}"
)


class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

app = FastAPI()
logger.warning("Undo/redo snapshots disabled (set before config import)")

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
    prefetched_rows = populate_cache_from_db()
    _log_startup_step("cache population", time.perf_counter() - cache_start)

    store_start = time.perf_counter()
    note_store.load_from_db(None, prefetched_rows=prefetched_rows)
    _log_startup_step("note store hydration", time.perf_counter() - store_start)

    # Hydrate v2 view-only store from the same prefetched rows using decrypted cache
    def _get_plaintext(note_id: str, row: dict) -> str:
        from .services.content_cache import get_cached_content
        plaintext = get_cached_content(note_id)
        if plaintext is None:
            raise RuntimeError(f"V2 hydrate failed: no plaintext in cache for note {note_id}")
        return plaintext

    v2_hydrate(prefetched_rows, get_plaintext=_get_plaintext)

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

ASSET_VERSION = str(int(time.time()))

templates = TemplateLookup(
    directories=[Path(__file__).parent / "templates"],
    module_directory=str(Path(__file__).parent / "__pycache__" / "mako_modules"),
    input_encoding="utf-8"
)

# Legacy v1 routers removed; keep dev utilities mounted separately.
app.include_router(dev.router, prefix="/dev", tags=["dev"])  # unchanged
# v2 routers mounted under configured API_PREFIX
app.include_router(api2_router, prefix=API_PREFIX, tags=["api2"]) 
app.include_router(api2_auth_router, prefix=API_PREFIX)
app.include_router(api2_memory_router, prefix=API_PREFIX)

# Catch-all guard for any v1 API access (hard exit)
@app.api_route(f"{V1_API_PREFIX}/{{rest_of_path:path}}", methods=["GET","POST","PUT","DELETE","PATCH","OPTIONS","HEAD"])
async def block_v1_any(rest_of_path: str):
    os._exit(1)

@app.api_route(f"{V1_API_PREFIX}", methods=["GET","POST","PUT","DELETE","PATCH","OPTIONS","HEAD"])
async def block_v1_root():
    os._exit(1)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    handler = request.scope.get("endpoint")
    handler_name = getattr(handler, "__qualname__", "unknown")
    logger.bind(request_id=request_id).info(
        "⇒ {method} {path} handler={handler}",
        method=request.method,
        path=request.url.path,
        handler=handler_name,
    )

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.bind(request_id=request_id).exception(
            "✖ {method} {path} failed after {duration:.2f} ms",
            method=request.method,
            path=request.url.path,
            duration=duration_ms,
        )
        os._exit(1)

    duration_ms = (time.perf_counter() - start) * 1000
    size = response.headers.get("content-length", "-")
    logger.bind(request_id=request_id).info(
        "⇐ {status} {method} {path} handler={handler} duration={duration:.2f} ms size={size}",
        status=response.status_code,
        method=request.method,
        path=request.url.path,
        handler=handler_name,
        duration=duration_ms,
        size=size,
    )
    return response

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
                asset_version=ASSET_VERSION,
                needs_auth=True,
            )
        else:
            # No password required - send empty notes (JavaScript will load them)
            return template.render(
                request=request,
                notes=[],
                version=VERSION,
                asset_version=ASSET_VERSION,
                needs_auth=False,
            )
    except Exception as e:
        logger.exception("Error in home route")
        raise


@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    """Maintenance mode page shown during bulk operations."""
    try:
        template = templates.get_template("maintenance.html")
        return template.render(request=request, version=VERSION, asset_version=ASSET_VERSION)
    except Exception as e:
        # FAIL FAST AND LOUD - NO SILENT FAILURES
        logger.error(f"🚨 FATAL: Failed to render maintenance template: {e}")
        logger.error(f"🚨 Cannot display maintenance page!")
        logger.error(f"🚨 CRASHING IMMEDIATELY")
        raise RuntimeError(f"Maintenance page failed: Could not render template: {e}") from e
