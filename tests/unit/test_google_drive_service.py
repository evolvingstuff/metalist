from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.db.session import begin_writer
from app.db.settings_sql import insert_default_settings
from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
import app.services.google_drive_service as google_drive_service
from app.services.backup_settings_service import load_backup_settings
from app.services.google_drive_service import (
    get_google_drive_connect_request_status,
    start_google_drive_connect_request,
)
from app.services.tokens import token_service


class _FakeLoopbackServer:
    def __init__(self, server_address: tuple[str, int], *, request_id: str) -> None:
        assert server_address == ("127.0.0.1", 0)
        self.request_id = request_id
        self.server_port = 43123
        self.shutdown_called = False
        self.server_close_called = False

    def serve_forever(self) -> None:
        return

    def shutdown(self) -> None:
        self.shutdown_called = True

    def server_close(self) -> None:
        self.server_close_called = True


class _FakeThread:
    def __init__(self, *, target, name: str, daemon: bool) -> None:
        self._target = target
        self._name = name
        self._daemon = daemon
        self._alive = False

    def start(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float) -> None:
        assert timeout >= 0
        self._alive = False


def test_google_drive_connect_request_uses_loopback_oauth_and_persists_namespace_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    set_encryption_required(False)
    token_service.reset()
    try:
        with begin_writer() as connection:
            insert_default_settings(connection)

        token = token_service.create_token(client_info="test", owner_tab_id="tab", dek=None)
        monkeypatch.setattr(
            google_drive_service,
            "GOOGLE_DRIVE_CLIENT_ID",
            "desktop-client-id.apps.googleusercontent.com",
        )
        monkeypatch.setattr(google_drive_service, "GOOGLE_DRIVE_CLIENT_SECRET", "")
        monkeypatch.setattr(
            google_drive_service,
            "_exchange_code_for_tokens",
            lambda *, code, redirect_uri, client_id, client_secret, code_verifier: {
                "access_token": f"access-{code}",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
            },
        )
        monkeypatch.setattr(
            google_drive_service,
            "_ensure_root_folder",
            lambda *, access_token, root_folder_name: "drive-root-folder-id",
        )
        monkeypatch.setattr(
            google_drive_service,
            "_get_google_account_email",
            lambda *, access_token: "namespace-user@example.com",
        )
        monkeypatch.setattr(google_drive_service, "_GoogleDriveLoopbackServer", _FakeLoopbackServer)
        monkeypatch.setattr(google_drive_service, "Thread", _FakeThread)

        connect_request = start_google_drive_connect_request(token=token)

        assert connect_request["request_id"] != ""
        authorization_query = parse_qs(urlsplit(connect_request["authorization_url"]).query)
        assert authorization_query["client_id"] == ["desktop-client-id.apps.googleusercontent.com"]
        assert authorization_query["code_challenge_method"] == ["S256"]
        assert authorization_query["response_type"] == ["code"]
        assert authorization_query["scope"] == ["https://www.googleapis.com/auth/drive.file"]

        redirect_uri = authorization_query["redirect_uri"][0]
        state = authorization_query["state"][0]
        redirect_parts = urlsplit(redirect_uri)
        assert redirect_parts.scheme == "http"
        assert redirect_parts.hostname == "127.0.0.1"
        assert redirect_parts.port is not None

        pending_status = get_google_drive_connect_request_status(request_id=connect_request["request_id"])
        assert pending_status.status == "pending"

        status_code, title, callback_message = google_drive_service._handle_google_drive_loopback_callback(
            request_id=connect_request["request_id"],
            callback_path=f"/?state={state}&code=oauth-code-123",
        )
        assert status_code == 200
        assert title == "Google Drive connected"
        assert callback_message == "Google Drive connected. Return to MetaList."
        google_drive_service._close_google_drive_connect_request_server(
            request_id=connect_request["request_id"],
        )

        final_status = get_google_drive_connect_request_status(request_id=connect_request["request_id"])
        assert final_status.status == "success"
        assert final_status.message == "Google Drive connected. Return to MetaList."

        settings = load_backup_settings(token=token)
        google_drive = settings["google_drive"]
        assert isinstance(google_drive, dict)
        assert google_drive["status"] == "connected"
        assert google_drive["account_email"] == "namespace-user@example.com"
        assert google_drive["access_token"] == "access-oauth-code-123"
        assert google_drive["refresh_token"] == "refresh-token"
        assert google_drive["root_folder_id"] == "drive-root-folder-id"
        assert google_drive["root_folder_name"] == google_drive_service.GOOGLE_DRIVE_ROOT_FOLDER_NAME
    finally:
        token_service.reset()
        set_encryption_required(False)
        SafeSession.use_file_db()
