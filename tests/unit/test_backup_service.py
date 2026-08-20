from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.db.file_schema import initialize_file_schema
from app.db.file_session import resolve_file_database_path
from app.db.schema import NAMESPACE_LAUNCH_PROFILE_TABLE
from app.db.schema import initialize_schema
from app.models.database import SafeSession
from app.services import backup_service as backup_service_module
from app.services.search_history_storage import serialize_search_history_payload
from app.services.backup_service import (
    create_timestamped_backup_for_paths,
    delete_oldest_backups_in_directory,
    list_backups_in_directory,
    read_backup_launch_profile,
    resolve_backup_directory_for_database,
    restore_backup_to_paths,
    restore_backup_to_paths_from_namespace,
)


def _write_counter(database_path: Path, counter: int) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE IF NOT EXISTS backup_test (counter INTEGER NOT NULL)")
        connection.execute("DELETE FROM backup_test")
        connection.execute("INSERT INTO backup_test(counter) VALUES (?)", (counter,))
        connection.commit()
    finally:
        connection.close()


def _read_counter(database_path: Path) -> int:
    connection = sqlite3.connect(str(database_path))
    try:
        cursor = connection.execute("SELECT counter FROM backup_test LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("backup_test row missing")
        return int(row[0])
    finally:
        connection.close()


def _write_launch_profile(
    *,
    database_path: Path,
    namespace: str,
    port: int,
    https_port: int | None,
    mcp_port: int,
) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    try:
        initialize_schema(connection)
        connection.execute(
            f"""
            INSERT INTO {NAMESPACE_LAUNCH_PROFILE_TABLE} (
                namespace,
                port,
                https_port,
                mcp_port,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """,
            (namespace, port, https_port, mcp_port),
        )
        connection.commit()
    finally:
        connection.close()


def _read_launch_profile_namespace(*, database_path: Path) -> str:
    connection = sqlite3.connect(str(database_path))
    try:
        row = connection.execute(
            f"""
            SELECT namespace
            FROM {NAMESPACE_LAUNCH_PROFILE_TABLE}
            ORDER BY namespace ASC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return str(row[0])


def _write_file_marker(database_path: Path, file_id: str) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    try:
        initialize_file_schema(connection)
        connection.execute("DELETE FROM files")
        connection.execute(
            """
            INSERT INTO files (
                id,
                title,
                title_encryption_nonce,
                title_encryption_tag,
                metadata_json,
                metadata_encryption_nonce,
                metadata_encryption_tag,
                blob_data,
                blob_encryption_nonce,
                blob_encryption_tag,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                "title",
                None,
                None,
                "{\"original_filename\":\"file.bin\",\"mime_type\":\"application/octet-stream\",\"size_bytes\":4,\"thumbnail_kind\":\"other\"}",
                None,
                None,
                b"blob",
                None,
                None,
                "2026-03-05T00:00:00+00:00",
                "2026-03-05T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _read_file_ids(database_path: Path) -> list[str]:
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    try:
        initialize_file_schema(connection)
        rows = connection.execute("SELECT id FROM files ORDER BY id ASC").fetchall()
        return [str(row["id"]) for row in rows]
    finally:
        connection.close()


def _resolve_legacy_search_history_database_path(database_path: Path) -> Path:
    return database_path.with_name(f"{database_path.stem}.search-history{database_path.suffix}")


def _write_search_history_marker(database_path: Path, query_key: str) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    try:
        initialize_schema(connection)
        connection.execute("DELETE FROM search_interaction_history")
        connection.execute(
            """
            INSERT INTO search_interaction_history (
                storage_id,
                payload_json,
                payload_encryption_nonce,
                payload_encryption_tag
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "00000000-0000-4000-8000-000000000001",
                serialize_search_history_payload(
                    counts_by_date={"2026-03-05": {query_key: 1}},
                ),
                None,
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _read_search_history_queries(database_path: Path) -> list[str]:
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    try:
        initialize_schema(connection)
        rows = connection.execute(
            "SELECT payload_json FROM search_interaction_history ORDER BY storage_id ASC"
        ).fetchall()
        query_keys: list[str] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            counts_by_date = payload["counts_by_date"]
            for tag_counts in counts_by_date.values():
                query_keys.extend(str(tag_name) for tag_name in tag_counts)
        return sorted(query_keys)
    finally:
        connection.close()


def _copy_database_for_fixture(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(str(source_path))
    target_connection = sqlite3.connect(str(target_path))
    try:
        source_connection.execute("PRAGMA wal_checkpoint(FULL)")
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()


def _read_archive_manifest(backup_path: Path) -> dict[str, object]:
    with tarfile.open(backup_path, mode="r:gz") as archive_handle:
        manifest_handle = archive_handle.extractfile("manifest.json")
        if manifest_handle is None:
            raise RuntimeError("manifest.json missing from archive")
        try:
            payload = manifest_handle.read()
        finally:
            manifest_handle.close()
    manifest = json.loads(payload)
    if not isinstance(manifest, dict):
        raise RuntimeError("archive manifest must be a JSON object")
    return manifest


def _archive_member_names(backup_path: Path) -> set[str]:
    with tarfile.open(backup_path, mode="r:gz") as archive_handle:
        return {member.name for member in archive_handle.getmembers()}


def _sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_archive_fixture(
    backup_path: Path,
    *,
    manifest: dict[str, object],
    archive_files: dict[str, Path],
) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="backup-fixture-") as temp_directory:
        temp_directory_path = Path(temp_directory)
        manifest_path = temp_directory_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        copied_members: list[tuple[Path, str]] = []
        for archive_name, source_path in archive_files.items():
            target_path = temp_directory_path / archive_name
            shutil.copyfile(source_path, target_path)
            copied_members.append((target_path, archive_name))

        with tarfile.open(backup_path, mode="w:gz") as archive_handle:
            archive_handle.add(manifest_path, arcname="manifest.json")
            for member_path, archive_name in copied_members:
                archive_handle.add(member_path, arcname=archive_name)


def test_create_and_restore_backup_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    backup_directory = tmp_path / "backups"

    _write_counter(database_path, 7)
    backup_file = create_timestamped_backup_for_paths(database_path, backup_directory)
    backup_path = backup_directory / backup_file.filename
    immutable_backup_hash = _sha256_for_path(backup_path)

    assert backup_file.filename.startswith("live-")
    assert backup_file.filename.endswith(".metalist-backup.tar.gz")
    assert _archive_member_names(backup_path) == {"manifest.json", "live.db"}

    manifest = _read_archive_manifest(backup_path)
    assert manifest["backup_format_version"] == 1
    assert manifest["manifest_schema_version"] == 1
    assert manifest["namespace"] == "live"
    assert manifest["encryption_enabled"] is False
    files = manifest["files"]
    assert isinstance(files, list)
    assert len(files) == 1
    assert files[0]["archive_name"] == "live.db"
    assert files[0]["database_role"] == "notes"

    _write_counter(database_path, 99)
    assert _read_counter(database_path) == 99

    restore_backup_to_paths(backup_path, database_path)
    assert _read_counter(database_path) == 7
    assert _sha256_for_path(backup_path) == immutable_backup_hash


def test_backup_creation_never_overwrites_an_existing_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "live.db"
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    _write_counter(database_path, 7)
    fixed_filename = "live-20260820-120000-000000.metalist-backup.tar.gz"
    existing_backup = backup_directory / fixed_filename
    existing_backup.write_bytes(b"existing-immutable-archive")
    existing_hash = _sha256_for_path(existing_backup)
    monkeypatch.setattr(
        backup_service_module,
        "_format_archive_backup_filename",
        lambda *, namespace, now_utc: fixed_filename,
    )

    with pytest.raises(FileExistsError, match="Backup already exists"):
        create_timestamped_backup_for_paths(database_path, backup_directory)

    assert _sha256_for_path(existing_backup) == existing_hash


def test_restore_detects_any_source_archive_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "live.db"
    backup_directory = tmp_path / "backups"
    _write_counter(database_path, 7)
    backup = create_timestamped_backup_for_paths(database_path, backup_directory)
    backup_path = backup_directory / backup.filename

    def _mutate_source(
        source_path: Path,
        _database_path: Path,
        *,
        source_namespace: str | None,
    ) -> None:
        assert source_namespace is None
        source_path.write_bytes(b"mutated-during-restore")

    monkeypatch.setattr(
        backup_service_module,
        "_restore_archive_backup_to_paths",
        _mutate_source,
    )

    with pytest.raises(RuntimeError, match="Restore source was modified"):
        restore_backup_to_paths(backup_path, database_path)


def test_restore_refuses_to_use_live_database_as_backup_source(tmp_path: Path) -> None:
    database_path = tmp_path / "20260820-120000-000000.live.db.bak"
    _write_counter(database_path, 7)

    with pytest.raises(ValueError, match="source and live database destination must differ"):
        restore_backup_to_paths(database_path, database_path)


def test_restore_archive_into_different_namespace_rewrites_launch_profile(tmp_path: Path) -> None:
    source_database_path = tmp_path / "namespaces" / "source" / "source.metalist.db"
    target_database_path = tmp_path / "namespaces" / "target" / "target.metalist.db"
    backup_directory = tmp_path / "backups"

    _write_counter(source_database_path, 7)
    _write_launch_profile(
        database_path=source_database_path,
        namespace="source",
        port=8010,
        https_port=None,
        mcp_port=8770,
    )
    backup_file = create_timestamped_backup_for_paths(source_database_path, backup_directory)
    backup_path = backup_directory / backup_file.filename

    backup_profile = read_backup_launch_profile(backup_path, expected_namespace="source")
    assert backup_profile is not None
    assert backup_profile.namespace == "source"
    assert backup_profile.port == 8010
    assert backup_profile.mcp_port == 8770

    restore_backup_to_paths_from_namespace(
        backup_path,
        target_database_path,
        source_namespace="source",
    )

    assert _read_counter(target_database_path) == 7
    assert _read_launch_profile_namespace(database_path=target_database_path) == "target"


def test_resolve_backup_directory_for_database_scopes_default_namespace_database(tmp_path: Path) -> None:
    database_path = tmp_path / "namespaces" / "default" / "default.metalist.db"

    backup_directory = resolve_backup_directory_for_database(database_path)

    assert backup_directory == tmp_path / "namespaces" / "default" / "backups"


def test_resolve_backup_directory_for_database_scopes_namespaced_database(tmp_path: Path) -> None:
    database_path = tmp_path / "namespaces" / "cla" / "cla.metalist.db"

    backup_directory = resolve_backup_directory_for_database(database_path)

    assert backup_directory == tmp_path / "namespaces" / "cla" / "backups"


def test_create_and_restore_backup_round_trip_includes_related_file_db(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    file_database_path = resolve_file_database_path(database_path)
    backup_directory = tmp_path / "backups"

    _write_counter(database_path, 7)
    _write_file_marker(file_database_path, "file-a")
    backup_file = create_timestamped_backup_for_paths(database_path, backup_directory)
    backup_path = backup_directory / backup_file.filename

    assert _archive_member_names(backup_path) == {"manifest.json", "live.db", "live.files.db"}
    manifest = _read_archive_manifest(backup_path)
    files = manifest["files"]
    assert isinstance(files, list)
    file_entries = {entry["database_role"]: entry for entry in files}
    assert file_entries["notes"]["archive_name"] == "live.db"
    assert file_entries["files"]["archive_name"] == "live.files.db"

    _write_counter(database_path, 99)
    _write_file_marker(file_database_path, "file-b")
    assert _read_counter(database_path) == 99
    assert _read_file_ids(file_database_path) == ["file-b"]

    restore_backup_to_paths(backup_path, database_path)
    assert _read_counter(database_path) == 7
    assert _read_file_ids(file_database_path) == ["file-a"]


def test_create_and_restore_backup_round_trip_ignores_legacy_search_history_sidecar(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    search_history_database_path = _resolve_legacy_search_history_database_path(database_path)
    backup_directory = tmp_path / "backups"

    _write_counter(database_path, 7)
    _write_search_history_marker(search_history_database_path, "journal")
    backup_file = create_timestamped_backup_for_paths(database_path, backup_directory)
    backup_path = backup_directory / backup_file.filename

    assert _archive_member_names(backup_path) == {"manifest.json", "live.db"}
    manifest = _read_archive_manifest(backup_path)
    files = manifest["files"]
    assert isinstance(files, list)
    file_entries = {entry["database_role"]: entry for entry in files}
    assert file_entries["notes"]["archive_name"] == "live.db"
    assert "search_history" not in file_entries

    _write_counter(database_path, 99)
    _write_search_history_marker(search_history_database_path, "exercise")
    assert _read_counter(database_path) == 99
    assert _read_search_history_queries(search_history_database_path) == ["exercise"]

    restore_backup_to_paths(backup_path, database_path)
    assert _read_counter(database_path) == 7
    assert _read_search_history_queries(search_history_database_path) == ["exercise"]


def test_namespaced_backup_directories_do_not_mix_files(tmp_path: Path) -> None:
    cla_database_path = tmp_path / "namespaces" / "cla" / "cla.metalist.db"
    work_database_path = tmp_path / "namespaces" / "work" / "work.metalist.db"
    cla_backup_directory = resolve_backup_directory_for_database(cla_database_path)
    work_backup_directory = resolve_backup_directory_for_database(work_database_path)

    _write_counter(cla_database_path, 11)
    _write_counter(work_database_path, 22)

    cla_backup = create_timestamped_backup_for_paths(cla_database_path, cla_backup_directory)
    work_backup = create_timestamped_backup_for_paths(work_database_path, work_backup_directory)

    cla_backups = list_backups_in_directory(cla_backup_directory, database_path=None)
    work_backups = list_backups_in_directory(work_backup_directory, database_path=None)

    assert [entry.filename for entry in cla_backups] == [cla_backup.filename]
    assert [entry.filename for entry in work_backups] == [work_backup.filename]
    assert cla_backup_directory != work_backup_directory


def test_list_backups_returns_newest_first_for_archive_backups(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    older = backup_directory / "default-20260101-000000-000001.metalist-backup.tar.gz"
    newer = backup_directory / "default-20260101-000000-000002.metalist-backup.tar.gz"
    ignored = backup_directory / "ignore-me.txt"

    older.write_bytes(b"older")
    newer.write_bytes(b"newer")
    ignored.write_text("ignored", encoding="utf-8")

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    backup_list = list_backups_in_directory(backup_directory, database_path=None)
    assert [entry.filename for entry in backup_list] == [newer.name, older.name]


def test_delete_oldest_backups_removes_oldest_first_for_archive_backups(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    database_path = tmp_path / "namespaces" / "default" / "default.metalist.db"
    oldest = backup_directory / "default-20260101-000000-000001.metalist-backup.tar.gz"
    middle = backup_directory / "default-20260101-000000-000002.metalist-backup.tar.gz"
    newest = backup_directory / "default-20260101-000000-000003.metalist-backup.tar.gz"

    oldest.write_bytes(b"oldest")
    middle.write_bytes(b"middle")
    newest.write_bytes(b"newest")

    os.utime(oldest, (1_700_000_000, 1_700_000_000))
    os.utime(middle, (1_700_000_050, 1_700_000_050))
    os.utime(newest, (1_700_000_100, 1_700_000_100))

    deleted = delete_oldest_backups_in_directory(backup_directory, 2, database_path=database_path)
    assert [entry.filename for entry in deleted] == [oldest.name, middle.name]

    remaining = list_backups_in_directory(backup_directory, database_path=None)
    assert [entry.filename for entry in remaining] == [newest.name]


def test_delete_oldest_backups_count_larger_than_available_deletes_all_for_archive_backups(
    tmp_path: Path,
) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    database_path = tmp_path / "namespaces" / "default" / "default.metalist.db"
    older = backup_directory / "default-20260101-000000-000001.metalist-backup.tar.gz"
    newer = backup_directory / "default-20260101-000000-000002.metalist-backup.tar.gz"

    older.write_bytes(b"older")
    newer.write_bytes(b"newer")

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    deleted = delete_oldest_backups_in_directory(backup_directory, 10, database_path=database_path)
    assert [entry.filename for entry in deleted] == [older.name, newer.name]

    remaining = list_backups_in_directory(backup_directory, database_path=None)
    assert remaining == []


def test_delete_oldest_backups_removes_matching_legacy_file_sidecars(tmp_path: Path) -> None:
    database_path = tmp_path / "namespaces" / "cla" / "cla.metalist.db"
    backup_directory = tmp_path / "namespaces" / "cla" / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    primary = backup_directory / "20260101-000000-000001.cla.metalist.db.bak"
    sidecar = backup_directory / "20260101-000000-000001.cla.metalist.files.db.bak"

    primary.write_bytes(b"primary")
    sidecar.write_bytes(b"sidecar")

    deleted = delete_oldest_backups_in_directory(backup_directory, 1, database_path=database_path)
    assert [entry.filename for entry in deleted] == [primary.name]
    assert primary.exists() is False
    assert sidecar.exists() is False


def test_delete_oldest_backups_removes_matching_legacy_search_history_sidecars(tmp_path: Path) -> None:
    database_path = tmp_path / "namespaces" / "cla" / "cla.metalist.db"
    backup_directory = tmp_path / "namespaces" / "cla" / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    primary = backup_directory / "20260101-000000-000001.cla.metalist.db.bak"
    sidecar = backup_directory / "20260101-000000-000001.cla.metalist.search-history.db.bak"

    primary.write_bytes(b"primary")
    sidecar.write_bytes(b"sidecar")

    deleted = delete_oldest_backups_in_directory(backup_directory, 1, database_path=database_path)
    assert [entry.filename for entry in deleted] == [primary.name]
    assert primary.exists() is False
    assert sidecar.exists() is False


def test_restore_supports_legacy_backup_format(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    file_database_path = resolve_file_database_path(database_path)
    search_history_database_path = _resolve_legacy_search_history_database_path(database_path)
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    _write_counter(database_path, 7)
    _write_file_marker(file_database_path, "file-a")
    _write_search_history_marker(search_history_database_path, "journal")

    backup_path = backup_directory / "20260101-000000-000001.live.db.bak"
    file_backup_path = backup_directory / "20260101-000000-000001.live.files.db.bak"
    search_history_backup_path = backup_directory / "20260101-000000-000001.live.search-history.db.bak"
    _copy_database_for_fixture(database_path, backup_path)
    _copy_database_for_fixture(file_database_path, file_backup_path)
    _copy_database_for_fixture(search_history_database_path, search_history_backup_path)
    source_hashes = (
        _sha256_for_path(backup_path),
        _sha256_for_path(file_backup_path),
        _sha256_for_path(search_history_backup_path),
    )

    _write_counter(database_path, 99)
    _write_file_marker(file_database_path, "file-b")
    _write_search_history_marker(search_history_database_path, "exercise")

    restore_backup_to_paths(backup_path, database_path)
    assert _read_counter(database_path) == 7
    assert _read_file_ids(file_database_path) == ["file-a"]
    assert _read_search_history_queries(search_history_database_path) == ["exercise"]
    assert (
        _sha256_for_path(backup_path),
        _sha256_for_path(file_backup_path),
        _sha256_for_path(search_history_backup_path),
    ) == source_hashes


def test_restore_rejects_unsupported_future_archive_format_before_writing(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    backup_directory = tmp_path / "backups"
    backup_path = backup_directory / "live-20260101-000000-000001.metalist-backup.tar.gz"
    snapshot_path = tmp_path / "snapshot-live.db"

    _write_counter(database_path, 7)
    _copy_database_for_fixture(database_path, snapshot_path)

    manifest = {
        "backup_format_version": 999,
        "manifest_schema_version": 1,
        "namespace": "live",
        "created_at": "2026-04-19T00:00:00+00:00",
        "encryption_enabled": False,
        "files": [
            {
                "archive_name": "live.db",
                "database_role": "notes",
                "size_bytes": snapshot_path.stat().st_size,
                "sha256": _sha256_for_path(snapshot_path),
            }
        ],
    }
    _write_archive_fixture(
        backup_path,
        manifest=manifest,
        archive_files={"live.db": snapshot_path},
    )

    _write_counter(database_path, 99)
    assert _read_counter(database_path) == 99

    with pytest.raises(RuntimeError, match="Unsupported backup format version"):
        restore_backup_to_paths(backup_path, database_path)

    assert _read_counter(database_path) == 99
