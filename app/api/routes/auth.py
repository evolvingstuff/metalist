from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from typing import Annotated, Optional
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from app.api.deps import get_db
from app.db.settings_sql import fetch_settings
from app.models.database import SafeSession
from app.services.auth_service import AuthService
from app.services.backup_service import (
    BackupFileInfo,
    create_timestamped_backup,
    list_backups,
    restore_backup,
)
from app.services.content_cache import clear_cache, populate_cache_from_db
from app.services.maintenance_mode import maintenance_service
from app.services.tokens import token_service
from app.services.note_store import store as note_store
from app.services.sync import clear_all_locks
from app.services.tab_state import tab_state_store
from app.services.view_cache import view_cache
from app.services import auth_cache_state
from app.services.ontology_rules_store import ensure_rules_decrypted_and_compiled
from app.services.hydration_state import hydration_state
from app.security.encryption import (
    clear_encryption_key,
    set_encryption_required,
    set_session_dek,
)


router = APIRouter(prefix="/auth", tags=["auth2"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    message: str
    hydration_required: bool


class SessionResponse(BaseModel):
    token: str
    message: str


class HydrationStatusResponse(BaseModel):
    status: str
    phase: str
    message: str
    processed: int
    total: int
    first_load: bool
    error: str
    overall_percent: int


class PasswordCreateRequest(BaseModel):
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    iterations: Optional[int] = None


class PasswordRemoveRequest(BaseModel):
    current_password: str


class BackupFileResponse(BaseModel):
    filename: str
    created_at: str
    size_bytes: int


class BackupListResponse(BaseModel):
    backups: list[BackupFileResponse]


class BackupCreateResponse(BaseModel):
    backup: BackupFileResponse
    message: str


class BackupRestoreRequest(BaseModel):
    filename: str


class BackupRestoreResponse(BaseModel):
    backup: BackupFileResponse
    message: str
    reauthentication_required: bool
    password_required: bool


_hydration_executor = ThreadPoolExecutor(max_workers=1)
_hydration_lock = Lock()
_hydration_future: Future | None = None


def _run_hydration() -> None:
    session = SafeSession()
    try:
        prefetched_rows = populate_cache_from_db(session)
        session.commit()
    finally:
        session.close()

    note_store.load_from_db(None, prefetched_rows=prefetched_rows)
    auth_cache_state.mark_cache_ready()
    hydration_state.finish()


def _on_hydration_done(future: Future) -> None:
    if future.cancelled():
        hydration_state.fail("Hydration canceled")
        return
    error = future.exception()
    if error is not None:
        hydration_state.fail(str(error))


def _start_hydration(first_load: bool) -> None:
    global _hydration_future
    with _hydration_lock:
        if _hydration_future is not None and not _hydration_future.done():
            return
        hydration_state.begin(
            first_load=first_load,
            message="Preparing encrypted data",
        )
        _hydration_future = _hydration_executor.submit(_run_hydration)
        _hydration_future.add_done_callback(_on_hydration_done)


def _build_hydration_status() -> HydrationStatusResponse:
    snapshot = hydration_state.snapshot()
    if not auth_cache_state.cache_refresh_needed() and snapshot["status"] == "idle":
        snapshot["status"] = "ready"
        snapshot["phase"] = "complete"
        snapshot["message"] = "Hydration complete"
        snapshot["overall_percent"] = 100
    return HydrationStatusResponse(**snapshot)


def _serialize_backup_file(backup_file: BackupFileInfo) -> BackupFileResponse:
    return BackupFileResponse(
        filename=backup_file.filename,
        created_at=backup_file.created_at,
        size_bytes=backup_file.size_bytes,
    )


def _reset_runtime_state_after_restore() -> bool:
    view_cache.clear()
    tab_state_store.reset()
    clear_all_locks()
    token_service.revoke_all_tokens()
    clear_encryption_key()
    clear_cache()
    note_store.reset()
    auth_cache_state.reset_cache_state()

    session = SafeSession()
    try:
        with SafeSession.allow_reads("auth:backup_restore:settings"):
            settings = fetch_settings(session.connection())
        if settings is None:
            raise RuntimeError("App settings missing after backup restore")

        password_required = bool(settings["encryption_enabled"])
        set_encryption_required(password_required)

        if password_required:
            return True

        prefetched_rows = populate_cache_from_db(session)
        note_store.load_from_db(None, prefetched_rows=prefetched_rows)
        auth_cache_state.mark_cache_ready()
        return False
    finally:
        session.close()


def _client_info(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "Unknown")
    if request.client:
        client_host = request.client.host
    else:
        client_host = "Unknown"
    return f"{user_agent[:100]} - {client_host}"


def _require_tab_id(
    x_metalist_tab_id: Annotated[str, Header(alias="X-Metalist-Tab-Id")],
) -> str:
    return x_metalist_tab_id


def _verify_token(
    request: Request,
    tab_id: Annotated[str, Depends(_require_tab_id)],
) -> Optional[str]:
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1]
    if token_service.verify_token_for_tab(token, tab_id):
        return token
    return None


def _require_auth(token: Annotated[Optional[str], Depends(_verify_token)]) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return token


@router.post("/login", response_model=LoginResponse)
def login(
    request: Request,
    payload: LoginRequest,
    tab_id: Annotated[str, Depends(_require_tab_id)],
    db: Annotated[SafeSession, Depends(get_db)],
):
    auth = AuthService(db)
    if not auth.has_password():
        raise HTTPException(status_code=400, detail="No password is set. Please set a password first.")
    if not auth.verify_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    dek = auth.unwrap_dek_for_password(payload.password)

    set_session_dek(dek)
    ensure_rules_decrypted_and_compiled(token="")

    needs_hydration = auth_cache_state.cache_refresh_needed()
    if not note_store.loaded:
        needs_hydration = True

    token = token_service.create_token(_client_info(request), tab_id, dek=dek)
    clear_all_locks()
    return LoginResponse(
        token=token,
        message="Login successful",
        hydration_required=needs_hydration,
    )


@router.post("/logout")
def logout(token: Annotated[str, Depends(_require_auth)]):
    token_service.revoke_token(token)
    clear_all_locks()
    clear_encryption_key()
    return {"message": "Logout successful"}


@router.post("/backup/create", response_model=BackupCreateResponse)
def create_backup(token: Annotated[str, Depends(_require_auth)]):
    backup_file = create_timestamped_backup()
    return BackupCreateResponse(
        backup=_serialize_backup_file(backup_file),
        message="Backup created successfully",
    )


@router.get("/backup/list", response_model=BackupListResponse)
def list_available_backups(token: Annotated[str, Depends(_require_auth)]):
    backup_files = list_backups()
    return BackupListResponse(
        backups=[_serialize_backup_file(backup_file) for backup_file in backup_files]
    )


@router.post("/backup/restore", response_model=BackupRestoreResponse)
def restore_from_backup(
    payload: BackupRestoreRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    maintenance_service.enter_maintenance("Restoring backup")
    try:
        backup_file = restore_backup(payload.filename)
        password_required = _reset_runtime_state_after_restore()
    finally:
        maintenance_service.exit_maintenance()

    return BackupRestoreResponse(
        backup=_serialize_backup_file(backup_file),
        message="Backup restored successfully",
        reauthentication_required=True,
        password_required=password_required,
    )


@router.post("/session", response_model=SessionResponse)
def create_passwordless_session(
    request: Request,
    tab_id: Annotated[str, Depends(_require_tab_id)],
    db: Annotated[SafeSession, Depends(get_db)],
):
    auth = AuthService(db)
    if auth.has_password():
        raise HTTPException(status_code=400, detail="Password is set. Use /login instead.")

    token = token_service.create_token(_client_info(request), tab_id, dek=None)
    clear_all_locks()
    return SessionResponse(token=token, message="Session established")


@router.get("/status")
def auth_status(
    db: Annotated[SafeSession, Depends(get_db)],
    token: Annotated[Optional[str], Depends(_verify_token)],
):
    auth = AuthService(db)
    settings = auth.get_settings()
    return {
        "authenticated": token is not None,
        "has_password": auth.has_password(),
        "encryption_enabled": settings.encryption_enabled if settings else False,
        "encryption_algorithm": settings.encryption_algorithm if settings else None,
        "cache_ready": not auth_cache_state.cache_refresh_needed(),
    }


@router.post("/hydrate", response_model=HydrationStatusResponse)
def hydrate_cache(
    db: Annotated[SafeSession, Depends(get_db)],
    token: Annotated[str, Depends(_require_auth)],
):
    auth = AuthService(db)
    if not auth.has_password():
        raise HTTPException(status_code=400, detail="Hydration is only required when a password is set.")

    needs_hydration = auth_cache_state.cache_refresh_needed()
    if not note_store.loaded:
        needs_hydration = True

    if needs_hydration:
        _start_hydration(first_load=auth_cache_state.cache_refresh_needed())

    return _build_hydration_status()


@router.get("/hydration-status", response_model=HydrationStatusResponse)
def hydration_status(token: Annotated[str, Depends(_require_auth)]):
    return _build_hydration_status()


@router.post("/settings/password/create")
def create_password(
    payload: PasswordCreateRequest,
    db: Annotated[SafeSession, Depends(get_db)],
):
    auth = AuthService(db)
    if auth.has_password():
        raise HTTPException(status_code=400, detail="Password already exists. Use change endpoint instead.")
    success, message = auth.set_password(payload.password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    token_service.revoke_all_tokens()
    clear_all_locks()
    return {"message": message}


@router.put("/settings/password/change")
def change_password(
    payload: PasswordChangeRequest,
    db: Annotated[SafeSession, Depends(get_db)],
    token: Annotated[str, Depends(_require_auth)],
):
    auth = AuthService(db)
    success, message = auth.change_password(
        payload.current_password,
        payload.new_password,
        payload.iterations,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    token_service.revoke_all_tokens()
    clear_all_locks()
    return {"message": message}


@router.delete("/settings/password/remove")
def remove_password(
    payload: PasswordRemoveRequest,
    db: Annotated[SafeSession, Depends(get_db)],
    token: Annotated[str, Depends(_require_auth)],
):
    auth = AuthService(db)
    success, message = auth.remove_password(payload.current_password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    token_service.revoke_all_tokens()
    clear_all_locks()
    return {"message": message}


@router.get("/sessions")
def sessions(token: Annotated[str, Depends(_require_auth)]):
    return {"sessions": token_service.list_active_sessions()}
