from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from dataclasses import dataclass

from app.server_runtime import NamespaceLaunchProfile
from app.server_runtime import load_all_namespace_launch_profiles
from app.services.exception_capture import CapturedExceptionContext


_WAIT_POLL_INTERVAL_SECONDS = 0.25
_DEFAULT_TERM_TIMEOUT_SECONDS = 5.0
_DEFAULT_KILL_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class NamespacePort:
    namespace: str
    service: str
    port: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stop processes listening on saved MetaList namespace ports."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print listener PIDs without terminating them.",
    )
    parser.add_argument(
        "--term-timeout",
        type=float,
        default=_DEFAULT_TERM_TIMEOUT_SECONDS,
        help="Seconds to wait after SIGTERM before SIGKILL.",
    )
    parser.add_argument(
        "--kill-timeout",
        type=float,
        default=_DEFAULT_KILL_TIMEOUT_SECONDS,
        help="Seconds to wait after SIGKILL before failing.",
    )
    return parser.parse_args()


def _namespace_ports_from_profile(*, profile: NamespaceLaunchProfile) -> list[NamespacePort]:
    ports: list[NamespacePort] = [
        NamespacePort(namespace=profile.namespace, service="HTTP", port=profile.port),
        NamespacePort(namespace=profile.namespace, service="MCP", port=profile.mcp_port),
    ]
    if profile.https_port is not None:
        ports.append(NamespacePort(namespace=profile.namespace, service="HTTPS", port=profile.https_port))
    return ports


def _load_namespace_ports() -> list[NamespacePort]:
    profiles = load_all_namespace_launch_profiles()
    ports: list[NamespacePort] = []
    seen_ports: set[int] = set()
    for profile in profiles:
        for namespace_port in _namespace_ports_from_profile(profile=profile):
            if namespace_port.port in seen_ports:
                continue
            seen_ports.add(namespace_port.port)
            ports.append(namespace_port)
    return ports


def _read_process_state(*, pid: int) -> str | None:
    completed = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return None
    process_state = completed.stdout.strip()
    if process_state == "":
        return None
    return process_state


def _is_process_running(*, pid: int) -> bool:
    if not isinstance(pid, int):
        raise TypeError(f"pid must be an int, got {type(pid)}")
    if pid <= 0:
        raise ValueError(f"pid must be positive, got: {pid}")
    kill_capture = CapturedExceptionContext(ProcessLookupError, PermissionError)
    with kill_capture:
        os.kill(pid, 0)
    if kill_capture.captured_exception is not None:
        if isinstance(kill_capture.captured_exception, ProcessLookupError):
            return False
        if isinstance(kill_capture.captured_exception, PermissionError):
            return True
        raise RuntimeError("Unexpected process-probe exception type")
    process_state = _read_process_state(pid=pid)
    if process_state is None:
        return True
    if process_state.startswith("Z"):
        return False
    return True


def _wait_for_process_exit(*, pid: int, timeout_seconds: float) -> bool:
    if not isinstance(timeout_seconds, float):
        raise TypeError(f"timeout_seconds must be a float, got {type(timeout_seconds)}")
    if timeout_seconds < 0.0:
        raise ValueError(f"timeout_seconds must be >= 0.0, got {timeout_seconds}")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_process_running(pid=pid):
            return True
        time.sleep(_WAIT_POLL_INTERVAL_SECONDS)
    return not _is_process_running(pid=pid)


def _send_signal_if_running(*, pid: int, signal_number: int) -> None:
    if not _is_process_running(pid=pid):
        return
    signal_capture = CapturedExceptionContext(ProcessLookupError)
    with signal_capture:
        os.kill(pid, signal_number)
    if signal_capture.captured_exception is not None:
        return


def _stop_process(*, pid: int, term_timeout_seconds: float, kill_timeout_seconds: float) -> None:
    if not _is_process_running(pid=pid):
        return

    _send_signal_if_running(pid=pid, signal_number=signal.SIGTERM)
    if _wait_for_process_exit(pid=pid, timeout_seconds=term_timeout_seconds):
        return

    _send_signal_if_running(pid=pid, signal_number=signal.SIGKILL)
    if _wait_for_process_exit(pid=pid, timeout_seconds=kill_timeout_seconds):
        return

    raise RuntimeError(f"Timed out waiting for process {pid} to exit")


def _find_listening_pids_for_port(*, port: int) -> list[int]:
    if not isinstance(port, int):
        raise TypeError(f"port must be an int, got {type(port)}")
    if port <= 0 or port > 65535:
        raise ValueError(f"port must be between 1 and 65535, got: {port}")

    completed = subprocess.run(
        ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode == 1:
        return []
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        raise RuntimeError(
            f"`lsof` failed for port {port}: exit={completed.returncode} stdout={stdout!r} stderr={stderr!r}"
        )

    seen_pids: set[int] = set()
    ordered_pids: list[int] = []
    for raw_line in completed.stdout.splitlines():
        raw_pid = raw_line.strip()
        if raw_pid == "":
            continue
        if not raw_pid.isdigit():
            raise RuntimeError(f"`lsof` returned a non-numeric pid for port {port}: {raw_pid!r}")
        pid = int(raw_pid)
        if pid <= 0:
            raise RuntimeError(f"`lsof` returned invalid pid for port {port}: {pid}")
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        ordered_pids.append(pid)
    return ordered_pids


def _stop_namespace_port(
    *,
    namespace_port: NamespacePort,
    dry_run: bool,
    current_pid: int,
    term_timeout_seconds: float,
    kill_timeout_seconds: float,
) -> int:
    listener_pids = _find_listening_pids_for_port(port=namespace_port.port)
    stopped_count = 0
    if len(listener_pids) == 0:
        print(f"{namespace_port.namespace} {namespace_port.service} {namespace_port.port}: no listener")
        return stopped_count

    for pid in listener_pids:
        if pid == current_pid:
            raise RuntimeError(f"Refusing to stop this kill.py process on port {namespace_port.port}")
        if dry_run:
            print(
                f"{namespace_port.namespace} {namespace_port.service} {namespace_port.port}: "
                f"would stop pid {pid}"
            )
            continue
        print(f"{namespace_port.namespace} {namespace_port.service} {namespace_port.port}: stopping pid {pid}")
        _stop_process(
            pid=pid,
            term_timeout_seconds=term_timeout_seconds,
            kill_timeout_seconds=kill_timeout_seconds,
        )
        stopped_count += 1
    return stopped_count


def main() -> None:
    args = _parse_args()
    if args.term_timeout < 0.0:
        raise RuntimeError(f"--term-timeout must be >= 0, got: {args.term_timeout}")
    if args.kill_timeout < 0.0:
        raise RuntimeError(f"--kill-timeout must be >= 0, got: {args.kill_timeout}")

    namespace_ports = _load_namespace_ports()
    if len(namespace_ports) == 0:
        print("No saved namespace launch profiles found.")
        return

    stopped_count = 0
    current_pid = os.getpid()
    for namespace_port in namespace_ports:
        stopped_count += _stop_namespace_port(
            namespace_port=namespace_port,
            dry_run=args.dry_run,
            current_pid=current_pid,
            term_timeout_seconds=args.term_timeout,
            kill_timeout_seconds=args.kill_timeout,
        )
    if args.dry_run:
        print("Dry run complete.")
        return
    print(f"Stopped {stopped_count} listener process(es).")


if __name__ == "__main__":
    main()
