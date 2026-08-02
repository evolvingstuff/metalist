from __future__ import annotations

import logging
import secrets
import sqlite3
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import Annotated, Optional
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
import os
import sys
import threading
import time

from app.api.transactions import transactional_route
from app.api.deps import get_db
from app.config import ACTIVE_NAMESPACE
from app.config import KDF_ALGORITHM
from app.config import KDF_MAX_MEMORY_COST_KIB
from app.config import KDF_MAX_PARALLELISM
from app.config import KDF_MAX_TIME_COST
from app.config import KDF_MIN_MEMORY_COST_KIB
from app.config import KDF_MIN_PARALLELISM
from app.config import KDF_MIN_TIME_COST
from app.config import KDF_TIME_COST
from app.config import VAULT_VERSION
from app.config import VERSION
from app.db.schema import APP_SETTINGS_TABLE
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
from app.services.exception_capture import CapturedExceptionContext
from app.services.login_rate_limit import login_rate_limiter
from app.services.maintenance_mode import maintenance_service
from app.services.namespace_switcher import build_namespace_catalog
from app.services.namespace_switcher import build_login_namespace_catalog
from app.services.namespace_switcher import delete_current_namespace
from app.services.namespace_switcher import delete_namespace
from app.services.namespace_switcher import open_login_namespace
from app.services.namespace_switcher import open_or_launch_namespace
from app.services.namespace_switcher import rename_current_namespace
from app.services.namespace_switcher import save_namespace_port_profiles
from app.services.namespace_deletion_jobs import load_namespace_deletion_job
from app.services.namespace_rename_jobs import load_namespace_rename_job
from app.server_runtime import NamespaceLaunchProfile
from app.server_runtime import resolve_namespace_directory
from app.server_runtime import resolve_namespaced_database_path
from app.server_runtime import validate_namespace
from app.services.encryption import EncryptionService
from app.services.tokens import token_service
from app.services.note_store import store as note_store
from app.services.sync import clear_all_locks
from app.services.tab_state import tab_state_store
from app.services.view_cache import view_cache
from app.services import auth_cache_state
from app.services.ontology_rules_store import ensure_rules_decrypted_and_compiled
from app.services.link_titles import link_title_store
from app.services.reminders import reminder_store
from app.services.search_history import search_history_store
from app.services.sound_storage import sound_store
from app.services.hydration_state import hydration_state
from app.services.file_registry import file_registry
from app.services.file_storage import bootstrap_file_registry
from app.services.session_timeout_service import (
    MAX_SESSION_TIMEOUT_MINUTES,
    MIN_SESSION_TIMEOUT_MINUTES,
    get_session_timeout_minutes,
    save_session_timeout_minutes,
)
from app.security.encryption import (
    clear_encryption_key,
    set_encryption_required,
    set_session_dek,
)
from app.api.request_auth import clear_auth_cookie
from app.api.request_auth import get_request_auth_token
from app.api.request_auth import set_auth_cookie
from app.services.client_state_service import load_client_preferences
from app.services.client_state_service import load_client_state
from app.services.client_state_service import save_client_preferences
from app.services.client_state_service import save_command_palette_usage


router = APIRouter(prefix="/auth", tags=["auth2"])
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    message: str
    hydration_required: bool


class SessionResponse(BaseModel):
    message: str


class ClientPreferencesResponse(BaseModel):
    preferences: dict[str, str]


class CommandPaletteUsageResponse(BaseModel):
    command_palette_usage: dict[str, dict[str, object]]


class ClientStateResponse(BaseModel):
    preferences: dict[str, str]
    command_palette_usage: dict[str, dict[str, object]]


class ClientPreferencesUpdateRequest(BaseModel):
    preferences: dict[str, str]


class CommandPaletteUsageUpdateRequest(BaseModel):
    command_palette_usage: dict[str, dict[str, object]]


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


class SessionTimeoutResponse(BaseModel):
    idle_timeout_minutes: int


class SessionTimeoutUpdateRequest(BaseModel):
    idle_timeout_minutes: int = Field(
        ...,
        ge=MIN_SESSION_TIMEOUT_MINUTES,
        le=MAX_SESSION_TIMEOUT_MINUTES,
    )


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


class LoginNamespaceCatalogResponse(BaseModel):
    current_namespace: str
    namespaces: list[str]


class LoginNamespaceOpenRequest(BaseModel):
    namespace: str


class LoginNamespaceOpenResponse(BaseModel):
    namespace: str
    action: str
    url: str
    message: str


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


def _namespace_target_exists(*, namespace: str) -> bool:
    namespace_directory = resolve_namespace_directory(namespace=namespace)
    namespace_database_path = resolve_namespaced_database_path(namespace=namespace)
    if namespace_directory.exists():
        return True
    if namespace_database_path.exists():
        return True
    return False


def _read_namespace_auth_settings(*, namespace: str) -> dict[str, object] | None:
    database_path = resolve_namespaced_database_path(namespace=namespace)
    if not database_path.exists():
        return None
    if not database_path.is_file():
        raise RuntimeError(f"Namespace database path is not a file: {database_path}")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        table_row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", APP_SETTINGS_TABLE),
        ).fetchone()
        if table_row is None:
            raise RuntimeError(f"Namespace database has no {APP_SETTINGS_TABLE} table: {namespace}")
        row = connection.execute(
            f"""
            SELECT
                auth_verifier,
                auth_salt,
                auth_iterations,
                kek_iterations,
                vault_version,
                kdf_algorithm,
                kdf_memory_cost_kib,
                kdf_parallelism,
                encryption_enabled
            FROM {APP_SETTINGS_TABLE}
            WHERE id = 1
            """
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Namespace database has no app_settings row: {namespace}")
        return {
            "auth_verifier": row["auth_verifier"],
            "auth_salt": row["auth_salt"],
            "auth_iterations": row["auth_iterations"],
            "kek_iterations": row["kek_iterations"],
            "vault_version": row["vault_version"],
            "kdf_algorithm": row["kdf_algorithm"],
            "kdf_memory_cost_kib": row["kdf_memory_cost_kib"],
            "kdf_parallelism": row["kdf_parallelism"],
            "encryption_enabled": row["encryption_enabled"],
        }
    finally:
        connection.close()


def _namespace_auth_settings_have_password(*, settings: dict[str, object] | None) -> bool:
    if settings is None:
        return False
    encryption_enabled = settings["encryption_enabled"]
    if encryption_enabled not in (0, 1, False, True):
        raise RuntimeError(f"Invalid encryption_enabled value in namespace DB: {encryption_enabled!r}")
    if not bool(encryption_enabled):
        return False
    _assert_supported_namespace_vault_profile(settings=settings)
    if settings["auth_verifier"] is None:
        raise RuntimeError("Namespace encryption is enabled but auth_verifier is missing")
    if settings["auth_salt"] is None:
        raise RuntimeError("Namespace auth_verifier is set but auth_salt is NULL")
    if settings["auth_iterations"] is None:
        raise RuntimeError("Namespace auth_verifier is set but auth_iterations is NULL")
    return True


def _namespace_requires_password(*, namespace: str) -> bool:
    settings = _read_namespace_auth_settings(namespace=namespace)
    return _namespace_auth_settings_have_password(settings=settings)


def _assert_supported_namespace_vault_profile(*, settings: dict[str, object]) -> None:
    vault_version = settings["vault_version"]
    if vault_version is None:
        raise RuntimeError("Namespace encryption is enabled but vault_version is NULL")
    if vault_version != VAULT_VERSION:
        raise RuntimeError(f"Unsupported namespace vault version: {vault_version}")
    kdf_algorithm = settings["kdf_algorithm"]
    if kdf_algorithm is None:
        raise RuntimeError("Namespace encryption is enabled but kdf_algorithm is NULL")
    if kdf_algorithm != KDF_ALGORITHM:
        raise RuntimeError(f"Unsupported namespace kdf_algorithm: {kdf_algorithm}")
    auth_iterations = settings["auth_iterations"]
    if auth_iterations is None:
        raise RuntimeError("Namespace encryption is enabled but auth_iterations is NULL")
    if not isinstance(auth_iterations, int):
        raise RuntimeError(f"Namespace auth_iterations is not an integer: {auth_iterations!r}")
    if not (KDF_MIN_TIME_COST <= auth_iterations <= KDF_MAX_TIME_COST):
        raise RuntimeError(f"Namespace auth_iterations out of range: {auth_iterations}")
    kek_iterations = settings["kek_iterations"]
    if kek_iterations is None:
        raise RuntimeError("Namespace encryption is enabled but kek_iterations is NULL")
    if not isinstance(kek_iterations, int):
        raise RuntimeError(f"Namespace kek_iterations is not an integer: {kek_iterations!r}")
    if not (KDF_MIN_TIME_COST <= kek_iterations <= KDF_MAX_TIME_COST):
        raise RuntimeError(f"Namespace kek_iterations out of range: {kek_iterations}")
    memory_cost_kib = settings["kdf_memory_cost_kib"]
    if memory_cost_kib is None:
        raise RuntimeError("Namespace encryption is enabled but kdf_memory_cost_kib is NULL")
    if not isinstance(memory_cost_kib, int):
        raise RuntimeError(f"Namespace kdf_memory_cost_kib is not an integer: {memory_cost_kib!r}")
    if not (KDF_MIN_MEMORY_COST_KIB <= memory_cost_kib <= KDF_MAX_MEMORY_COST_KIB):
        raise RuntimeError(f"Namespace kdf_memory_cost_kib out of range: {memory_cost_kib}")
    parallelism = settings["kdf_parallelism"]
    if parallelism is None:
        raise RuntimeError("Namespace encryption is enabled but kdf_parallelism is NULL")
    if not isinstance(parallelism, int):
        raise RuntimeError(f"Namespace kdf_parallelism is not an integer: {parallelism!r}")
    if not (KDF_MIN_PARALLELISM <= parallelism <= KDF_MAX_PARALLELISM):
        raise RuntimeError(f"Namespace kdf_parallelism out of range: {parallelism}")


def _verify_namespace_password(*, namespace: str, password: str) -> None:
    if not isinstance(password, str):
        raise TypeError("namespace password must be a string")
    settings = _read_namespace_auth_settings(namespace=namespace)
    if not _namespace_auth_settings_have_password(settings=settings):
        return
    if password == "":
        raise HTTPException(status_code=400, detail="Namespace password is required")

    assert settings is not None
    auth_salt = settings["auth_salt"]
    auth_iterations = settings["auth_iterations"]
    memory_cost_kib = settings["kdf_memory_cost_kib"]
    parallelism = settings["kdf_parallelism"]
    auth_verifier = settings["auth_verifier"]
    if not isinstance(auth_salt, bytes):
        raise RuntimeError("Namespace auth_salt is not bytes")
    if not isinstance(auth_iterations, int):
        raise RuntimeError("Namespace auth_iterations is not an integer")
    if not isinstance(memory_cost_kib, int):
        raise RuntimeError("Namespace kdf_memory_cost_kib is not an integer")
    if not isinstance(parallelism, int):
        raise RuntimeError("Namespace kdf_parallelism is not an integer")
    if not isinstance(auth_verifier, str):
        raise RuntimeError("Namespace auth_verifier is not a string")

    candidate = EncryptionService().derive_master_key(
        password,
        auth_salt,
        auth_iterations,
        memory_cost_kib,
        parallelism,
    ).hex()
    if not secrets.compare_digest(candidate, auth_verifier):
        raise HTTPException(status_code=401, detail="Invalid password")


def _run_hydration(*, rebuild_required: bool) -> None:
    hydration_state.set_phase(
        phase="database_check",
        message="Database is up to date",
        total=1,
    )
    hydration_state.update(1)
    if not rebuild_required:
        hydration_state.finish()
        return
    session = SafeSession()
    try:
        prefetched_rows = populate_cache_from_db(session)
        session.commit()
    finally:
        session.close()

    note_store.load_from_db(None, prefetched_rows=prefetched_rows)
    sound_store.bootstrap(token="")
    auth_cache_state.mark_cache_ready()
    hydration_state.finish()


def _on_hydration_done(future: Future) -> None:
    if future.cancelled():
        hydration_state.fail("Hydration canceled")
        return
    error = future.exception()
    if error is not None:
        error_message = f"{type(error).__name__}: {error}"
        logger.error(
            "Hydration worker failed: %s",
            error_message,
            exc_info=(type(error), error, error.__traceback__),
        )
        hydration_state.fail(error_message)


def _start_hydration(*, first_load: bool, rebuild_required: bool) -> None:
    global _hydration_future
    with _hydration_lock:
        if _hydration_future is not None and not _hydration_future.done():
            return
        hydration_state.begin(
            first_load=first_load,
            message="Preparing encrypted data",
        )
        _hydration_future = _hydration_executor.submit(
            _run_hydration,
            rebuild_required=rebuild_required,
        )
        _hydration_future.add_done_callback(_on_hydration_done)


def _build_hydration_status() -> HydrationStatusResponse:
    snapshot = hydration_state.snapshot()
    if not auth_cache_state.cache_refresh_needed() and snapshot["status"] == "idle":
        snapshot["status"] = "ready"
        snapshot["phase"] = "complete"
        snapshot["message"] = "Workspace ready"
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
    link_title_store.reset()
    reminder_store.reset()
    search_history_store.reset()
    sound_store.reset()
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

        with SafeSession.allow_reads("auth:backup_restore:runtime_stores"):
            tab_state_store.bootstrap(connection=session.connection())
            link_title_store.bootstrap(connection=session.connection())
            reminder_store.bootstrap(connection=session.connection())
            search_history_store.bootstrap(connection=session.connection())

        if password_required:
            return True

        sound_store.bootstrap(token="")
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
    token = get_request_auth_token(request)
    if token is None:
        return None
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


def _require_string_field_allow_empty(payload: dict[str, object], field_name: str) -> str:
    if field_name not in payload:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a string")
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


def _require_list_field(payload: dict[str, object], field_name: str) -> list[object]:
    if field_name not in payload:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    value = payload[field_name]
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a list")
    return value


@router.post("/login", response_model=LoginResponse)
@transactional_route
def login(
    request: Request,
    response: Response,
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
    auth.run_authenticated_database_migrations(dek=dek)

    set_session_dek(dek)
    ensure_rules_decrypted_and_compiled(token="")
    tab_state_store.ensure_decrypted(token="")
    link_title_store.ensure_decrypted(token="")
    reminder_store.ensure_decrypted(token="")
    search_history_store.ensure_decrypted(token="")

    token = token_service.create_token(_client_info(request), tab_id, dek=dek)
    set_auth_cookie(request=request, response=response, token=token)
    login_rate_limiter.record_success(rate_limit_key)
    clear_all_locks()
    return LoginResponse(
        message="Login successful",
        hydration_required=True,
    )


@router.post("/logout")
@transactional_route
def logout(
    response: Response,
    token: Annotated[str, Depends(_require_auth)],
):
    token_service.revoke_token(token)
    clear_all_locks()
    clear_encryption_key()
    clear_auth_cookie(response=response)
    return {"message": "Logout successful"}


@router.post("/backup/create", response_model=BackupCreateResponse)
@transactional_route
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
@transactional_route
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
@transactional_route
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
@transactional_route
def create_passwordless_session(
    request: Request,
    response: Response,
    tab_id: Annotated[str, Depends(_require_tab_id)],
    db: Annotated[SafeSession, Depends(get_db)],
):
    auth = AuthService(db)
    if auth.has_password():
        raise HTTPException(status_code=400, detail="Password is set. Use /login instead.")

    token = token_service.create_token(_client_info(request), tab_id, dek=None)
    set_auth_cookie(request=request, response=response, token=token)
    clear_all_locks()
    return SessionResponse(message="Session established")


@router.get("/status")
def auth_status(
    db: Annotated[SafeSession, Depends(get_db)],
    token: Annotated[Optional[str], Depends(_verify_token)],
):
    auth = AuthService(db)
    settings = auth.get_settings()
    database_user_version_row = db.connection().execute("PRAGMA user_version").fetchone()
    if database_user_version_row is None:
        raise RuntimeError("Database user_version PRAGMA returned no row")
    database_user_version = database_user_version_row[0]
    if not isinstance(database_user_version, int) or database_user_version < 0:
        raise RuntimeError(f"Invalid database user_version: {database_user_version!r}")
    client_preferences: dict[str, str] = {}
    if not bool(settings and settings.encryption_enabled):
        client_preferences = load_client_preferences(token="")
    elif token is not None:
        client_preferences = load_client_preferences(token=token)
    return {
        "version": VERSION,
        "database_user_version": database_user_version,
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
        "link_title_revision": link_title_store.get_revision(),
        "client_preferences": client_preferences,
    }


@router.get("/client-state", response_model=ClientStateResponse)
def get_client_state(token: Annotated[str, Depends(_require_auth)]):
    payload = load_client_state(token=token)
    return ClientStateResponse(**payload)


@router.put("/client-state/preferences", response_model=ClientPreferencesResponse)
@transactional_route
def put_client_preferences(
    payload: ClientPreferencesUpdateRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    normalized = save_client_preferences(preferences=payload.preferences, token=token)
    return ClientPreferencesResponse(preferences=normalized)


@router.put("/client-state/command-palette-usage", response_model=CommandPaletteUsageResponse)
@transactional_route
def put_command_palette_usage(
    payload: CommandPaletteUsageUpdateRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    normalized = save_command_palette_usage(
        usage_state=payload.command_palette_usage,
        token=token,
    )
    return CommandPaletteUsageResponse(command_palette_usage=normalized)


@router.get("/login-namespaces", response_model=LoginNamespaceCatalogResponse)
def login_namespace_catalog():
    payload = build_login_namespace_catalog(
        environ=os.environ,
        current_namespace=ACTIVE_NAMESPACE,
    )
    return LoginNamespaceCatalogResponse(**payload)


@router.post("/login-namespaces/open", response_model=LoginNamespaceOpenResponse)
@transactional_route
def open_login_namespace_route(payload: LoginNamespaceOpenRequest):
    launch_capture = CapturedExceptionContext(
        RuntimeError,
        ValueError,
        TypeError,
        FileNotFoundError,
    )
    result = None
    with launch_capture:
        result = open_login_namespace(
            environ=os.environ,
            current_namespace=ACTIVE_NAMESPACE,
            namespace=payload.namespace,
        )
    if launch_capture.captured_exception is not None:
        exc = launch_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise RuntimeError("Namespace login open did not return a result")
    return LoginNamespaceOpenResponse(
        namespace=result.namespace,
        action=result.action,
        url=result.url,
        message=result.message,
    )


@router.get("/namespaces")
def namespace_catalog(token: Annotated[str, Depends(_require_auth)]):
    return build_namespace_catalog(
        environ=os.environ,
        current_namespace=ACTIVE_NAMESPACE,
    )


@router.post("/namespaces/open")
@transactional_route
def open_namespace(
    payload: dict[str, object],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    namespace = _require_string_field(body, "namespace")
    port = _require_int_field(body, "port")
    https_port = _optional_int_field(body, "https_port")
    mcp_port = _require_int_field(body, "mcp_port")
    launch_capture = CapturedExceptionContext(
        RuntimeError,
        ValueError,
        TypeError,
        FileNotFoundError,
    )
    result = None
    with launch_capture:
        result = open_or_launch_namespace(
            environ=os.environ,
            current_namespace=ACTIVE_NAMESPACE,
            namespace=namespace,
            port=port,
            https_port=https_port,
            mcp_port=mcp_port,
        )
    if launch_capture.captured_exception is not None:
        exc = launch_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise RuntimeError("Namespace launch did not return a result")
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


@router.post("/namespaces/ports")
@transactional_route
def save_namespace_ports(
    payload: dict[str, object],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    raw_profiles = _require_list_field(body, "profiles")
    requested_profiles: list[NamespaceLaunchProfile] = []
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            raise HTTPException(status_code=400, detail="profiles entries must be objects")
        namespace = _require_string_field(raw_profile, "namespace")
        port = _require_int_field(raw_profile, "port")
        https_port = _optional_int_field(raw_profile, "https_port")
        mcp_port = _require_int_field(raw_profile, "mcp_port")
        requested_profiles.append(
            NamespaceLaunchProfile(
                namespace=namespace,
                port=port,
                https_port=https_port,
                mcp_port=mcp_port,
            )
        )

    save_capture = CapturedExceptionContext(
        RuntimeError,
        ValueError,
        TypeError,
        FileNotFoundError,
    )
    result = None
    with save_capture:
        result = save_namespace_port_profiles(
            environ=os.environ,
            current_namespace=ACTIVE_NAMESPACE,
            requested_profiles=requested_profiles,
        )
    if save_capture.captured_exception is not None:
        exc = save_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise RuntimeError("Namespace ports save did not return a result")
    return {
        "profiles": [
            {
                "namespace": profile.namespace,
                "port": profile.port,
                "https_port": profile.https_port,
                "mcp_port": profile.mcp_port,
            }
            for profile in result.saved_profiles
        ],
        "message": result.message,
    }


def _delete_namespace_from_body(*, body: dict[str, object], target_namespace: str) -> dict[str, object]:
    normalized_target_namespace = validate_namespace(namespace=target_namespace)
    confirmed_namespace = _require_string_field(body, "confirmed_namespace")
    current_password = _require_string_field_allow_empty(body, "current_password")
    redirect_namespace = _require_string_field(body, "redirect_namespace")

    if _namespace_requires_password(namespace=normalized_target_namespace):
        _verify_namespace_password(
            namespace=normalized_target_namespace,
            password=current_password,
        )

    delete_capture = CapturedExceptionContext(
        RuntimeError,
        ValueError,
        TypeError,
        FileNotFoundError,
    )
    result = None
    with delete_capture:
        result = delete_namespace(
            environ=os.environ,
            current_namespace=ACTIVE_NAMESPACE,
            target_namespace=normalized_target_namespace,
            confirmed_namespace=confirmed_namespace,
            redirect_namespace=redirect_namespace,
        )
    if delete_capture.captured_exception is not None:
        exc = delete_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise RuntimeError("Namespace deletion did not return a result")

    return {
        "deleted_namespace": result.deleted_namespace,
        "redirect_url": result.redirect_url,
        "delete_job_id": result.delete_job_id,
        "active_namespace_deleted": result.active_namespace_deleted,
        "message": result.message,
    }


@router.post("/namespaces/delete/preflight")
@transactional_route
def namespace_delete_preflight(
    payload: dict[str, object],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    target_namespace = validate_namespace(
        namespace=_require_string_field(body, "target_namespace"),
    )
    target_exists = _namespace_target_exists(namespace=target_namespace)
    target_requires_password = False
    if target_exists:
        target_requires_password = _namespace_requires_password(namespace=target_namespace)
    catalog = build_namespace_catalog(
        environ=os.environ,
        current_namespace=ACTIVE_NAMESPACE,
    )
    raw_namespaces = catalog["namespaces"]
    if not isinstance(raw_namespaces, list):
        raise RuntimeError("Namespace catalog missing namespaces")
    redirect_namespaces: list[str] = []
    for raw_entry in raw_namespaces:
        if not isinstance(raw_entry, dict):
            raise RuntimeError("Namespace catalog entry must be an object")
        namespace = raw_entry["namespace"]
        if not isinstance(namespace, str) or namespace == "":
            raise RuntimeError("Namespace catalog entry missing namespace")
        if namespace != target_namespace:
            redirect_namespaces.append(namespace)
    redirect_namespaces.sort()
    recreates_default = target_namespace == ACTIVE_NAMESPACE and len(redirect_namespaces) == 0
    if recreates_default:
        redirect_namespaces.append("default")
    return {
        "target_namespace": target_namespace,
        "target_exists": target_exists,
        "target_requires_password": target_requires_password,
        "is_current_namespace": target_namespace == ACTIVE_NAMESPACE,
        "redirect_namespaces": redirect_namespaces,
        "recreates_default": recreates_default,
    }


@router.post("/namespaces/delete")
@transactional_route
def delete_named_namespace(
    payload: dict[str, object],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    target_namespace = _require_string_field(body, "target_namespace")
    return _delete_namespace_from_body(
        body=body,
        target_namespace=target_namespace,
    )


@router.post("/namespaces/delete-current")
@transactional_route
def delete_active_namespace(
    payload: dict[str, object],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    return _delete_namespace_from_body(
        body=body,
        target_namespace=ACTIVE_NAMESPACE,
    )


@router.post("/namespaces/rename-current")
@transactional_route
def rename_active_namespace(
    payload: dict[str, object],
    token: Annotated[str, Depends(_require_auth)],
):
    body = _require_body_object(payload)
    target_namespace = _require_string_field(body, "target_namespace")
    rename_capture = CapturedExceptionContext(
        RuntimeError,
        ValueError,
        TypeError,
        FileNotFoundError,
    )
    result = None
    with rename_capture:
        result = rename_current_namespace(
            environ=os.environ,
            current_namespace=ACTIVE_NAMESPACE,
            target_namespace=target_namespace,
        )
    if rename_capture.captured_exception is not None:
        exc = rename_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise RuntimeError("Namespace rename did not return a result")
    return {
        "source_namespace": result.source_namespace,
        "target_namespace": result.target_namespace,
        "redirect_url": result.redirect_url,
        "rename_job_id": result.rename_job_id,
        "message": result.message,
    }


@router.get("/namespaces/delete-jobs/{job_id}")
def namespace_delete_job_status(
    job_id: str,
):
    job_record_capture = CapturedExceptionContext(
        RuntimeError,
        TypeError,
        ValueError,
        FileNotFoundError,
    )
    job_record: dict[str, object] | None = None
    with job_record_capture:
        job_record = load_namespace_deletion_job(job_id=job_id)
    if job_record_capture.captured_exception is not None:
        exc = job_record_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job_record is None:
        raise HTTPException(status_code=404, detail=f"Namespace deletion job not found: {job_id}")
    return job_record


@router.get("/namespaces/rename-jobs/{job_id}")
def namespace_rename_job_status(job_id: str):
    job_record_capture = CapturedExceptionContext(
        RuntimeError,
        TypeError,
        ValueError,
        FileNotFoundError,
    )
    job_record: dict[str, object] | None = None
    with job_record_capture:
        job_record = load_namespace_rename_job(job_id=job_id)
    if job_record_capture.captured_exception is not None:
        exc = job_record_capture.captured_exception
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job_record is None:
        raise HTTPException(status_code=404, detail=f"Namespace rename job not found: {job_id}")
    return job_record


@router.post("/hydrate", response_model=HydrationStatusResponse)
@transactional_route
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

    _start_hydration(
        first_load=auth_cache_state.cache_refresh_needed(),
        rebuild_required=needs_hydration,
    )

    return _build_hydration_status()


@router.get("/hydration-status", response_model=HydrationStatusResponse)
def hydration_status(token: Annotated[str, Depends(_require_auth)]):
    return _build_hydration_status()


@router.post("/settings/password/create")
@transactional_route
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
@transactional_route
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
@transactional_route
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


@router.get("/settings/session-timeout", response_model=SessionTimeoutResponse)
def get_session_timeout_settings(
    token: Annotated[str, Depends(_require_auth)],
):
    del token
    return SessionTimeoutResponse(
        idle_timeout_minutes=get_session_timeout_minutes(),
    )


@router.put("/settings/session-timeout", response_model=SessionTimeoutResponse)
@transactional_route
def put_session_timeout_settings(
    payload: SessionTimeoutUpdateRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    del token
    timeout_minutes = save_session_timeout_minutes(
        timeout_minutes=payload.idle_timeout_minutes,
    )
    token_service.refresh_active_tokens_for_current_timeout()
    return SessionTimeoutResponse(
        idle_timeout_minutes=timeout_minutes,
    )


@router.get("/sessions")
def sessions(token: Annotated[str, Depends(_require_auth)]):
    return {"sessions": token_service.list_active_sessions()}
