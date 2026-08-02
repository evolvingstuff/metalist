from __future__ import annotations

from pathlib import Path

import pytest

import app.server_runtime as server_runtime
import app.services.namespace_rename_worker as namespace_rename_worker
from app.server_runtime import load_namespace_launch_profile
from app.server_runtime import save_namespace_launch_profile


def test_rename_namespace_storage_moves_databases_and_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    save_namespace_launch_profile(
        namespace="default",
        port=8000,
        https_port=None,
        mcp_port=8765,
    )
    source_directory = server_runtime.resolve_namespace_directory(namespace="default")
    source_files_database = source_directory / "default.metalist.files.db"
    source_files_database.write_bytes(b"files")
    backups_directory = source_directory / "backups"
    backups_directory.mkdir()
    historical_backup = backups_directory / "default-old.metalist-backup.tar.gz"
    historical_backup.write_bytes(b"backup")

    namespace_rename_worker._rename_namespace_storage(
        source_namespace="default",
        target_namespace="personal",
    )

    assert not source_directory.exists()
    target_directory = server_runtime.resolve_namespace_directory(namespace="personal")
    assert (target_directory / "personal.metalist.db").is_file()
    assert (target_directory / "personal.metalist.files.db").read_bytes() == b"files"
    assert (target_directory / "backups" / historical_backup.name).read_bytes() == b"backup"
    profile = load_namespace_launch_profile(namespace="personal")
    assert profile is not None
    assert profile.namespace == "personal"
    assert profile.port == 8000
    assert profile.mcp_port == 8765


def test_rename_namespace_storage_rejects_existing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    save_namespace_launch_profile(namespace="default", port=8000, https_port=None, mcp_port=8765)
    save_namespace_launch_profile(namespace="personal", port=8001, https_port=None, mcp_port=8766)

    with pytest.raises(RuntimeError, match="Namespace personal already exists"):
        namespace_rename_worker._rename_namespace_storage(
            source_namespace="default",
            target_namespace="personal",
        )
