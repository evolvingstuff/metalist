from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.usecases.run_shell as run_shell_module
from app.usecases.run_shell import CmdRunShellStart
from app.usecases.run_shell import CmdRunShellStatus


def test_passwordless_namespace_rejects_shell_before_loading_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_note_is_loaded(note_id: str) -> None:
        raise AssertionError(f"passwordless shell attempt loaded note {note_id}")

    def fail_if_shell_is_started(**kwargs: object) -> None:
        raise AssertionError(f"passwordless shell attempt started a process: {kwargs}")

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
