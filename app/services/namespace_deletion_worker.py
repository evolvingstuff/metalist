from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import time
import traceback

import app.server_runtime as server_runtime
from app.server_runtime import delete_namespace_launch_profile
from app.server_runtime import resolve_namespace_directory
from app.server_runtime import validate_namespace
from app.services.namespace_deletion_jobs import mark_namespace_deletion_job_failed
from app.services.namespace_deletion_jobs import mark_namespace_deletion_job_succeeded


_WAIT_POLL_INTERVAL_SECONDS = 0.25
_INITIAL_EXIT_GRACE_SECONDS = 1.0
_TERMINATE_GRACE_SECONDS = 5.0
_KILL_GRACE_SECONDS = 5.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete a namespace after its server process exits")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--job-id", required=True)
    return parser.parse_args()


def _read_process_state(*, pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return None
    process_state = result.stdout.strip()
    if process_state == "":
        return None
    return process_state


def _is_process_running(*, pid: int) -> bool:
    if not isinstance(pid, int):
        raise TypeError(f"pid must be an int, got {type(pid)}")
    if pid <= 0:
        raise ValueError(f"pid must be positive, got: {pid}")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
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
    try:
        os.kill(pid, signal_number)
    except ProcessLookupError:
        return


def _stop_process(*, pid: int) -> None:
    if _wait_for_process_exit(pid=pid, timeout_seconds=_INITIAL_EXIT_GRACE_SECONDS):
        return

    _send_signal_if_running(pid=pid, signal_number=signal.SIGTERM)
    if _wait_for_process_exit(pid=pid, timeout_seconds=_TERMINATE_GRACE_SECONDS):
        return

    _send_signal_if_running(pid=pid, signal_number=signal.SIGKILL)
    if _wait_for_process_exit(pid=pid, timeout_seconds=_KILL_GRACE_SECONDS):
        return

    raise RuntimeError(f"Timed out waiting for process {pid} to exit")


def _delete_namespace_directory(*, namespace: str) -> None:
    namespace_directory = resolve_namespace_directory(namespace=namespace)
    if not namespace_directory.exists():
        return
    if not namespace_directory.is_dir():
        raise RuntimeError(f"Namespace path is not a directory: {namespace_directory}")
    shutil.rmtree(namespace_directory)


def main() -> None:
    args = _parse_args()
    try:
        normalized_namespace = validate_namespace(namespace=args.namespace)
        if normalized_namespace == server_runtime._DEFAULT_NAMESPACE:
            raise RuntimeError("Default namespace cannot be deleted")

        _stop_process(pid=args.pid)
        _delete_namespace_directory(namespace=normalized_namespace)
        delete_namespace_launch_profile(namespace=normalized_namespace)
        mark_namespace_deletion_job_succeeded(job_id=args.job_id)
    except Exception:
        mark_namespace_deletion_job_failed(
            job_id=args.job_id,
            error=traceback.format_exc(),
        )
        raise


if __name__ == "__main__":
    main()
