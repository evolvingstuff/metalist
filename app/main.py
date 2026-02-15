from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pathlib import Path
from typing import Annotated
from app.presentation.templates import get_templates
from .api import dev
from .api.middleware.auth import AuthMiddleware
from app.config import VERSION
from .db.session import begin_writer, enable_read_guard
from .db.schema import initialize_schema
from .db.notes_sql import clear_encryption_metadata_for_empty_notes
from .db.settings_sql import fetch_settings, insert_default_settings
from .api.deps import get_db
from .services.content_cache import populate_cache_from_db
from .services.auth import AuthService
from .services.note_store import store as note_store
from app.services import auth_cache_state
from app.services.integrity import assert_linked_list_integrity
from app.services.tag_ontology import OntologyParseError
from app.services.ontology_rules_store import bootstrap_ontology_rules_store
from app.services.runtime_hardening import apply_runtime_hardening
from app.security.encryption import set_encryption_required
from app.api.routes.notes import router as api2_router
from app.api.routes.auth import router as api2_auth_router
from app.api.routes.memory import router as api2_memory_router
from app.api.routes.ontology import router as api2_ontology_router
from app.api.routes.test import router as api2_test_router
from app.config import API_PREFIX, TEST_MODE, V1_API_PREFIX
from app.config import CRASH_SERVER_ON_FAIL
from .models.database import SafeSession
from loguru import logger
import logging
import time
import sys
import uuid
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from fastapi.middleware.gzip import GZipMiddleware
import os
from datetime import datetime, timezone

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


@app.exception_handler(OntologyParseError)
async def handle_ontology_parse_error(request: Request, exc: OntologyParseError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

_startup_timing_enabled = True


def _log_startup_step(step: str, elapsed: float) -> None:
    if not _startup_timing_enabled:
        return
    message = f"[startup] {step} took {elapsed:.2f}s"
    logger.info(message)


overall_start = time.perf_counter()

hardening_start = time.perf_counter()
apply_runtime_hardening()
_log_startup_step("runtime hardening checks", time.perf_counter() - hardening_start)

schema_start = time.perf_counter()
with begin_writer() as connection:
    initialize_schema(connection.raw_connection)
    settings = fetch_settings(connection)
    if not settings:
        insert_default_settings(connection)
    bootstrap_ontology_rules_store(connection=connection)
_log_startup_step("schema + settings bootstrap", time.perf_counter() - schema_start)

integrity_start = time.perf_counter()
integrity_session = SafeSession()
try:
    assert_linked_list_integrity(integrity_session, "startup")
    integrity_session.commit()
finally:
    integrity_session.close()
_log_startup_step("linked list integrity check", time.perf_counter() - integrity_start)

startup_has_password = False
encryption_enabled = False
if settings:
    encryption_enabled = bool(settings["encryption_enabled"])
    startup_has_password = encryption_enabled
set_encryption_required(encryption_enabled)

if startup_has_password:
    logger.info("[startup] password set; skipping cache + store hydration until login")
    auth_cache_state.reset_cache_state()
    guard_start = time.perf_counter()
    enable_read_guard()
    _log_startup_step("read guard enable", time.perf_counter() - guard_start)
    _log_startup_step("total startup", time.perf_counter() - overall_start)
else:
    # Populate content cache on startup
    repair_start = time.perf_counter()
    with begin_writer() as connection:
        repaired = clear_encryption_metadata_for_empty_notes(
            connection,
            updated_at=datetime.now(timezone.utc),
        )
    if repaired:
        logger.info(
            f"[startup] repaired {repaired} empty encrypted notes (cleared nonce/tag)"
        )
    _log_startup_step(
        "empty-note encryption metadata repair",
        time.perf_counter() - repair_start,
    )

    cache_start = time.perf_counter()
    cache_session = SafeSession()
    try:
        prefetched_rows = populate_cache_from_db(cache_session)
        cache_session.commit()
    finally:
        cache_session.close()
    _log_startup_step("cache population", time.perf_counter() - cache_start)

    store_start = time.perf_counter()
    note_store.load_from_db(None, prefetched_rows=prefetched_rows)
    _log_startup_step("note store hydration", time.perf_counter() - store_start)
    auth_cache_state.mark_cache_ready()

    guard_start = time.perf_counter()
    enable_read_guard()
    _log_startup_step("read guard enable", time.perf_counter() - guard_start)

    _log_startup_step("total startup", time.perf_counter() - overall_start)

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

templates = get_templates()

# Legacy v1 routers removed; keep dev utilities mounted separately.
app.include_router(dev.router, prefix="/dev", tags=["dev"])  # unchanged
# v2 routers mounted under configured API_PREFIX
app.include_router(api2_router, prefix=API_PREFIX, tags=["api2"]) 
app.include_router(api2_auth_router, prefix=API_PREFIX)
app.include_router(api2_memory_router, prefix=API_PREFIX)
app.include_router(api2_ontology_router, prefix=API_PREFIX)
if TEST_MODE:
    app.include_router(api2_test_router, prefix=API_PREFIX, tags=["api2-test"])

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

    path = request.url.path
    is_noisy_poll = request.method == "GET" and path == f"{API_PREFIX}/auth/status"
    is_noisy_lock = request.method == "POST" and path in {
        f"{API_PREFIX}/notes/acquire-lock",
        f"{API_PREFIX}/notes/release-lock",
    }
    if not (is_noisy_poll or is_noisy_lock):
        logger.bind(request_id=request_id).info(
            "⇒ {method} {path} handler={handler}",
            method=request.method,
            path=path,
            handler=handler_name,
        )

    start = time.perf_counter()
    response = await call_next(request)

    duration_ms = (time.perf_counter() - start) * 1000
    size = response.headers.get("content-length", "-")
    if not (is_noisy_poll or is_noisy_lock):
        logger.bind(request_id=request_id).info(
            "⇐ {status} {method} {path} handler={handler} duration={duration:.2f} ms size={size}",
            status=response.status_code,
            method=request.method,
            path=path,
            handler=handler_name,
            duration=duration_ms,
            size=size,
        )
    return response

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Annotated[SafeSession, Depends(get_db)]):
    template = templates.get_template("index.html")

    auth = AuthService(db)
    needs_auth = auth.has_password()

    if needs_auth:
        return template.render(
            request=request,
            version=VERSION,
            asset_version=ASSET_VERSION,
            needs_auth=True,
        )
    return template.render(
        request=request,
        notes=[],
        version=VERSION,
        asset_version=ASSET_VERSION,
        needs_auth=False,
    )


@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    """Maintenance mode page shown during bulk operations."""
    template = templates.get_template("maintenance.html")
    return template.render(request=request, version=VERSION, asset_version=ASSET_VERSION)


@app.get("/locked", response_class=HTMLResponse)
async def locked_page(request: Request, db: Annotated[SafeSession, Depends(get_db)]):
    """Render a dedicated locked screen when a session is invalidated."""
    template = templates.get_template("locked.html")
    auth = AuthService(db)
    has_password = auth.has_password()
    return template.render(
        request=request,
        version=VERSION,
        asset_version=ASSET_VERSION,
        has_password=has_password,
    )
