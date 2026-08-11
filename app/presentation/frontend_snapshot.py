from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile


@dataclass(frozen=True)
class FrontendSnapshot:
    static_directory: Path
    template_directory: Path
    mako_module_directory: Path
    _temporary_directory: tempfile.TemporaryDirectory


def create_frontend_snapshot(source_app_directory: Path) -> FrontendSnapshot:
    if not isinstance(source_app_directory, Path):
        raise TypeError("source_app_directory must be a Path")
    source_static_directory = source_app_directory / "static"
    source_template_directory = source_app_directory / "templates"
    if not source_static_directory.is_dir():
        raise FileNotFoundError(f"Static directory not found: {source_static_directory}")
    if not source_template_directory.is_dir():
        raise FileNotFoundError(f"Template directory not found: {source_template_directory}")

    temporary_directory = tempfile.TemporaryDirectory(prefix="metalist-frontend-")
    snapshot_root = Path(temporary_directory.name)
    static_directory = snapshot_root / "static"
    template_directory = snapshot_root / "templates"
    mako_module_directory = snapshot_root / "mako_modules"
    shutil.copytree(source_static_directory, static_directory)
    shutil.copytree(source_template_directory, template_directory)
    mako_module_directory.mkdir()

    assert static_directory.is_dir()
    assert template_directory.is_dir()
    assert mako_module_directory.is_dir()
    return FrontendSnapshot(
        static_directory=static_directory,
        template_directory=template_directory,
        mako_module_directory=mako_module_directory,
        _temporary_directory=temporary_directory,
    )
