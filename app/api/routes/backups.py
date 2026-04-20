from __future__ import annotations

import shutil
import subprocess
import sys
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Annotated
from pathlib import Path

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
from app.server_runtime import resolve_namespaced_database_path
from app.server_runtime import resolve_namespaces_directory
from app.server_runtime import validate_namespace
from app.services.backup_settings_service import (
    load_backup_settings,
    update_backup_settings,
)
from app.services.tokens import token_service
from app.services.maintenance_mode import maintenance_service
from app.api.routes.auth import _reset_runtime_state_after_restore, _schedule_server_restart_after_restore


router = APIRouter(prefix="/backup", tags=["backup2"])
_FOLDER_PATH_REQUIRED_MESSAGE = "Folder backups require an absolute folder path."


class BackupSettingsResponse(BaseModel):
    local_enabled: bool
    folder_enabled: bool
    folder_path: str
    retention_count: int


class BackupSettingsUpdateRequest(BaseModel):
    local_enabled: bool
    folder_enabled: bool
    folder_path: str
    retention_count: int = Field(..., gt=0)


class BackupFolderPickResponse(BaseModel):
    selected: bool
    folder_path: str


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
    folder_path = settings["folder_path"]
    if not isinstance(folder_path, str):
        raise RuntimeError("backup settings folder_path must be a string")
    return BackupSettingsResponse(
        local_enabled=bool(settings["local_enabled"]),
        folder_enabled=bool(settings["folder_enabled"]),
        folder_path=folder_path,
        retention_count=int(settings["retention_count"]),
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


def _normalize_folder_backup_path(*, folder_path: str) -> Path:
    if not isinstance(folder_path, str):
        raise TypeError("folder_path must be a string")
    stripped_folder_path = folder_path.strip()
    if stripped_folder_path == "":
        raise HTTPException(status_code=400, detail=_FOLDER_PATH_REQUIRED_MESSAGE)
    normalized_path = Path(stripped_folder_path).expanduser()
    if not normalized_path.is_absolute():
        raise HTTPException(status_code=400, detail=_FOLDER_PATH_REQUIRED_MESSAGE)
    return normalized_path


def _prepare_folder_backup_directory_for_settings(*, folder_enabled: bool, folder_path: str) -> str:
    if not isinstance(folder_enabled, bool):
        raise TypeError("folder_enabled must be a bool")
    if not isinstance(folder_path, str):
        raise TypeError("folder_path must be a string")
    normalized_folder_path = folder_path
    if folder_path != "":
        normalized_folder_path = str(_normalize_folder_backup_path(folder_path=folder_path))
    if not folder_enabled:
        return normalized_folder_path
    folder_directory = _normalize_folder_backup_path(folder_path=folder_path)
    folder_directory.mkdir(parents=True, exist_ok=True)
    if not folder_directory.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Folder backup path is not a directory: {folder_directory}",
        )
    return str(folder_directory)


def _run_native_folder_picker_command(*, command: list[str]) -> str | None:
    if not isinstance(command, list) or len(command) == 0:
        raise TypeError("command must be a non-empty list")
    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode == 0:
        if stdout == "":
            return None
        return stdout
    if completed.returncode == 1 and (stderr == "" or "User canceled" in stderr or "(-128)" in stderr):
        return None
    raise RuntimeError(
        f"Native folder picker failed: exit={completed.returncode} stdout={stdout!r} stderr={stderr!r}"
    )


def _pick_backup_folder_path() -> str | None:
    if sys.platform == "darwin":
        osascript_path = shutil.which("osascript")
        if osascript_path is None:
            raise RuntimeError("`osascript` is required for the macOS folder picker")
        return _run_native_folder_picker_command(
            command=[
                osascript_path,
                "-e",
                'POSIX path of (choose folder with prompt "Choose a backup folder for MetaList")',
            ]
        )

    if sys.platform.startswith("linux"):
        zenity_path = shutil.which("zenity")
        if zenity_path is not None:
            return _run_native_folder_picker_command(
                command=[
                    zenity_path,
                    "--file-selection",
                    "--directory",
                    "--title=Choose a backup folder for MetaList",
                ]
            )
        kdialog_path = shutil.which("kdialog")
        if kdialog_path is not None:
            return _run_native_folder_picker_command(
                command=[
                    kdialog_path,
                    "--getexistingdirectory",
                    "",
                    "--title",
                    "Choose a backup folder for MetaList",
                ]
            )
        raise RuntimeError("No supported Linux folder picker was found (`zenity` or `kdialog`)")

    if sys.platform == "win32":
        powershell_path = shutil.which("powershell")
        if powershell_path is None:
            powershell_path = shutil.which("pwsh")
        if powershell_path is None:
            raise RuntimeError("PowerShell is required for the Windows folder picker")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$dialog.Description = 'Choose a backup folder for MetaList'; "
            "$dialog.ShowNewFolderButton = $true; "
            "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
            "Write-Output $dialog.SelectedPath; exit 0 }; "
            "exit 1"
        )
        return _run_native_folder_picker_command(
            command=[powershell_path, "-NoProfile", "-Command", script]
        )

    raise RuntimeError(f"Native folder picker is not supported on platform: {sys.platform}")


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


def _folder_backup_id(*, namespace: str, filename: str) -> str:
    return f"folder::{namespace}::{filename}"


def _parse_folder_backup_id(backup_id: str) -> tuple[str, str]:
    if not isinstance(backup_id, str) or backup_id == "":
        raise HTTPException(status_code=400, detail="backup_id must be a non-empty string")
    parts = backup_id.split("::", 2)
    if len(parts) != 3 or parts[0] != "folder":
        raise HTTPException(status_code=400, detail="Invalid folder backup_id")
    namespace = validate_namespace(namespace=parts[1])
    filename = parts[2]
    if filename == "":
        raise HTTPException(status_code=400, detail="Invalid folder backup_id filename")
    return namespace, filename


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
    normalized_folder_path = _prepare_folder_backup_directory_for_settings(
        folder_enabled=payload.folder_enabled,
        folder_path=payload.folder_path,
    )
    settings = update_backup_settings(
        token=token,
        local_enabled=payload.local_enabled,
        folder_enabled=payload.folder_enabled,
        folder_path=normalized_folder_path,
        retention_count=payload.retention_count,
    )
    return _serialize_settings_response(settings)


@router.post("/folder/pick", response_model=BackupFolderPickResponse)
@transactional_route
def pick_backup_folder(token: Annotated[str, Depends(_require_auth)]):
    del token
    selected_folder_path = _pick_backup_folder_path()
    if selected_folder_path is None:
        return BackupFolderPickResponse(
            selected=False,
            folder_path="",
        )
    normalized_folder_path = str(_normalize_folder_backup_path(folder_path=selected_folder_path))
    return BackupFolderPickResponse(
        selected=True,
        folder_path=normalized_folder_path,
    )


@router.get("/list", response_model=BackupListResponse)
def list_backups(token: Annotated[str, Depends(_require_auth)]):
    backups = _list_local_backups_across_namespaces()
    settings = load_backup_settings(token=token)
    folder_path = settings["folder_path"]
    if not isinstance(folder_path, str):
        raise RuntimeError("backup settings folder_path must be a string")
    if folder_path != "":
        folder_directory = _normalize_folder_backup_path(folder_path=folder_path)
        folder_backups = list_backups_in_directory(folder_directory, database_path=None)
        for backup in folder_backups:
            backup_namespace = parse_backup_namespace_from_filename(backup.filename)
            backups.append(
                _serialize_backup_entry(
                    backup_id=_folder_backup_id(namespace=backup_namespace, filename=backup.filename),
                    source="folder",
                    filename=backup.filename,
                    namespace=backup_namespace,
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
    settings = load_backup_settings(token=token)
    local_enabled = settings["local_enabled"]
    folder_enabled = settings["folder_enabled"]
    folder_path = settings["folder_path"]
    retention_count = settings["retention_count"]
    if not isinstance(local_enabled, bool) or not isinstance(folder_enabled, bool):
        raise RuntimeError("backup settings destination flags must be bools")
    if not isinstance(folder_path, str):
        raise RuntimeError("backup settings folder_path must be a string")
    if not isinstance(retention_count, int) or retention_count <= 0:
        raise RuntimeError("backup settings retention_count must be a positive integer")
    if not local_enabled and not folder_enabled:
        raise HTTPException(status_code=400, detail="Enable local or folder backups before running a backup")

    backup_info = None
    archive_path = None
    results: list[BackupRunDestinationResponse] = []
    any_success = False
    folder_directory = None
    if folder_enabled:
        folder_directory = _normalize_folder_backup_path(folder_path=folder_path)
        folder_directory.mkdir(parents=True, exist_ok=True)
        if not folder_directory.is_dir():
            raise RuntimeError(f"Folder backup path is not a directory: {folder_directory}")

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

    if folder_enabled:
        assert folder_directory is not None
        if archive_path is None:
            backup_info = create_timestamped_backup_for_paths(database_path, folder_directory)
            archive_path = folder_directory / backup_info.filename
        else:
            assert backup_info is not None
            folder_archive_path = folder_directory / backup_info.filename
            if archive_path != folder_archive_path:
                shutil.copy2(archive_path, folder_archive_path)
            archive_path = folder_archive_path
        current_folder_backups = list_backups_in_directory(folder_directory, database_path=database_path)
        folder_delete_count = len(current_folder_backups) - retention_count
        deleted_folder_count = 0
        if folder_delete_count > 0:
            deleted_folder_count = len(
                delete_oldest_backups_in_directory(
                    folder_directory,
                    folder_delete_count,
                    database_path=database_path,
                )
            )
        remaining_folder_backups = list_backups_in_directory(folder_directory, database_path=database_path)
        any_success = True
        assert backup_info is not None
        results.append(
            BackupRunDestinationResponse(
                destination="folder",
                success=True,
                created_filename=backup_info.filename,
                deleted_count=deleted_folder_count,
                remaining_count=len(remaining_folder_backups),
                message=f"Folder backup completed: {folder_directory}",
            )
        )

    if not any_success:
        raise HTTPException(status_code=500, detail="Backup failed for all enabled destinations")
    return BackupRunResponse(results=results)


@router.post("/restore", response_model=BackupRestoreResponse)
@transactional_route
def restore_backup(
    payload: BackupRestoreRequest,
    token: Annotated[str, Depends(_require_auth)],
):
    if payload.source not in {"local", "folder"}:
        raise HTTPException(status_code=400, detail="source must be local or folder")
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
    elif payload.source == "folder":
        folder_namespace, folder_filename = _parse_folder_backup_id(payload.backup_id)
        if folder_namespace != backup_namespace:
            raise HTTPException(status_code=400, detail="folder backup namespace does not match payload")
        if folder_filename != payload.backup_filename:
            raise HTTPException(status_code=400, detail="folder backup filename does not match payload")
        settings = load_backup_settings(token=token)
        folder_path = settings["folder_path"]
        if not isinstance(folder_path, str):
            raise RuntimeError("backup settings folder_path must be a string")
        folder_directory = _normalize_folder_backup_path(folder_path=folder_path)
        backup_path = folder_directory / folder_filename
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail=f"Backup not found: {folder_filename}")
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
