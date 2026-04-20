from __future__ import annotations

from pathlib import Path

import pytest

import app.api.routes.backups as backups_route
from app.services.backup_service import BackupFileInfo


def test_run_backup_keeps_local_success_when_google_drive_upload_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cla.metalist.db"
    backup_directory = tmp_path / "backups"
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
            "local_enabled": True,
            "google_drive_enabled": True,
            "retention_count": 30,
        },
    )
    monkeypatch.setattr(
        backups_route,
        "resolve_backup_directory_for_database",
        lambda _database_path: backup_directory,
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
    monkeypatch.setattr(
        backups_route,
        "upload_google_drive_backup",
        lambda *, token, namespace, archive_path: (_ for _ in ()).throw(RuntimeError("drive failed")),
    )

    response = backups_route.run_backup(token="token")

    assert len(response.results) == 2
    assert response.results[0].destination == "local"
    assert response.results[0].success is True
    assert response.results[0].created_filename == created_backup.filename
    assert response.results[1].destination == "google_drive"
    assert response.results[1].success is False
    assert response.results[1].created_filename == created_backup.filename
    assert response.results[1].message == "drive failed"
