from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from app.services.namespace_switcher import stop_all_namespace_processes_for_update


_WINDOWS_CREATE_NEW_CONSOLE = 0x00000010


@dataclass(frozen=True)
class SelfUpdateScheduleResult:
    stopped_process_count: int
    platform_name: str
    message: str


def schedule_self_update(
    *,
    metalist_executable: str,
    current_pid: int,
    platform_name: str,
    environ: Mapping[str, str],
) -> SelfUpdateScheduleResult:
    _validate_schedule_inputs(
        metalist_executable=metalist_executable,
        current_pid=current_pid,
        platform_name=platform_name,
    )
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        raise RuntimeError("uv executable was not found on PATH; MetaList was not stopped")

    updater_command: list[str]
    updater_options: dict[str, object]
    if platform_name == "win32":
        powershell_executable = _resolve_windows_powershell()
        updater_command = _build_windows_updater_command(
            powershell_executable=powershell_executable,
            uv_executable=uv_executable,
            metalist_executable=metalist_executable,
            current_pid=current_pid,
        )
        updater_options = {
            "creationflags": _WINDOWS_CREATE_NEW_CONSOLE,
            "cwd": str(Path.home()),
            "env": dict(environ),
        }
    else:
        shell_path = Path("/bin/sh")
        if not shell_path.is_file():
            raise RuntimeError("/bin/sh is required for MetaList self-update; MetaList was not stopped")
        updater_command = _build_posix_updater_command(
            shell_executable=str(shell_path),
            uv_executable=uv_executable,
            metalist_executable=metalist_executable,
            current_pid=current_pid,
        )
        updater_options = {
            "start_new_session": True,
            "cwd": str(Path.home()),
            "env": dict(environ),
        }

    stopped_process_count = stop_all_namespace_processes_for_update()
    subprocess.Popen(updater_command, **updater_options)
    return SelfUpdateScheduleResult(
        stopped_process_count=stopped_process_count,
        platform_name=platform_name,
        message=(
            f"Stopped {stopped_process_count} MetaList process(es). "
            "The updater will install the latest release and restart MetaList."
        ),
    )


def _validate_schedule_inputs(
    *,
    metalist_executable: str,
    current_pid: int,
    platform_name: str,
) -> None:
    if not isinstance(metalist_executable, str) or metalist_executable.strip() == "":
        raise ValueError("metalist_executable must be a non-empty string")
    if not isinstance(current_pid, int) or current_pid <= 0:
        raise ValueError("current_pid must be a positive integer")
    if platform_name not in {"darwin", "linux", "win32"}:
        raise RuntimeError(f"MetaList self-update does not support platform: {platform_name}")


def _resolve_windows_powershell() -> str:
    powershell_executable = shutil.which("powershell.exe")
    if powershell_executable is not None:
        return powershell_executable
    pwsh_executable = shutil.which("pwsh.exe")
    if pwsh_executable is not None:
        return pwsh_executable
    raise RuntimeError("PowerShell is required for MetaList self-update; MetaList was not stopped")


def _quote_powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_windows_updater_command(
    *,
    powershell_executable: str,
    uv_executable: str,
    metalist_executable: str,
    current_pid: int,
) -> list[str]:
    quoted_uv = _quote_powershell_literal(uv_executable)
    quoted_metalist = _quote_powershell_literal(metalist_executable)
    script = (
        f"while (Get-Process -Id {current_pid} -ErrorAction SilentlyContinue) "
        "{ Start-Sleep -Milliseconds 100 }; "
        f"& {quoted_uv} tool install --force --reinstall --refresh metalist; "
        "if ($LASTEXITCODE -ne 0) { "
        "Write-Host 'MetaList update failed. Review the uv output above.' -ForegroundColor Red; "
        "Start-Sleep -Seconds 10; exit $LASTEXITCODE }; "
        f"& {quoted_metalist}; "
        "if ($LASTEXITCODE -ne 0) { "
        "Write-Host 'MetaList updated, but restart failed.' -ForegroundColor Red; "
        "Start-Sleep -Seconds 10; exit $LASTEXITCODE }; "
        "Write-Host 'MetaList update complete.' -ForegroundColor Green; "
        "Start-Sleep -Seconds 3"
    )
    return [
        powershell_executable,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]


def _build_posix_updater_command(
    *,
    shell_executable: str,
    uv_executable: str,
    metalist_executable: str,
    current_pid: int,
) -> list[str]:
    uv_command = shlex.join(
        [uv_executable, "tool", "install", "--force", "--reinstall", "--refresh", "metalist"]
    )
    metalist_command = shlex.join([metalist_executable])
    script = (
        f"while kill -0 {current_pid} 2>/dev/null; do sleep 0.1; done\n"
        f"if ! {uv_command}; then\n"
        "  echo 'MetaList update failed. Review the uv output above.' >&2\n"
        "  exit 1\n"
        "fi\n"
        f"if ! {metalist_command}; then\n"
        "  echo 'MetaList updated, but restart failed.' >&2\n"
        "  exit 1\n"
        "fi\n"
        "echo 'MetaList update complete.'\n"
    )
    return [shell_executable, "-c", script]
