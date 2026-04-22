from __future__ import annotations

from pathlib import Path

import pytest

import app.api.routes.backups as backups_route
from app.services.backup_service import BackupFileInfo


def test_serialize_settings_response_returns_folder_and_namespace_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backups_route, "_list_available_namespaces", lambda: ["default", "work"])

    response = backups_route._serialize_settings_response(
        {
            "folder_path": "/tmp/backups",
            "selected_namespaces": ["work"],
            "retention_count": 30,
        }
    )

    payload = response.model_dump()
    assert payload == {
        "folder_path": "/tmp/backups",
        "selected_namespaces": ["work"],
        "available_namespaces": ["default", "work"],
        "retention_count": 30,
    }


def test_put_backup_settings_normalizes_and_passes_folder_path_and_namespaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    expected_folder = tmp_path / "backup-folder"
    default_database = tmp_path / "default.metalist.db"
    work_database = tmp_path / "work.metalist.db"
    default_database.touch()
    work_database.touch()

    def _capture_update_settings(
        *,
        token: str,
        folder_path: str,
        selected_namespaces: list[str],
        retention_count: int,
    ) -> dict[str, object]:
        captured["token"] = token
        captured["folder_path"] = folder_path
        captured["selected_namespaces"] = selected_namespaces
        captured["retention_count"] = retention_count
        return {
            "folder_path": folder_path,
            "selected_namespaces": selected_namespaces,
            "retention_count": retention_count,
        }

    monkeypatch.setattr(backups_route, "update_backup_settings", _capture_update_settings)
    monkeypatch.setattr(
        backups_route,
        "resolve_namespaced_database_path",
        lambda *, namespace: {
            "default": default_database,
            "work": work_database,
        }[namespace],
    )

    payload = backups_route.BackupSettingsUpdateRequest(
        folder_path=f"  {expected_folder}  ",
        selected_namespaces=["work", "default"],
        retention_count=10,
    )

    response = backups_route.put_backup_settings(payload=payload, token="token")

    assert captured["folder_path"] == str(expected_folder)
    assert captured["selected_namespaces"] == ["default", "work"]
    assert expected_folder.is_dir() is True
    assert response.folder_path == str(expected_folder)
    assert response.selected_namespaces == ["default", "work"]


def test_run_backup_writes_each_selected_namespace_to_configured_folder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    folder_directory = tmp_path / "synced" / "MetaList Backups"
    default_database = tmp_path / "default.metalist.db"
    work_database = tmp_path / "work.metalist.db"
    default_database.touch()
    work_database.touch()
    default_backup = BackupFileInfo(
        filename="default-20260419-090000-000000.metalist-backup.tar.gz",
        created_at="2026-04-19T09:00:00+00:00",
        size_bytes=128,
    )
    work_backup = BackupFileInfo(
        filename="work-20260419-090001-000000.metalist-backup.tar.gz",
        created_at="2026-04-19T09:00:01+00:00",
        size_bytes=256,
    )

    monkeypatch.setattr(
        backups_route,
        "load_backup_settings",
        lambda *, token: {
            "folder_path": str(folder_directory),
            "selected_namespaces": ["default", "work"],
            "retention_count": 30,
        },
    )
    monkeypatch.setattr(
        backups_route,
        "resolve_namespaced_database_path",
        lambda *, namespace: {
            "default": default_database,
            "work": work_database,
        }[namespace],
    )
    monkeypatch.setattr(
        backups_route,
        "create_timestamped_backup_for_paths",
        lambda database_path, _backup_directory: default_backup if database_path == default_database else work_backup,
    )
    monkeypatch.setattr(
        backups_route,
        "list_backups_in_directory",
        lambda _backup_directory, *, database_path=None: (
            [default_backup] if database_path == default_database else [work_backup]
        ),
    )

    response = backups_route.run_backup(token="token")

    assert folder_directory.is_dir() is True
    assert len(response.results) == 2
    assert response.results[0].namespace == "default"
    assert response.results[0].destination == "folder"
    assert response.results[0].success is True
    assert response.results[0].created_filename == default_backup.filename
    assert response.results[0].size_bytes == default_backup.size_bytes
    assert response.results[1].namespace == "work"
    assert response.results[1].created_filename == work_backup.filename
    assert response.results[1].size_bytes == work_backup.size_bytes


def test_run_backup_rejects_when_no_namespaces_are_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backups_route,
        "load_backup_settings",
        lambda *, token: {
            "folder_path": "/tmp/backups",
            "selected_namespaces": [],
            "retention_count": 30,
        },
    )

    with pytest.raises(backups_route.HTTPException) as excinfo:
        backups_route.run_backup(token="token")

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Select at least one namespace to back up"


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
