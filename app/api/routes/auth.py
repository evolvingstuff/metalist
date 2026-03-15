from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Annotated, Optional
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
import os
import sys
import threading
import time

from app.api.deps import get_db
from app.config import ACTIVE_NAMESPACE, KDF_TIME_COST
from app.db.settings_sql import fetch_settings
from app.models.database import SafeSession
from app.services.auth_service import AuthService
from app.services.backup_service import (
    BackupFileInfo,
    create_timestamped_backup,
    delete_oldest_backups,
    list_backups,
    restore_backup,
)
from app.services.content_cache import clear_cache, populate_cache_from_db
from app.services.login_rate_limit import login_rate_limiter
from app.services.maintenance_mode import maintenance_service
from app.services.namespace_switcher import build_namespace_catalog
from app.services.namespace_switcher import delete_current_namespace
from app.services.namespace_switcher import open_or_launch_namespace
from app.services.namespace_deletion_jobs import load_namespace_deletion_job
from app.services.tokens import token_service
from app.services.note_store import store as note_store
from app.services.sync import clear_all_locks
from app.services.tab_state import tab_state_store
from app.services.view_cache import view_cache
from app.services import auth_cache_state
from app.services.ontology_rules_store import ensure_rules_decrypted_and_compiled
from app.services.hydration_state import hydration_state
from app.services.file_registry import file_registry
from app.services.file_storage import bootstrap_file_registry
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


class BackupDeleteOldestRequest(BaseModel):
    count: int = Field(..., gt=0)


class BackupDeleteOldestResponse(BaseModel):
    deleted_backups: list[BackupFileResponse]
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
_server_restart_lock = Lock()
_server_restart_scheduled = False


def _reexec_server_process() -> None:
    argv = [sys.executable, *sys.argv]
    os.execv(sys.executable, argv)


def _schedule_server_restart_after_restore(delay_seconds: float) -> None:
    if not isinstance(delay_seconds, float):
        raise TypeError(f"delay_seconds must be a float, got {type(delay_seconds)}")
    if delay_seconds < 0.0:
        raise ValueError(f"delay_seconds must be >= 0.0, got {delay_seconds}")

    global _server_restart_scheduled
    with _server_restart_lock:
        if _server_restart_scheduled:
            return
        _server_restart_scheduled = True

    def _restart_worker() -> None:
        time.sleep(delay_seconds)
        _reexec_server_process()

    restart_thread = threading.Thread(
        target=_restart_worker,
        name="auth-backup-restore-restart",
        daemon=True,
    )
    restart_thread.start()


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
    file_registry.reset()
    bootstrap_file_registry()

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


def _login_rate_limit_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for is not None:
        forwarded_for = forwarded_for.strip()
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return f"ip:{first_hop}"
    if request.client and request.client.host:
        return f"ip:{request.client.host}"
    user_agent = request.headers.get("user-agent", "Unknown")
    return f"ua:{user_agent[:128]}"


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


def _require_body_object(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    return payload


def _require_string_field(payload: dict[str, object], field_name: str) -> str:
    if field_name not in payload:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a string")
    if value.strip() == "":
        raise HTTPException(status_code=400, detail=f"{field_name} must not be empty")
    return value


def _require_int_field(payload: dict[str, object], field_name: str) -> int:
    if field_name not in payload:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, int):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer")
    return value


def _optional_int_field(payload: dict[str, object], field_name: str) -> int | None:
    if field_name not in payload:
        return None
    value = payload[field_name]
    if value is None:
        return None
    if not isinstance(value, int):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer or null")
    return value


@router.post("/login", response_model=LoginResponse)
def login(
    request: Request,
    payload: LoginRequest,
    tab_id: Annotated[str, Depends(_require_tab_id)],
    db: Annotated[SafeSession, Depends(get_db)],
):
    rate_limit_key = _login_rate_limit_key(request)
    allowed, retry_after_seconds = login_rate_limiter.check_allowed(rate_limit_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {retry_after_seconds} seconds.",
        )

    auth = AuthService(db)
    if not auth.has_password():
        raise HTTPException(status_code=400, detail="No password is set. Please set a password first.")
    if not auth.verify_password(payload.password):
        login_rate_limiter.record_failure(rate_limit_key)
        raise HTTPException(status_code=401, detail="Invalid password")

    dek = auth.unwrap_dek_for_password(payload.password)

    set_session_dek(dek)
    ensure_rules_decrypted_and_compiled(token="")

    needs_hydration = auth_cache_state.cache_refresh_needed()
    if not note_store.loaded:
        needs_hydration = True

    token = token_service.create_token(_client_info(request), tab_id, dek=dek)
    login_rate_limiter.record_success(rate_limit_key)
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


@router.post("/backup/delete-oldest", response_model=BackupDeleteOldestResponse)
def delete_oldest_backup_files(
    payload: BackupDeleteOldestRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    deleted_backup_files = delete_oldest_backups(payload.count)
    return BackupDeleteOldestResponse(
        deleted_backups=[
            _serialize_backup_file(backup_file) for backup_file in deleted_backup_files
        ],
        message=f"Deleted {len(deleted_backup_files)} backup(s)",
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

    _schedule_server_restart_after_restore(delay_seconds=0.5)

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
        "vault_version": settings.vault_version if settings else None,
        "kdf_algorithm": settings.kdf_algorithm if settings else None,
        "kdf_memory_cost_kib": settings.kdf_memory_cost_kib if settings else None,
        "kdf_parallelism": settings.kdf_parallelism if settings else None,
        "cache_ready": not auth_cache_state.cache_refresh_needed(),
        "namespace": ACTIVE_NAMESPACE,
    }


@router.get("/namespaces")
def namespace_catalog(token: Annotated[str, Depends(_require_auth)]):
    return build_namespace_catalog(
        environ=os.environ,
        current_namespace=ACTIVE_NAMESPACE,
    )


@router.post("/namespaces/open")
def open_namespace(
    payload: dict[str, object],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    namespace = _require_string_field(body, "namespace")
    port = _require_int_field(body, "port")
    https_port = _optional_int_field(body, "https_port")
    mcp_port = _require_int_field(body, "mcp_port")
    try:
        result = open_or_launch_namespace(
            environ=os.environ,
            current_namespace=ACTIVE_NAMESPACE,
            namespace=namespace,
            port=port,
            https_port=https_port,
            mcp_port=mcp_port,
        )
    except (RuntimeError, ValueError, TypeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "namespace": result.namespace,
        "action": result.action,
        "url": result.url,
        "saved_profile": {
            "namespace": result.saved_profile.namespace,
            "port": result.saved_profile.port,
            "https_port": result.saved_profile.https_port,
            "mcp_port": result.saved_profile.mcp_port,
        },
        "saved_for_next_launch": result.saved_for_next_launch,
        "message": result.message,
    }


@router.post("/namespaces/delete-current")
def delete_active_namespace(
    payload: dict[str, object],
    db: Annotated[SafeSession, Depends(get_db)],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    confirmation_text = _require_string_field(body, "confirmation_text")

    auth = AuthService(db)
    if auth.has_password():
        current_password = _require_string_field(body, "current_password")
        if not auth.verify_password(current_password):
            raise HTTPException(status_code=401, detail="Invalid password")

    try:
        result = delete_current_namespace(
            environ=os.environ,
            current_namespace=ACTIVE_NAMESPACE,
            confirmation_text=confirmation_text,
        )
    except (RuntimeError, ValueError, TypeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "deleted_namespace": result.deleted_namespace,
        "redirect_url": result.redirect_url,
        "delete_job_id": result.delete_job_id,
        "message": result.message,
    }


@router.get("/namespaces/delete-jobs/{job_id}")
def namespace_delete_job_status(
    job_id: str,
):
    try:
        job_record = load_namespace_deletion_job(job_id=job_id)
    except (RuntimeError, TypeError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job_record is None:
        raise HTTPException(status_code=404, detail=f"Namespace deletion job not found: {job_id}")
    return job_record


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
    success, message = auth.set_password(payload.password, KDF_TIME_COST)
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
    if payload.iterations is not None:
        time_cost = payload.iterations
    else:
        time_cost = KDF_TIME_COST
    success, message = auth.change_password(
        payload.current_password,
        payload.new_password,
        time_cost,
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
    clear_encryption_key()
    return {"message": message}


@router.get("/sessions")
def sessions(token: Annotated[str, Depends(_require_auth)]):
    return {"sessions": token_service.list_active_sessions()}
