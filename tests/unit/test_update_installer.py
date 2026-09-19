import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from app.services import update_installer
from scripts.build_windows_update_repair import build_repair_archive


@pytest.fixture
def installer_fixture(monkeypatch, tmp_path):
    binary = b"verified installer fixture"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("uv.exe", binary)
    archive_body = stream.getvalue()
    monkeypatch.setattr(update_installer, "WINDOWS_INSTALLERS", {"x86_64": (
        hashlib.sha256(archive_body).hexdigest(), hashlib.sha256(binary).hexdigest(),
    )})
    monkeypatch.setattr(update_installer, "_windows_architecture", lambda: "x86_64")
    downloads = []

    def download(architecture):
        downloads.append(architecture)
        return archive_body

    monkeypatch.setattr(update_installer, "_download_installer_archive", download)
    return {"LOCALAPPDATA": str(tmp_path), "PATH": "original-path"}, binary, downloads


def test_old_windows_installer_is_replaced_privately_before_use(monkeypatch, installer_fixture):
    environ, binary, downloads = installer_fixture
    calls = []

    def run(command, **kwargs):
        assert command[1:] == ["--version"]
        calls.append(command[0])
        version = update_installer.INSTALLER_VERSION
        if command[0] == "old-uv":
            version = "0.11.23"
        return SimpleNamespace(stdout=f"uv {version} (fixture 2026-09-19)\n")

    monkeypatch.setattr(update_installer.subprocess, "run", run)
    selected = update_installer.resolve_update_installer(
        uv_executable="old-uv", platform_name="win32", environ=environ,
    )
    assert Path(selected).read_bytes() == binary
    assert calls == ["old-uv", selected]
    assert downloads == ["x86_64"]
    assert environ["PATH"] == "original-path"
    assert update_installer._managed_windows_installer(environ) == selected
    assert downloads == ["x86_64"], "A verified cached installer needs no redownload"


@pytest.mark.parametrize("version", [(0, 12, 13), (0, 12, 17), (1, 0, 0)])
def test_fixed_windows_installer_is_used_without_downloading(monkeypatch, version):
    monkeypatch.setattr(update_installer, "_installer_version", lambda *args: version)
    monkeypatch.setattr(update_installer, "_managed_windows_installer", lambda *args: pytest.fail("unexpected download"))
    assert update_installer.resolve_update_installer(uv_executable="installed-uv", platform_name="win32", environ={}) == "installed-uv"


@pytest.mark.parametrize("platform_name", ["darwin", "linux"])
def test_non_windows_update_keeps_existing_installer(monkeypatch, platform_name):
    monkeypatch.setattr(update_installer.subprocess, "run", lambda *args, **kwargs: pytest.fail("unexpected probe"))
    assert update_installer.resolve_update_installer(uv_executable="uv", platform_name=platform_name, environ={}) == "uv"


def test_bad_download_never_publishes_or_executes_installer(monkeypatch, installer_fixture):
    environ, _, _ = installer_fixture
    monkeypatch.setattr(update_installer, "_download_installer_archive", lambda arch: b"altered archive")
    with pytest.raises(RuntimeError, match="Downloaded update installer failed checksum"):
        update_installer._managed_windows_installer(environ)
    assert not list(Path(environ["LOCALAPPDATA"]).rglob("uv.exe"))


def test_binary_checksum_is_checked_even_when_archive_checksum_matches(monkeypatch, installer_fixture):
    environ, _, _ = installer_fixture
    archive_digest, _ = update_installer.WINDOWS_INSTALLERS["x86_64"]
    monkeypatch.setitem(update_installer.WINDOWS_INSTALLERS, "x86_64", (archive_digest, "0" * 64))
    with pytest.raises(RuntimeError, match="executable failed checksum"):
        update_installer._managed_windows_installer(environ)
    assert not list(Path(environ["LOCALAPPDATA"]).rglob("uv.exe"))


def test_managed_installer_must_report_the_pinned_version(monkeypatch, installer_fixture):
    environ, _, _ = installer_fixture
    versions = iter(((0, 11, 23), (0, 12, 16)))
    monkeypatch.setattr(update_installer, "_installer_version", lambda *args: next(versions))
    with pytest.raises(RuntimeError, match="wrong version"):
        update_installer.resolve_update_installer(uv_executable="old-uv", platform_name="win32", environ=environ)


def test_tampered_cached_binary_is_rejected(installer_fixture):
    environ, _, _ = installer_fixture
    path = Path(update_installer._managed_windows_installer(environ))
    path.write_bytes(b"tampered executable")
    with pytest.raises(RuntimeError, match="Cached update installer failed checksum"):
        update_installer._managed_windows_installer(environ)


def test_download_failure_propagates_before_any_installer_is_published(monkeypatch, installer_fixture):
    environ, _, _ = installer_fixture

    def unavailable(architecture):
        raise OSError("network unavailable")

    monkeypatch.setattr(update_installer, "_download_installer_archive", unavailable)
    with pytest.raises(OSError, match="network unavailable"):
        update_installer._managed_windows_installer(environ)
    assert not list(Path(environ["LOCALAPPDATA"]).rglob("uv.exe"))


@pytest.mark.parametrize("stdout", ["", "uv not-a-version", "uv 0.12.13-dev"])
def test_unverifiable_version_is_rejected(monkeypatch, stdout):
    monkeypatch.setattr(update_installer.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=stdout))
    with pytest.raises(RuntimeError, match="Cannot verify"):
        update_installer._installer_version("uv", {})


def test_recovery_runs_existing_updater_with_fixed_installer_on_child_path(monkeypatch, tmp_path):
    selected = str(tmp_path / "fixed" / "uv.exe")
    monkeypatch.setattr(update_installer, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(update_installer.shutil, "which", lambda command: "/existing/" + command)
    monkeypatch.setattr(update_installer, "resolve_update_installer", lambda **kwargs: selected)
    monkeypatch.setenv("PATH", "/original/path")
    calls = []
    monkeypatch.setattr(update_installer.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    update_installer.repair_windows_update()
    assert calls[0][0] == (["/existing/metalist", "update"],)
    assert calls[0][1]["check"] is True
    assert calls[0][1]["env"]["PATH"].startswith(str(Path(selected).parent) + update_installer.os.pathsep)
    assert update_installer.os.environ["PATH"] == "/original/path"


def test_recovery_does_not_continue_after_installer_failure(monkeypatch):
    monkeypatch.setattr(update_installer, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(update_installer.shutil, "which", lambda command: "/existing/" + command)

    def broken_installer(**kwargs):
        raise RuntimeError("checksum failed")

    monkeypatch.setattr(update_installer, "resolve_update_installer", broken_installer)
    monkeypatch.setattr(update_installer.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not run updater"))
    with pytest.raises(RuntimeError, match="checksum failed"):
        update_installer.repair_windows_update()


def test_repair_archive_contains_current_production_resolver_and_launcher(tmp_path):
    archive_path = tmp_path / "repair.zip"
    build_repair_archive(archive_path)
    root = Path(__file__).resolve().parents[2]
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {"Repair-MetaList.cmd", "update_installer.py", "README.txt"}
        assert archive.read("update_installer.py") == (root / "app/services/update_installer.py").read_bytes()
        assert archive.read("Repair-MetaList.cmd") == (root / "scripts/Repair-MetaList.cmd").read_bytes()
    original_archive = archive_path.read_bytes()
    with pytest.raises(FileExistsError):
        build_repair_archive(archive_path)
    assert archive_path.read_bytes() == original_archive
