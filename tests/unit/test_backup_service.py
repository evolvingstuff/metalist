from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from app.db.file_schema import initialize_file_schema
from app.db.file_session import resolve_file_database_path
from app.services.backup_service import (
    create_timestamped_backup_for_paths,
    delete_oldest_backups_in_directory,
    list_backups_in_directory,
    resolve_backup_directory_for_database,
    restore_backup_to_paths,
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


def test_create_and_restore_backup_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    backup_directory = tmp_path / "backups"

    _write_counter(database_path, 7)
    backup_file = create_timestamped_backup_for_paths(database_path, backup_directory)
    backup_path = backup_directory / backup_file.filename

    _write_counter(database_path, 99)
    assert _read_counter(database_path) == 99

    restore_backup_to_paths(backup_path, database_path)
    assert _read_counter(database_path) == 7


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
    related_file_backup_path = backup_directory / backup_file.filename.replace(".db.bak", ".files.db.bak", 1)

    assert related_file_backup_path.exists()

    _write_counter(database_path, 99)
    _write_file_marker(file_database_path, "file-b")
    assert _read_counter(database_path) == 99
    assert _read_file_ids(file_database_path) == ["file-b"]

    restore_backup_to_paths(backup_path, database_path)
    assert _read_counter(database_path) == 7
    assert _read_file_ids(file_database_path) == ["file-a"]


def test_namespaced_backup_directories_do_not_mix_files(tmp_path: Path) -> None:
    cla_database_path = tmp_path / "namespaces" / "cla" / "cla.metalist.db"
    work_database_path = tmp_path / "namespaces" / "work" / "work.metalist.db"
    cla_backup_directory = resolve_backup_directory_for_database(cla_database_path)
    work_backup_directory = resolve_backup_directory_for_database(work_database_path)

    _write_counter(cla_database_path, 11)
    _write_counter(work_database_path, 22)

    cla_backup = create_timestamped_backup_for_paths(cla_database_path, cla_backup_directory)
    work_backup = create_timestamped_backup_for_paths(work_database_path, work_backup_directory)

    cla_backups = list_backups_in_directory(cla_backup_directory)
    work_backups = list_backups_in_directory(work_backup_directory)

    assert [entry.filename for entry in cla_backups] == [cla_backup.filename]
    assert [entry.filename for entry in work_backups] == [work_backup.filename]
    assert cla_backup_directory != work_backup_directory


def test_list_backups_returns_newest_first(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    older = backup_directory / "20260101-000000-000001.default.metalist.db.bak"
    newer = backup_directory / "20260101-000000-000002.default.metalist.db.bak"
    ignored = backup_directory / "ignore-me.txt"

    older.write_bytes(b"older")
    newer.write_bytes(b"newer")
    ignored.write_text("ignored", encoding="utf-8")

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    backup_list = list_backups_in_directory(backup_directory)
    assert [entry.filename for entry in backup_list] == [newer.name, older.name]


def test_delete_oldest_backups_removes_oldest_first(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    database_path = tmp_path / "namespaces" / "default" / "default.metalist.db"
    oldest = backup_directory / "20260101-000000-000001.default.metalist.db.bak"
    middle = backup_directory / "20260101-000000-000002.default.metalist.db.bak"
    newest = backup_directory / "20260101-000000-000003.default.metalist.db.bak"

    oldest.write_bytes(b"oldest")
    middle.write_bytes(b"middle")
    newest.write_bytes(b"newest")

    os.utime(oldest, (1_700_000_000, 1_700_000_000))
    os.utime(middle, (1_700_000_050, 1_700_000_050))
    os.utime(newest, (1_700_000_100, 1_700_000_100))

    deleted = delete_oldest_backups_in_directory(backup_directory, 2, database_path=database_path)
    assert [entry.filename for entry in deleted] == [oldest.name, middle.name]

    remaining = list_backups_in_directory(backup_directory)
    assert [entry.filename for entry in remaining] == [newest.name]


def test_delete_oldest_backups_count_larger_than_available_deletes_all(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    database_path = tmp_path / "namespaces" / "default" / "default.metalist.db"
    older = backup_directory / "20260101-000000-000001.default.metalist.db.bak"
    newer = backup_directory / "20260101-000000-000002.default.metalist.db.bak"

    older.write_bytes(b"older")
    newer.write_bytes(b"newer")

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    deleted = delete_oldest_backups_in_directory(backup_directory, 10, database_path=database_path)
    assert [entry.filename for entry in deleted] == [older.name, newer.name]

    remaining = list_backups_in_directory(backup_directory)
    assert remaining == []


def test_delete_oldest_backups_removes_matching_file_sidecars(tmp_path: Path) -> None:
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
