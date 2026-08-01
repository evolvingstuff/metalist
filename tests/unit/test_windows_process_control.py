from __future__ import annotations

from types import SimpleNamespace

from app.services import windows_process_control


def test_find_listening_pids_for_port_uses_powershell_and_deduplicates(monkeypatch) -> None:
    completed = SimpleNamespace(returncode=0, stdout="4321\n4321\n8765\n", stderr="")
    calls: list[list[str]] = []

    monkeypatch.setattr(
        windows_process_control,
        "_resolve_powershell_path",
        lambda: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    )
    monkeypatch.setattr(
        windows_process_control.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or completed,
    )

    assert windows_process_control.find_listening_pids_for_port(port=8443) == [4321, 8765]
    assert "Get-NetTCPConnection -State Listen -LocalPort 8443" in calls[0][-1]


def test_is_process_running_returns_false_when_powershell_finds_no_process(monkeypatch) -> None:
    completed = SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        windows_process_control,
        "_resolve_powershell_path",
        lambda: "powershell.exe",
    )
    monkeypatch.setattr(windows_process_control.subprocess, "run", lambda *args, **kwargs: completed)

    assert windows_process_control.is_process_running(pid=4321) is False


def test_stop_process_escalates_to_force(monkeypatch) -> None:
    running_results = iter([True, True, False])
    commands: list[str] = []

    monkeypatch.setattr(
        windows_process_control,
        "is_process_running",
        lambda *, pid: next(running_results),
    )
    monkeypatch.setattr(
        windows_process_control,
        "_wait_for_process_exit",
        lambda *, pid, timeout_seconds: False,
    )
    monkeypatch.setattr(
        windows_process_control,
        "_run_powershell",
        lambda *, script, operation: commands.append(script),
    )

    windows_process_control.stop_process(pid=4321)

    assert commands == [
        "Stop-Process -Id 4321 -ErrorAction Stop",
        "Stop-Process -Id 4321 -Force -ErrorAction Stop",
    ]
