from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Annotated
from pathlib import Path
from tempfile import TemporaryDirectory

from app.api.transactions import transactional_route
from app.config import ACTIVE_NAMESPACE
from app.services.backup_service import (
    create_timestamped_backup_for_paths,
    delete_oldest_backups_in_directory,
    list_backups_in_directory,
    parse_backup_namespace_from_filename,
    resolve_backup_directory_for_database,
    resolve_live_database_path,
    restore_backup_to_paths,
)
from app.server_runtime import resolve_namespaced_database_path, resolve_namespaces_directory, validate_namespace
from app.services.google_drive_service import (
    delete_google_drive_backup,
    disconnect_google_drive,
    download_google_drive_backup,
    get_google_drive_connect_request_status,
    get_google_drive_connection_status,
    is_google_drive_oauth_available,
    list_google_drive_backups,
    list_google_drive_backups_for_namespace,
    start_google_drive_connect_request,
    upload_google_drive_backup,
    validate_google_drive_connection,
)
from app.services.backup_settings_service import (
    load_backup_settings,
    update_backup_settings,
)
from app.services.tokens import token_service
from app.services.maintenance_mode import maintenance_service
from app.services.exception_capture import CapturedExceptionContext
from app.api.routes.auth import _reset_runtime_state_after_restore, _schedule_server_restart_after_restore


router = APIRouter(prefix="/backup", tags=["backup2"])


class BackupSettingsResponse(BaseModel):
    local_enabled: bool
    google_drive_enabled: bool
    retention_count: int
    google_drive_status: str
    google_drive_account_email: str
    google_drive_root_folder_name: str
    google_drive_connected: bool
    google_drive_available: bool


class BackupSettingsUpdateRequest(BaseModel):
    local_enabled: bool
    google_drive_enabled: bool
    retention_count: int = Field(..., gt=0)


class GoogleDriveConnectStartResponse(BaseModel):
    request_id: str
    authorization_url: str


class GoogleDriveConnectStatusResponse(BaseModel):
    request_id: str
    status: str
    message: str


class GoogleDriveConnectionResponse(BaseModel):
    status: str
    account_email: str
    root_folder_name: str
    connected: bool


class BackupListEntryResponse(BaseModel):
    backup_id: str
    source: str
    filename: str
    namespace: str
    created_at: str
    size_bytes: int


class BackupListResponse(BaseModel):
    backups: list[BackupListEntryResponse]


class BackupRunDestinationResponse(BaseModel):
    destination: str
    success: bool
    created_filename: str
    deleted_count: int
    remaining_count: int
    message: str


class BackupRunResponse(BaseModel):
    results: list[BackupRunDestinationResponse]


class BackupRestoreRequest(BaseModel):
    backup_id: str
    source: str
    backup_filename: str
    backup_namespace: str
    target_namespace: str


class BackupRestoreResponse(BaseModel):
    backup_id: str
    source: str
    backup_filename: str
    backup_namespace: str
    target_namespace: str
    active_namespace_restarted: bool
    open_namespace_suggested: bool
    message: str


def _require_tab_id(
    x_metalist_tab_id: Annotated[str, Header(alias="X-Metalist-Tab-Id")],
) -> str:
    return x_metalist_tab_id


def _verify_token(
    request: Request,
    tab_id: Annotated[str, Depends(_require_tab_id)],
) -> str | None:
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


def _require_auth(token: Annotated[str | None, Depends(_verify_token)]) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return token


def _serialize_settings_response(settings: dict[str, object]) -> BackupSettingsResponse:
    google_drive = settings["google_drive"]
    if not isinstance(google_drive, dict):
        raise RuntimeError("backup settings google_drive must be an object")
    status = google_drive["status"]
    account_email = google_drive["account_email"]
    root_folder_name = google_drive["root_folder_name"]
    if (
        not isinstance(status, str)
        or not isinstance(account_email, str)
        or not isinstance(root_folder_name, str)
    ):
        raise RuntimeError("backup settings google_drive fields must be strings")
    return BackupSettingsResponse(
        local_enabled=bool(settings["local_enabled"]),
        google_drive_enabled=bool(settings["google_drive_enabled"]),
        retention_count=int(settings["retention_count"]),
        google_drive_status=status,
        google_drive_account_email=account_email,
        google_drive_root_folder_name=root_folder_name,
        google_drive_connected=status == "connected",
        google_drive_available=is_google_drive_oauth_available(),
    )


def _serialize_backup_entry(
    *,
    backup_id: str,
    source: str,
    filename: str,
    namespace: str,
    created_at: str,
    size_bytes: int,
) -> BackupListEntryResponse:
    return BackupListEntryResponse(
        backup_id=backup_id,
        source=source,
        filename=filename,
        namespace=namespace,
        created_at=created_at,
        size_bytes=size_bytes,
    )


def _local_backup_id(*, namespace: str, filename: str) -> str:
    return f"local::{namespace}::{filename}"


def _parse_local_backup_id(backup_id: str) -> tuple[str, str]:
    if not isinstance(backup_id, str) or backup_id == "":
        raise HTTPException(status_code=400, detail="backup_id must be a non-empty string")
    parts = backup_id.split("::", 2)
    if len(parts) != 3 or parts[0] != "local":
        raise HTTPException(status_code=400, detail="Invalid local backup_id")
    namespace = validate_namespace(namespace=parts[1])
    filename = parts[2]
    if filename == "":
        raise HTTPException(status_code=400, detail="Invalid local backup_id filename")
    return namespace, filename


def _derive_active_namespace_from_database_path(database_path: Path) -> str:
    filename = database_path.name
    if filename.endswith(".metalist.db"):
        return validate_namespace(namespace=filename[: -len(".metalist.db")])
    return validate_namespace(namespace=database_path.stem)


def _list_local_backups_across_namespaces() -> list[BackupListEntryResponse]:
    namespaces_directory = resolve_namespaces_directory()
    if not namespaces_directory.exists():
        return []
    if not namespaces_directory.is_dir():
        raise RuntimeError(f"namespaces directory is not a directory: {namespaces_directory}")

    backups: list[BackupListEntryResponse] = []
    for child in sorted(namespaces_directory.iterdir()):
        if not child.is_dir():
            continue
        namespace_capture = child.name
        normalized_namespace = validate_namespace(namespace=namespace_capture)
        database_path = resolve_namespaced_database_path(namespace=normalized_namespace)
        backup_directory = resolve_backup_directory_for_database(database_path)
        local_backups = list_backups_in_directory(backup_directory, database_path=database_path)
        for backup in local_backups:
            backups.append(
                _serialize_backup_entry(
                    backup_id=_local_backup_id(namespace=normalized_namespace, filename=backup.filename),
                    source="local",
                    filename=backup.filename,
                    namespace=normalized_namespace,
                    created_at=backup.created_at,
                    size_bytes=backup.size_bytes,
                )
            )

    backups.sort(key=lambda entry: entry.created_at, reverse=True)
    return backups


@router.get("/settings", response_model=BackupSettingsResponse)
def get_backup_settings(token: Annotated[str, Depends(_require_auth)]):
    settings = load_backup_settings(token=token)
    return _serialize_settings_response(settings)


@router.put("/settings", response_model=BackupSettingsResponse)
@transactional_route
def put_backup_settings(
    payload: BackupSettingsUpdateRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    settings = update_backup_settings(
        token=token,
        local_enabled=payload.local_enabled,
        google_drive_enabled=payload.google_drive_enabled,
        retention_count=payload.retention_count,
    )
    return _serialize_settings_response(settings)


@router.post("/google-drive/connect/start", response_model=GoogleDriveConnectStartResponse)
@transactional_route
def start_google_drive_connect(
    token: Annotated[str, Depends(_require_auth)],
):
    connect_request = start_google_drive_connect_request(
        token=token,
    )
    return GoogleDriveConnectStartResponse(
        request_id=connect_request["request_id"],
        authorization_url=connect_request["authorization_url"],
    )


@router.get("/google-drive/connect/callback", response_class=HTMLResponse)
def finish_google_drive_connect():
    return HTMLResponse(
        content=(
            "<!doctype html><html><body>"
            "<p>This callback endpoint is no longer used for Google Drive connect. "
            "Return to MetaList and start the connection again.</p>"
            "</body></html>"
        )
    )


@router.get("/google-drive/connect/status", response_model=GoogleDriveConnectStatusResponse)
def get_google_drive_connect_status(
    request_id: str,
    token: Annotated[str, Depends(_require_auth)],
):
    del token
    status = get_google_drive_connect_request_status(request_id=request_id)
    return GoogleDriveConnectStatusResponse(
        request_id=status.request_id,
        status=status.status,
        message=status.message,
    )


@router.post("/google-drive/validate", response_model=GoogleDriveConnectionResponse)
@transactional_route
def post_google_drive_validate(token: Annotated[str, Depends(_require_auth)]):
    status = validate_google_drive_connection(token=token)
    return GoogleDriveConnectionResponse(**status)


@router.post("/google-drive/disconnect", response_model=GoogleDriveConnectionResponse)
@transactional_route
def post_google_drive_disconnect(token: Annotated[str, Depends(_require_auth)]):
    disconnect_google_drive(token=token)
    status = get_google_drive_connection_status(token=token)
    return GoogleDriveConnectionResponse(**status)


@router.get("/list", response_model=BackupListResponse)
def list_backups(token: Annotated[str, Depends(_require_auth)]):
    backups = _list_local_backups_across_namespaces()
    settings = load_backup_settings(token=token)
    google_drive = settings["google_drive"]
    if not isinstance(google_drive, dict):
        raise RuntimeError("backup settings google_drive must be an object")
    google_drive_status = google_drive["status"]
    if not isinstance(google_drive_status, str):
        raise RuntimeError("backup settings google_drive status must be a string")
    if google_drive_status == "connected":
        for backup in list_google_drive_backups(token=token):
            backups.append(
                _serialize_backup_entry(
                    backup_id=backup.file_id,
                    source="google_drive",
                    filename=backup.filename,
                    namespace=backup.namespace,
                    created_at=backup.created_at,
                    size_bytes=backup.size_bytes,
                )
            )
    backups.sort(key=lambda entry: entry.created_at, reverse=True)
    return BackupListResponse(backups=backups)


@router.post("/run", response_model=BackupRunResponse)
@transactional_route
def run_backup(token: Annotated[str, Depends(_require_auth)]):
    database_path = resolve_live_database_path()
    namespace = _derive_active_namespace_from_database_path(database_path)
    settings = load_backup_settings(token=token)
    local_enabled = settings["local_enabled"]
    google_drive_enabled = settings["google_drive_enabled"]
    retention_count = settings["retention_count"]
    if not isinstance(local_enabled, bool) or not isinstance(google_drive_enabled, bool):
        raise RuntimeError("backup settings destination flags must be bools")
    if not isinstance(retention_count, int) or retention_count <= 0:
        raise RuntimeError("backup settings retention_count must be a positive integer")
    if not local_enabled and not google_drive_enabled:
        raise HTTPException(status_code=400, detail="Enable local, Google Drive, or both before running a backup")

    backup_info = None
    archive_path = None
    cleanup_temp_archive = False
    results: list[BackupRunDestinationResponse] = []
    any_success = False

    if local_enabled:
        backup_directory = resolve_backup_directory_for_database(database_path)
        backup_info = create_timestamped_backup_for_paths(database_path, backup_directory)
        archive_path = backup_directory / backup_info.filename
        current_local_backups = list_backups_in_directory(backup_directory, database_path=database_path)
        local_delete_count = len(current_local_backups) - retention_count
        deleted_local_count = 0
        if local_delete_count > 0:
            deleted_local_count = len(
                delete_oldest_backups_in_directory(
                    backup_directory,
                    local_delete_count,
                    database_path=database_path,
                )
            )
        remaining_local_backups = list_backups_in_directory(backup_directory, database_path=database_path)
        any_success = True
        results.append(
            BackupRunDestinationResponse(
                destination="local",
                success=True,
                created_filename=backup_info.filename,
                deleted_count=deleted_local_count,
                remaining_count=len(remaining_local_backups),
                message="Local backup completed",
            )
        )

    temp_directory_manager = None
    if google_drive_enabled and archive_path is None:
        temp_directory_manager = TemporaryDirectory(prefix="metalist-drive-backup-")
        temp_directory_path = Path(temp_directory_manager.name)
        backup_info = create_timestamped_backup_for_paths(database_path, temp_directory_path)
        archive_path = temp_directory_path / backup_info.filename
        cleanup_temp_archive = True

    if google_drive_enabled:
        google_drive_capture = CapturedExceptionContext(RuntimeError, ValueError, FileNotFoundError)
        with google_drive_capture:
            assert backup_info is not None
            assert archive_path is not None
            upload_google_drive_backup(
                token=token,
                namespace=namespace,
                archive_path=str(archive_path),
            )
            drive_backups = list_google_drive_backups_for_namespace(token=token, namespace=namespace)
            drive_delete_count = len(drive_backups) - retention_count
            deleted_drive_count = 0
            if drive_delete_count > 0:
                drive_backups_oldest_first = list(reversed(drive_backups))
                drive_backups_to_delete = drive_backups_oldest_first[:drive_delete_count]
                for backup in drive_backups_to_delete:
                    delete_google_drive_backup(token=token, file_id=backup.file_id)
                deleted_drive_count = len(drive_backups_to_delete)
                drive_backups = list_google_drive_backups_for_namespace(token=token, namespace=namespace)
            any_success = True
            results.append(
                BackupRunDestinationResponse(
                    destination="google_drive",
                    success=True,
                    created_filename=backup_info.filename,
                    deleted_count=deleted_drive_count,
                    remaining_count=len(drive_backups),
                    message="Google Drive backup completed",
                )
            )
        if google_drive_capture.captured_exception is not None:
            failed_created_filename = ""
            if backup_info is not None:
                failed_created_filename = backup_info.filename
            results.append(
                BackupRunDestinationResponse(
                    destination="google_drive",
                    success=False,
                    created_filename=failed_created_filename,
                    deleted_count=0,
                    remaining_count=0,
                    message=str(google_drive_capture.captured_exception),
                )
            )

    if temp_directory_manager is not None:
        temp_directory_manager.cleanup()
    if cleanup_temp_archive and archive_path is None:
        raise RuntimeError("expected archive_path for Google Drive backup")

    if not any_success:
        raise HTTPException(status_code=500, detail="Backup failed for all enabled destinations")
    return BackupRunResponse(results=results)


@router.post("/restore", response_model=BackupRestoreResponse)
@transactional_route
def restore_backup(
    payload: BackupRestoreRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    if payload.source not in {"local", "google_drive"}:
        raise HTTPException(status_code=400, detail="source must be local or google_drive")
    backup_namespace = validate_namespace(namespace=payload.backup_namespace)
    target_namespace = validate_namespace(namespace=payload.target_namespace)
    if target_namespace != backup_namespace:
        raise HTTPException(
            status_code=400,
            detail="For now, target_namespace must match backup_namespace",
        )

    target_database_path = resolve_namespaced_database_path(namespace=target_namespace)
    active_namespace_restarted = False
    open_namespace_suggested = target_namespace != ACTIVE_NAMESPACE

    if payload.source == "local":
        local_namespace, local_filename = _parse_local_backup_id(payload.backup_id)
        if local_namespace != backup_namespace:
            raise HTTPException(status_code=400, detail="local backup namespace does not match payload")
        if local_filename != payload.backup_filename:
            raise HTTPException(status_code=400, detail="local backup filename does not match payload")
        backup_directory = resolve_backup_directory_for_database(
            resolve_namespaced_database_path(namespace=local_namespace)
        )
        backup_path = backup_directory / local_filename
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail=f"Backup not found: {local_filename}")
        if target_namespace == ACTIVE_NAMESPACE:
            maintenance_service.enter_maintenance("Restoring backup")
            try:
                restore_backup_to_paths(backup_path, target_database_path)
                _reset_runtime_state_after_restore()
            finally:
                maintenance_service.exit_maintenance()
            _schedule_server_restart_after_restore(delay_seconds=0.5)
            active_namespace_restarted = True
            open_namespace_suggested = False
        else:
            restore_backup_to_paths(backup_path, target_database_path)
    else:
        if payload.backup_id == "":
            raise HTTPException(status_code=400, detail="backup_id must not be empty")
        with TemporaryDirectory(prefix="metalist-drive-restore-") as temp_directory:
            temp_backup_path = Path(temp_directory) / payload.backup_filename
            download_google_drive_backup(
                token=token,
                file_id=payload.backup_id,
                target_path=str(temp_backup_path),
            )
            if parse_backup_namespace_from_filename(payload.backup_filename) != backup_namespace:
                raise HTTPException(status_code=400, detail="backup filename namespace does not match payload")
            if target_namespace == ACTIVE_NAMESPACE:
                maintenance_service.enter_maintenance("Restoring backup")
                try:
                    restore_backup_to_paths(temp_backup_path, target_database_path)
                    _reset_runtime_state_after_restore()
                finally:
                    maintenance_service.exit_maintenance()
                _schedule_server_restart_after_restore(delay_seconds=0.5)
                active_namespace_restarted = True
                open_namespace_suggested = False
            else:
                restore_backup_to_paths(temp_backup_path, target_database_path)

    return BackupRestoreResponse(
        backup_id=payload.backup_id,
        source=payload.source,
        backup_filename=payload.backup_filename,
        backup_namespace=backup_namespace,
        target_namespace=target_namespace,
        active_namespace_restarted=active_namespace_restarted,
        open_namespace_suggested=open_namespace_suggested,
        message="Backup restored successfully",
    )
