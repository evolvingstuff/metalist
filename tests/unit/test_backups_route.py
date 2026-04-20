from __future__ import annotations

from pathlib import Path

import pytest

import app.api.routes.backups as backups_route
from app.services.backup_service import BackupFileInfo


def test_serialize_settings_response_returns_local_and_folder_fields_only() -> None:
    response = backups_route._serialize_settings_response(
        {
            "local_enabled": True,
            "folder_enabled": False,
            "folder_path": "",
            "retention_count": 30,
        }
    )

    payload = response.model_dump()
    assert payload == {
        "local_enabled": True,
        "folder_enabled": False,
        "folder_path": "",
        "retention_count": 30,
    }


def test_put_backup_settings_normalizes_and_passes_folder_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    expected_folder = tmp_path / "backup-folder"

    def _capture_update_settings(
        *,
        token: str,
        local_enabled: bool,
        folder_enabled: bool,
        folder_path: str,
        retention_count: int,
    ) -> dict[str, object]:
        captured["token"] = token
        captured["local_enabled"] = local_enabled
        captured["folder_enabled"] = folder_enabled
        captured["folder_path"] = folder_path
        captured["retention_count"] = retention_count
        return {
            "local_enabled": local_enabled,
            "folder_enabled": folder_enabled,
            "folder_path": folder_path,
            "retention_count": retention_count,
        }

    monkeypatch.setattr(backups_route, "update_backup_settings", _capture_update_settings)

    payload = backups_route.BackupSettingsUpdateRequest(
        local_enabled=True,
        folder_enabled=True,
        folder_path=f"  {expected_folder}  ",
        retention_count=10,
    )

    response = backups_route.put_backup_settings(payload=payload, token="token")

    assert captured["folder_enabled"] is True
    assert captured["folder_path"] == str(expected_folder)
    assert expected_folder.is_dir() is True
    assert response.folder_enabled is True
    assert response.folder_path == str(expected_folder)


def test_run_backup_writes_to_configured_folder_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cla.metalist.db"
    folder_directory = tmp_path / "synced" / "MetaList Backups"
    created_backup = BackupFileInfo(
        filename="cla-20260419-090000-000000.metalist-backup.tar.gz",
        created_at="2026-04-19T09:00:00+00:00",
        size_bytes=128,
    )

    monkeypatch.setattr(backups_route, "resolve_live_database_path", lambda: database_path)
    monkeypatch.setattr(
        backups_route,
        "load_backup_settings",
        lambda *, token: {
            "local_enabled": False,
            "folder_enabled": True,
            "folder_path": str(folder_directory),
            "retention_count": 30,
        },
    )
    monkeypatch.setattr(
        backups_route,
        "create_timestamped_backup_for_paths",
        lambda _database_path, _backup_directory: created_backup,
    )
    monkeypatch.setattr(
        backups_route,
        "list_backups_in_directory",
        lambda _backup_directory, *, database_path=None: [created_backup],
    )

    response = backups_route.run_backup(token="token")

    assert folder_directory.is_dir() is True
    assert len(response.results) == 1
    assert response.results[0].destination == "folder"
    assert response.results[0].success is True
    assert response.results[0].created_filename == created_backup.filename
    assert "Folder backup completed" in response.results[0].message


def test_run_backup_rejects_when_no_destinations_are_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(backups_route, "resolve_live_database_path", lambda: tmp_path / "cla.metalist.db")
    monkeypatch.setattr(
        backups_route,
        "load_backup_settings",
        lambda *, token: {
            "local_enabled": False,
            "folder_enabled": False,
            "folder_path": "",
            "retention_count": 30,
        },
    )

    with pytest.raises(backups_route.HTTPException) as excinfo:
        backups_route.run_backup(token="token")

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Enable local or folder backups before running a backup"


def test_pick_backup_folder_returns_selected_folder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    folder_path = tmp_path / "MetaList Backups"
    monkeypatch.setattr(
        backups_route,
        "_pick_backup_folder_path",
        lambda: str(folder_path),
    )

    response = backups_route.pick_backup_folder(token="token")

    assert response.selected is True
    assert response.folder_path == str(folder_path)


def test_pick_backup_folder_returns_not_selected_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backups_route,
        "_pick_backup_folder_path",
        lambda: None,
    )

    response = backups_route.pick_backup_folder(token="token")

    assert response.selected is False
    assert response.folder_path == ""
