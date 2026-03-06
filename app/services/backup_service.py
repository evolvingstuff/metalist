from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from threading import Lock

from app.models.database import SafeSession
from app.db.file_schema import initialize_file_schema
from app.db.file_session import resolve_file_database_path


_BACKUP_LOCK = Lock()
_BACKUP_FILENAME_RE = re.compile(r"^metalist-backup-[0-9]{8}-[0-9]{6}-[0-9]{6}\.db$")


@dataclass(frozen=True)
class BackupFileInfo:
    filename: str
    created_at: str
    size_bytes: int


def _format_backup_filename(now_utc: datetime) -> str:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    return now_utc.strftime("metalist-backup-%Y%m%d-%H%M%S-%f.db")


def _stat_to_backup_info(path: Path) -> BackupFileInfo:
    if not path.exists():
        raise FileNotFoundError(f"Backup file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Backup path is not a file: {path}")

    stat_result = path.stat()
    created_at = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat()
    return BackupFileInfo(
        filename=path.name,
        created_at=created_at,
        size_bytes=stat_result.st_size,
    )


def _validate_backup_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise TypeError(f"filename must be a string, got {type(filename)}")
    if filename == "":
        raise ValueError("filename must be non-empty")
    if Path(filename).name != filename:
        raise ValueError("filename must not contain path separators")
    if _BACKUP_FILENAME_RE.match(filename) is None:
        raise ValueError(
            "filename must match metalist-backup-YYYYMMDD-HHMMSS-ffffff.db"
        )
    return filename


def _derive_file_backup_filename(filename: str) -> str:
    validated_filename = _validate_backup_filename(filename)
    return validated_filename.replace("metalist-backup-", "metalist-files-backup-", 1)


def _resolve_related_file_database_path(database_path: Path) -> Path:
    return resolve_file_database_path(database_path)


def _resolve_related_file_backup_path(backup_directory: Path, filename: str) -> Path:
    return backup_directory / _derive_file_backup_filename(filename)


def _copy_database(source_path: Path, target_path: Path) -> None:
    source_connection = sqlite3.connect(str(source_path), check_same_thread=False)
    target_connection = sqlite3.connect(str(target_path), check_same_thread=False)
    try:
        source_connection.execute("PRAGMA wal_checkpoint(FULL)")
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()


def _reset_file_database_to_empty(file_database_path: Path) -> None:
    file_database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(file_database_path), check_same_thread=False)
    try:
        initialize_file_schema(connection)
        connection.execute("DELETE FROM files")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()


def resolve_live_database_path() -> Path:
    if SafeSession._use_memory:  # type: ignore[attr-defined]
        raise RuntimeError("Backups are unavailable when using the in-memory database")

    db_path = SafeSession._db_path  # type: ignore[attr-defined]
    if not isinstance(db_path, Path):
        raise TypeError(f"SafeSession._db_path must be a Path, got {type(db_path)}")
    return db_path


def resolve_backup_directory_for_database(database_path: Path) -> Path:
    if not isinstance(database_path, Path):
        raise TypeError(f"database_path must be a Path, got {type(database_path)}")
    if database_path.name == "":
        raise ValueError("database_path must be a file path")
    return database_path.parent / "backups"


def list_backups_in_directory(backup_directory: Path) -> list[BackupFileInfo]:
    if not isinstance(backup_directory, Path):
        raise TypeError(f"backup_directory must be a Path, got {type(backup_directory)}")
    if not backup_directory.exists():
        return []
    if not backup_directory.is_dir():
        raise ValueError(f"backup_directory is not a directory: {backup_directory}")

    candidates = list(backup_directory.glob("metalist-backup-*.db"))
    candidates.sort(key=lambda candidate: candidate.stat().st_mtime, reverse=True)

    entries = []
    for candidate in candidates:
        entries.append(_stat_to_backup_info(candidate))
    return entries


def create_timestamped_backup_for_paths(
    database_path: Path,
    backup_directory: Path,
) -> BackupFileInfo:
    if not isinstance(database_path, Path):
        raise TypeError(f"database_path must be a Path, got {type(database_path)}")
    if not isinstance(backup_directory, Path):
        raise TypeError(f"backup_directory must be a Path, got {type(backup_directory)}")
    if not database_path.exists():
        raise FileNotFoundError(f"Database file not found: {database_path}")
    if not database_path.is_file():
        raise ValueError(f"Database path is not a file: {database_path}")

    backup_directory.mkdir(parents=True, exist_ok=True)

    with _BACKUP_LOCK:
        filename = _format_backup_filename(datetime.now(timezone.utc))
        backup_path = backup_directory / filename
        if backup_path.exists():
            raise FileExistsError(f"Backup already exists: {backup_path}")

        _copy_database(database_path, backup_path)

        related_file_database_path = _resolve_related_file_database_path(database_path)
        if related_file_database_path.exists():
            if not related_file_database_path.is_file():
                raise ValueError(f"Related file database path is not a file: {related_file_database_path}")
            related_file_backup_path = _resolve_related_file_backup_path(backup_directory, filename)
            if related_file_backup_path.exists():
                raise FileExistsError(f"Backup already exists: {related_file_backup_path}")
            _copy_database(related_file_database_path, related_file_backup_path)

    return _stat_to_backup_info(backup_path)


def restore_backup_to_paths(backup_path: Path, database_path: Path) -> None:
    if not isinstance(backup_path, Path):
        raise TypeError(f"backup_path must be a Path, got {type(backup_path)}")
    if not isinstance(database_path, Path):
        raise TypeError(f"database_path must be a Path, got {type(database_path)}")
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    if not backup_path.is_file():
        raise ValueError(f"Backup path is not a file: {backup_path}")

    database_path.parent.mkdir(parents=True, exist_ok=True)

    with _BACKUP_LOCK:
        _copy_database(backup_path, database_path)
        target_connection = sqlite3.connect(str(database_path), check_same_thread=False)
        try:
            target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            target_connection.close()

        related_file_database_path = _resolve_related_file_database_path(database_path)
        related_file_backup_path = _resolve_related_file_backup_path(backup_path.parent, backup_path.name)
        if related_file_backup_path.exists():
            _copy_database(related_file_backup_path, related_file_database_path)
            file_target_connection = sqlite3.connect(str(related_file_database_path), check_same_thread=False)
            try:
                file_target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                file_target_connection.close()
        else:
            _reset_file_database_to_empty(related_file_database_path)


def create_timestamped_backup() -> BackupFileInfo:
    database_path = resolve_live_database_path()
    backup_directory = resolve_backup_directory_for_database(database_path)
    return create_timestamped_backup_for_paths(database_path, backup_directory)


def list_backups() -> list[BackupFileInfo]:
    database_path = resolve_live_database_path()
    backup_directory = resolve_backup_directory_for_database(database_path)
    return list_backups_in_directory(backup_directory)


def delete_oldest_backups_in_directory(
    backup_directory: Path,
    count: int,
) -> list[BackupFileInfo]:
    if not isinstance(backup_directory, Path):
        raise TypeError(f"backup_directory must be a Path, got {type(backup_directory)}")
    if not isinstance(count, int):
        raise TypeError(f"count must be an int, got {type(count)}")
    if count <= 0:
        raise ValueError("count must be greater than zero")
    if not backup_directory.exists():
        return []
    if not backup_directory.is_dir():
        raise ValueError(f"backup_directory is not a directory: {backup_directory}")

    with _BACKUP_LOCK:
        backups_newest_first = list_backups_in_directory(backup_directory)
        backups_oldest_first = list(reversed(backups_newest_first))
        backups_to_delete = backups_oldest_first[:count]
        deleted_backups: list[BackupFileInfo] = []

        for backup in backups_to_delete:
            backup_path = backup_directory / backup.filename
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            if not backup_path.is_file():
                raise ValueError(f"Backup path is not a file: {backup_path}")
            backup_path.unlink()

            related_file_backup_path = _resolve_related_file_backup_path(backup_directory, backup.filename)
            if related_file_backup_path.exists():
                if not related_file_backup_path.is_file():
                    raise ValueError(f"Backup path is not a file: {related_file_backup_path}")
                related_file_backup_path.unlink()

            deleted_backups.append(backup)

        return deleted_backups


def delete_oldest_backups(count: int) -> list[BackupFileInfo]:
    database_path = resolve_live_database_path()
    backup_directory = resolve_backup_directory_for_database(database_path)
    return delete_oldest_backups_in_directory(backup_directory, count)


def resolve_backup_path_by_filename(filename: str) -> Path:
    validated_filename = _validate_backup_filename(filename)
    database_path = resolve_live_database_path()
    backup_directory = resolve_backup_directory_for_database(database_path)
    backup_path = backup_directory / validated_filename
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {validated_filename}")
    return backup_path


def restore_backup(filename: str) -> BackupFileInfo:
    backup_path = resolve_backup_path_by_filename(filename)
    database_path = resolve_live_database_path()
    restore_backup_to_paths(backup_path, database_path)
    return _stat_to_backup_info(backup_path)
