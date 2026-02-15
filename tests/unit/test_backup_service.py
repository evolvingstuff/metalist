from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from app.services.backup_service import (
    create_timestamped_backup_for_paths,
    delete_oldest_backups_in_directory,
    list_backups_in_directory,
    restore_backup_to_paths,
)


def _write_counter(database_path: Path, counter: int) -> None:
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


def test_list_backups_returns_newest_first(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    older = backup_directory / "metalist-backup-20260101-000000-000001.db"
    newer = backup_directory / "metalist-backup-20260101-000000-000002.db"
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

    oldest = backup_directory / "metalist-backup-20260101-000000-000001.db"
    middle = backup_directory / "metalist-backup-20260101-000000-000002.db"
    newest = backup_directory / "metalist-backup-20260101-000000-000003.db"

    oldest.write_bytes(b"oldest")
    middle.write_bytes(b"middle")
    newest.write_bytes(b"newest")

    os.utime(oldest, (1_700_000_000, 1_700_000_000))
    os.utime(middle, (1_700_000_050, 1_700_000_050))
    os.utime(newest, (1_700_000_100, 1_700_000_100))

    deleted = delete_oldest_backups_in_directory(backup_directory, 2)
    assert [entry.filename for entry in deleted] == [oldest.name, middle.name]

    remaining = list_backups_in_directory(backup_directory)
    assert [entry.filename for entry in remaining] == [newest.name]


def test_delete_oldest_backups_count_larger_than_available_deletes_all(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    older = backup_directory / "metalist-backup-20260101-000000-000001.db"
    newer = backup_directory / "metalist-backup-20260101-000000-000002.db"

    older.write_bytes(b"older")
    newer.write_bytes(b"newer")

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    deleted = delete_oldest_backups_in_directory(backup_directory, 10)
    assert [entry.filename for entry in deleted] == [older.name, newer.name]

    remaining = list_backups_in_directory(backup_directory)
    assert remaining == []
