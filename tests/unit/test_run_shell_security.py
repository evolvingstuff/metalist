from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from starlette.requests import Request

import app.api.routes.notes as notes_route
import app.usecases.run_shell as run_shell_module
from app.usecases.run_shell import CmdRunShellStart
from app.usecases.run_shell import CmdRunShellStatus


def _request_from_host(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api2/notes/note-123/run-shell",
            "headers": [],
            "client": (host, 43210),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_shell_route_accepts_loopback_clients() -> None:
    notes_route._require_loopback_shell_request(_request_from_host("127.0.0.1"))
    notes_route._require_loopback_shell_request(_request_from_host("::1"))


def test_shell_route_rejects_non_loopback_clients() -> None:
    with pytest.raises(HTTPException) as exc_info:
        notes_route._require_loopback_shell_request(_request_from_host("192.168.1.50"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Shell execution is restricted to loopback clients"


def test_passwordless_namespace_rejects_shell_before_loading_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_note_is_loaded(note_id: str) -> None:
        raise AssertionError(f"passwordless shell attempt loaded note {note_id}")

    def fail_if_shell_is_started(**kwargs: object) -> None:
        raise AssertionError(f"passwordless shell attempt started a process: {kwargs}")

    monkeypatch.setattr(run_shell_module, "is_shell_execution_enabled", lambda: True)
    monkeypatch.setattr(run_shell_module, "is_encryption_required", lambda: False)
    monkeypatch.setattr(run_shell_module.store, "get", fail_if_note_is_loaded)
    monkeypatch.setattr(
        run_shell_module.shell_session_service,
        "start_run",
        fail_if_shell_is_started,
    )

    response = CmdRunShellStart(note_id="note-123", timeout_seconds=30).execute()

    assert response == {
        "runId": "",
        "status": "error",
        "exitCode": -1,
        "stdout": "",
        "stderr": "",
        "durationMs": 0,
        "errorMessage": "Shell execution requires password protection",
    }


def test_password_protected_namespace_can_start_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_arguments: dict[str, object] = {}
    expected_response = {
        "runId": "run-123",
        "status": "running",
        "exitCode": None,
        "stdout": "",
        "stderr": "",
        "durationMs": 0,
        "errorMessage": None,
    }

    def capture_shell_start(**kwargs: object) -> dict[str, object]:
        captured_arguments.update(kwargs)
        return expected_response

    monkeypatch.setattr(run_shell_module, "is_shell_execution_enabled", lambda: True)
    monkeypatch.setattr(run_shell_module, "is_encryption_required", lambda: True)
    monkeypatch.setattr(
        run_shell_module.store,
        "get",
        lambda note_id: SimpleNamespace(
            id=note_id,
            tags="@shell",
            content="<div>printf protected</div>",
        ),
    )
    monkeypatch.setattr(
        run_shell_module.shell_session_service,
        "start_run",
        capture_shell_start,
    )

    response = CmdRunShellStart(note_id="note-123", timeout_seconds=30).execute()

    assert response == expected_response
    assert captured_arguments == {
        "note_id": "note-123",
        "script_text": "printf protected",
        "timeout_seconds": 30,
    }


def test_passwordless_namespace_rejects_shell_status_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_snapshot_is_loaded(**kwargs: object) -> None:
        raise AssertionError(f"passwordless shell attempt loaded a snapshot: {kwargs}")

    monkeypatch.setattr(run_shell_module, "is_shell_execution_enabled", lambda: True)
    monkeypatch.setattr(run_shell_module, "is_encryption_required", lambda: False)
    monkeypatch.setattr(
        run_shell_module.shell_session_service,
        "get_snapshot",
        fail_if_snapshot_is_loaded,
    )

    response = CmdRunShellStatus(note_id="note-123", run_id="run-123").execute()

    assert response["status"] == "error"
    assert response["runId"] == ""
    assert response["errorMessage"] == "Shell execution requires password protection"


def test_shell_disabled_server_rejects_start_before_password_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_shell_module, "is_shell_execution_enabled", lambda: False)
    monkeypatch.setattr(
        run_shell_module,
        "is_encryption_required",
        lambda: (_ for _ in ()).throw(AssertionError("password state must not be checked")),
    )

    response = CmdRunShellStart(note_id="note-123", timeout_seconds=30).execute()

    assert response["status"] == "error"
    assert response["errorMessage"] == "Shell execution is disabled for this server"
