from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import ACTIVE_NAMESPACE
from app.db.session import begin_writer
from app.db.settings_sql import insert_default_settings
from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
from app.services.backup_settings_service import load_backup_settings


def test_load_backup_settings_backfills_folder_fields_for_legacy_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    set_encryption_required(False)
    try:
        with begin_writer() as connection:
            insert_default_settings(connection)
            connection.execute(
                """
                UPDATE app_settings
                SET backup_settings_json = ?,
                    backup_settings_encryption_nonce = NULL,
                    backup_settings_encryption_tag = NULL
                WHERE id = 1
                """,
                (
                    json.dumps(
                        {
                            "retention_count": 30,
                            "local_enabled": True,
                            "google_drive_enabled": False,
                            "google_drive": {
                                "status": "disconnected",
                                "account_email": "",
                                "access_token": "",
                                "refresh_token": "",
                                "token_expiry": "",
                                "root_folder_id": "",
                                "root_folder_name": "",
                            },
                        }
                    ),
                ),
            )

        settings = load_backup_settings(token="")

        assert settings["folder_path"] == ""
        assert settings["selected_namespaces"] == [ACTIVE_NAMESPACE]
        assert settings["retention_count"] == 30
        assert "local_enabled" not in settings
        assert "folder_enabled" not in settings
        assert "google_drive_enabled" not in settings
        assert "google_drive" not in settings
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()
