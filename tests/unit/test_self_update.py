from __future__ import annotations

import os
import subprocess

import pytest

import app.services.self_update as self_update


@pytest.mark.parametrize("platform_name", ("darwin", "linux"))
def test_schedule_posix_self_update_stops_servers_then_hands_off_to_shell(
    monkeypatch,
    platform_name: str,
) -> None:
    popen_calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        self_update,
        "stop_all_namespace_processes_for_update",
        lambda: 3,
    )
    monkeypatch.setattr(self_update.shutil, "which", lambda command: "/opt/homebrew/bin/uv")
    monkeypatch.setattr(
        self_update.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)),
    )

    result = self_update.schedule_self_update(
        metalist_executable="/Users/example/.local/bin/metalist",
        current_pid=4321,
        platform_name=platform_name,
        environ={"PATH": "/opt/homebrew/bin"},
    )

    assert result.stopped_process_count == 3
    assert result.platform_name == platform_name
    assert len(popen_calls) == 1
    command, kwargs = popen_calls[0]
    assert command[:2] == ["/bin/sh", "-c"]
    assert "kill -0 4321" in command[2]
    assert "/opt/homebrew/bin/uv tool install --force --reinstall --refresh metalist" in command[2]
    assert "/Users/example/.local/bin/metalist" in command[2]
    assert kwargs["start_new_session"] is True
    assert kwargs["cwd"] == str(self_update.Path.home())
    assert kwargs["env"] == {"PATH": "/opt/homebrew/bin"}


def test_schedule_windows_self_update_uses_external_powershell_console(monkeypatch) -> None:
    popen_calls: list[tuple[list[str], dict[str, object]]] = []
    executable_paths = {
        "uv": "C:\\Users\\example\\.local\\bin\\uv.exe",
        "powershell.exe": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    }

    def _resolve_executable(command: str) -> str | None:
        if command in executable_paths:
            return executable_paths[command]
        return None

    monkeypatch.setattr(
        self_update,
        "stop_all_namespace_processes_for_update",
        lambda: 2,
    )
    monkeypatch.setattr(self_update.shutil, "which", _resolve_executable)
    monkeypatch.setattr(
        self_update.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)),
    )

    result = self_update.schedule_self_update(
        metalist_executable="C:\\Users\\example\\.local\\bin\\metalist.exe",
        current_pid=9876,
        platform_name="win32",
        environ={"PATH": "C:\\Windows\\System32"},
    )

    assert result.stopped_process_count == 2
    assert result.platform_name == "win32"
    assert len(popen_calls) == 1
    command, kwargs = popen_calls[0]
    assert command[:5] == [
        executable_paths["powershell.exe"],
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert "Get-Process -Id 9876" in command[5]
    assert "tool install --force --reinstall --refresh metalist" in command[5]
    assert "metalist.exe" in command[5]
    assert kwargs["creationflags"] == self_update._WINDOWS_CREATE_NEW_CONSOLE
    assert kwargs["cwd"] == str(self_update.Path.home())
    assert kwargs["env"] == {"PATH": "C:\\Windows\\System32"}


def test_schedule_self_update_refuses_to_stop_servers_without_uv(monkeypatch) -> None:
    monkeypatch.setattr(self_update.shutil, "which", lambda command: None)
    monkeypatch.setattr(
        self_update,
        "stop_all_namespace_processes_for_update",
        lambda: (_ for _ in ()).throw(AssertionError("servers must remain running")),
    )

    with pytest.raises(RuntimeError, match="uv executable was not found"):
        self_update.schedule_self_update(
            metalist_executable="/Users/example/.local/bin/metalist",
            current_pid=os.getpid(),
            platform_name="linux",
            environ={},
        )


def test_schedule_windows_self_update_refuses_to_stop_servers_without_powershell(monkeypatch) -> None:
    executable_paths = {"uv": "C:\\Users\\example\\.local\\bin\\uv.exe"}

    def _resolve_executable(command: str) -> str | None:
        if command in executable_paths:
            return executable_paths[command]
        return None

    monkeypatch.setattr(self_update.shutil, "which", _resolve_executable)
    monkeypatch.setattr(
        self_update,
        "stop_all_namespace_processes_for_update",
        lambda: (_ for _ in ()).throw(AssertionError("servers must remain running")),
    )

    with pytest.raises(RuntimeError, match="PowerShell is required"):
        self_update.schedule_self_update(
            metalist_executable="C:\\Users\\example\\.local\\bin\\metalist.exe",
            current_pid=1234,
            platform_name="win32",
            environ={},
        )
