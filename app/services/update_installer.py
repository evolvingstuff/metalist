"""Select a compatible Windows installer; also runs standalone for old installations."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import io
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile
from urllib.request import urlopen
import zipfile


# Official immutable 0.12.17 release assets. 0.12.13 removed the temporary
# Windows PE resource-editing operation that can fail under file inspection.
INSTALLER_VERSION = "0.12.17"
MINIMUM_WINDOWS_VERSION = (0, 12, 13)
WINDOWS_INSTALLERS = {
    "x86_64": (
        "a252121d5b59398fcb137c6ea448176459a44010f33f67e0072305a637119ca7",
        "2019cdf564cb8f749262f5f021cedc75a99abb1c6081227ca340bbcda972611d",
    ),
    "aarch64": (
        "3e1aa6849d77f0e00dc865e4afab5c5b32de053e21fe35bf5ad5cec3734ec976",
        "92e3a7af84b7da8925997eb5b856595e1c36a4b3591fbccee7d143e69f1c8656",
    ),
    "i686": (
        "1d3653cb6eafd1e675e979d7cd8eeac1456202f8927a2216419993077a4c473f",
        "8d08a9c61f18f9436069f3ccf6e13e7f665b0e9b1ff85ac98f1ec8261c493145",
    ),
}


def _installer_version(executable: str, environ: Mapping[str, str]) -> tuple[int, int, int]:
    completed = subprocess.run([executable, "--version"], env=dict(environ),
                               capture_output=True, text=True, check=True, timeout=30)
    match = re.fullmatch(r"uv (\d+)\.(\d+)\.(\d+)(?: \([^\r\n]+\))?", completed.stdout.strip())
    if match is None:
        raise RuntimeError("Cannot verify the uv installer version; MetaList was not stopped")
    return tuple(int(part) for part in match.groups())


def _windows_architecture() -> str:
    machine = platform.machine().casefold()
    aliases = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64",
               "aarch64": "aarch64", "x86": "i686", "i386": "i686", "i686": "i686"}
    if machine not in aliases:
        raise RuntimeError(f"Unsupported Windows updater architecture: {machine}")
    return aliases[machine]


def _download_installer_archive(architecture: str) -> bytes:
    assert architecture in WINDOWS_INSTALLERS
    url = (f"https://github.com/astral-sh/uv/releases/download/{INSTALLER_VERSION}/"
           f"uv-{architecture}-pc-windows-msvc.zip")
    with urlopen(url, timeout=120) as response:
        return response.read()


def _managed_windows_installer(environ: Mapping[str, str]) -> str:
    architecture = _windows_architecture()
    archive_digest, binary_digest = WINDOWS_INSTALLERS[architecture]
    local_directory = Path(environ["LOCALAPPDATA"])
    if not local_directory.is_absolute():
        raise RuntimeError("LOCALAPPDATA must be an absolute path for the update installer")
    directory = local_directory / "MetaList" / "update-tools" / f"uv-{INSTALLER_VERSION}-{architecture}"
    executable = directory / "uv.exe"
    if executable.exists():
        if hashlib.sha256(executable.read_bytes()).hexdigest() != binary_digest:
            raise RuntimeError("Cached update installer failed checksum verification; MetaList was not stopped")
        return str(executable)
    print(f"Preparing verified Windows update installer uv {INSTALLER_VERSION}...", flush=True)
    archive_body = _download_installer_archive(architecture)
    if hashlib.sha256(archive_body).hexdigest() != archive_digest:
        raise RuntimeError("Downloaded update installer failed checksum verification; MetaList was not stopped")
    with zipfile.ZipFile(io.BytesIO(archive_body)) as archive:
        binary = archive.read("uv.exe")
    if hashlib.sha256(binary).hexdigest() != binary_digest:
        raise RuntimeError("Update installer executable failed checksum verification; MetaList was not stopped")
    directory.mkdir(parents=True, exist_ok=True)
    # Publish only complete, verified bytes. This is an installer cache, never a backup.
    with NamedTemporaryFile(dir=directory, prefix="uv-", suffix=".tmp", delete=False) as staged:
        staged.write(binary)
    os.replace(staged.name, executable)
    return str(executable)


def resolve_update_installer(*, uv_executable: str, platform_name: str,
                             environ: Mapping[str, str]) -> str:
    if platform_name != "win32":
        return uv_executable
    if _installer_version(uv_executable, environ) >= MINIMUM_WINDOWS_VERSION:
        return uv_executable
    executable = _managed_windows_installer(environ)
    expected_version = tuple(int(part) for part in INSTALLER_VERSION.split("."))
    if _installer_version(executable, environ) != expected_version:
        raise RuntimeError("Verified update installer reported the wrong version; MetaList was not stopped")
    return executable


def repair_windows_update() -> None:
    if sys.platform != "win32":
        raise RuntimeError("This recovery launcher is for Windows installations")
    uv_executable = shutil.which("uv")
    metalist_executable = shutil.which("metalist")
    if uv_executable is None or metalist_executable is None:
        raise RuntimeError("The existing uv and MetaList commands must be available on PATH")
    environ = dict(os.environ)
    installer = resolve_update_installer(uv_executable=uv_executable, platform_name="win32", environ=environ)
    # The already-installed updater discovers uv through PATH. Preserve that
    # updater's preflight, shutdown, backup, offline install, and restart flow.
    environ["PATH"] = str(Path(installer).parent) + os.pathsep + environ["PATH"]
    subprocess.run([metalist_executable, "update"], env=environ, check=True)


if __name__ == "__main__":
    repair_windows_update()
