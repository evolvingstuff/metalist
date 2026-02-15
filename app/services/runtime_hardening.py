from __future__ import annotations

import re
import subprocess
import sys
from typing import Sequence

from app.config import (
    SECURITY_HARDENING_ENABLED,
    SECURITY_REQUIRE_ENCRYPTED_SWAP,
    SECURITY_REQUIRE_MACOS_NO_HIBERNATION,
)

if sys.platform == "win32":
    _resource = None
else:
    import resource as _resource


def _run_command(command: Sequence[str]) -> str:
    completed = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(
            f"Command failed: {' '.join(command)} exit={completed.returncode} stderr={stderr}"
        )
    return completed.stdout


def disable_core_dumps() -> None:
    if _resource is None:
        return
    _resource.setrlimit(_resource.RLIMIT_CORE, (0, 0))
    soft_limit, hard_limit = _resource.getrlimit(_resource.RLIMIT_CORE)
    if soft_limit != 0 or hard_limit != 0:
        raise RuntimeError(
            f"Failed to disable core dumps: soft={soft_limit} hard={hard_limit}"
        )


def _parse_pmset_values(output: str, key: str) -> list[int]:
    pattern = re.compile(rf"\b{re.escape(key)}\s+(\d+)\b")
    values = [int(match.group(1)) for match in pattern.finditer(output)]
    if not values:
        raise RuntimeError(f"pmset output missing key {key!r}")
    return values


def _assert_macos_no_hibernation() -> None:
    output = _run_command(["pmset", "-g", "custom"])
    settings = ("hibernatemode", "standby", "autopoweroff")
    for key in settings:
        values = _parse_pmset_values(output, key)
        for value in values:
            if value != 0:
                raise RuntimeError(
                    "Unsafe macOS memory-to-disk power setting detected: "
                    f"{key}={value}. Set to 0 to avoid writing RAM to disk."
                )


def _assert_macos_encrypted_swap() -> None:
    output = _run_command(["sysctl", "vm.swapusage"])
    if "(encrypted)" not in output:
        raise RuntimeError(
            "Swap is not reported as encrypted by macOS. "
            "Refusing startup because memory pages may be written unencrypted."
        )


def apply_runtime_hardening() -> None:
    if not SECURITY_HARDENING_ENABLED:
        return

    disable_core_dumps()

    if sys.platform != "darwin":
        return

    if SECURITY_REQUIRE_MACOS_NO_HIBERNATION:
        _assert_macos_no_hibernation()
    if SECURITY_REQUIRE_ENCRYPTED_SWAP:
        _assert_macos_encrypted_swap()

