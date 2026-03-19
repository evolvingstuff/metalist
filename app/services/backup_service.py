from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from threading import Lock

from app.db.file_schema import initialize_file_schema
from app.db.file_session import resolve_file_database_path
from app.db.search_history_schema import initialize_search_history_schema
from app.db.search_history_session import resolve_search_history_database_path
from app.models.database import SafeSession


_BACKUP_LOCK = Lock()
_PRIMARY_BACKUP_FILENAME_RE = re.compile(
    r"^(?P<timestamp>[0-9]{8}-[0-9]{6}-[0-9]{6})\.(?P<database_name>.+)\.bak$"
)


@dataclass(frozen=True)
class BackupFileInfo:
    filename: str
    created_at: str
    size_bytes: int


def _format_backup_filename(*, database_path: Path, now_utc: datetime) -> str:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    if not isinstance(database_path, Path):
        raise TypeError(f"database_path must be a Path, got {type(database_path)}")
    timestamp = now_utc.strftime("%Y%m%d-%H%M%S-%f")
    return f"{timestamp}.{database_path.name}.bak"


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


def _match_primary_backup_filename(filename: str) -> re.Match[str] | None:
    match = _PRIMARY_BACKUP_FILENAME_RE.fullmatch(filename)
    if match is None:
        return None
    database_name = match.group("database_name")
    if (
        not database_name.endswith(".db")
        or database_name.endswith(".files.db")
        or database_name.endswith(".search-history.db")
    ):
        return None
    return match


def _validate_backup_filename(*, filename: str, database_path: Path) -> str:
    if not isinstance(filename, str):
        raise TypeError(f"filename must be a string, got {type(filename)}")
    if not isinstance(database_path, Path):
        raise TypeError(f"database_path must be a Path, got {type(database_path)}")
    if filename == "":
        raise ValueError("filename must be non-empty")
    if Path(filename).name != filename:
        raise ValueError("filename must not contain path separators")

    match = _match_primary_backup_filename(filename)
    if match is None or match.group("database_name") != database_path.name:
        raise ValueError("filename must match the active database backup naming convention")
    return filename


def _derive_file_backup_filename(*, filename: str, database_path: Path) -> str:
    validated_filename = _validate_backup_filename(filename=filename, database_path=database_path)
    match = _match_primary_backup_filename(validated_filename)
    assert match is not None
    database_name = match.group("database_name")
    file_database_name = f"{database_name[:-len('.db')]}.files.db"
    return f"{match.group('timestamp')}.{file_database_name}.bak"


def _derive_any_file_backup_filename(filename: str) -> str:
    match = _match_primary_backup_filename(filename)
    if match is None:
        raise ValueError(f"Unsupported primary backup filename: {filename}")
    database_name = match.group("database_name")
    file_database_name = f"{database_name[:-len('.db')]}.files.db"
    return f"{match.group('timestamp')}.{file_database_name}.bak"


def _derive_search_history_backup_filename(*, filename: str, database_path: Path) -> str:
    validated_filename = _validate_backup_filename(filename=filename, database_path=database_path)
    match = _match_primary_backup_filename(validated_filename)
    assert match is not None
    database_name = match.group("database_name")
    search_history_database_name = f"{database_name[:-len('.db')]}.search-history.db"
    return f"{match.group('timestamp')}.{search_history_database_name}.bak"


def _derive_any_search_history_backup_filename(filename: str) -> str:
    match = _match_primary_backup_filename(filename)
    if match is None:
        raise ValueError(f"Unsupported primary backup filename: {filename}")
    database_name = match.group("database_name")
    search_history_database_name = f"{database_name[:-len('.db')]}.search-history.db"
    return f"{match.group('timestamp')}.{search_history_database_name}.bak"


def _resolve_related_file_database_path(database_path: Path) -> Path:
    return resolve_file_database_path(database_path)


def _resolve_related_search_history_database_path(database_path: Path) -> Path:
    return resolve_search_history_database_path(database_path)


def _resolve_related_file_backup_path(
    backup_directory: Path,
    filename: str,
    *,
    database_path: Path,
) -> Path:
    return backup_directory / _derive_file_backup_filename(filename=filename, database_path=database_path)


def _resolve_related_search_history_backup_path(
    backup_directory: Path,
    filename: str,
    *,
    database_path: Path,
) -> Path:
    return backup_directory / _derive_search_history_backup_filename(
        filename=filename,
        database_path=database_path,
    )


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


def _reset_search_history_database_to_empty(search_history_database_path: Path) -> None:
    search_history_database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(search_history_database_path), check_same_thread=False)
    try:
        initialize_search_history_schema(connection)
        connection.execute("DELETE FROM search_interaction_history")
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


def list_backups_in_directory(
    backup_directory: Path,
    *,
    database_path: Path | None,
) -> list[BackupFileInfo]:
    if not isinstance(backup_directory, Path):
        raise TypeError(f"backup_directory must be a Path, got {type(backup_directory)}")
    if not backup_directory.exists():
        return []
    if not backup_directory.is_dir():
        raise ValueError(f"backup_directory is not a directory: {backup_directory}")

    candidates = list(backup_directory.iterdir())
    candidates.sort(key=lambda candidate: candidate.stat().st_mtime, reverse=True)

    entries: list[BackupFileInfo] = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        match = _match_primary_backup_filename(candidate.name)
        if match is None:
            continue
        if database_path is not None and match.group("database_name") != database_path.name:
            continue
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
        now_utc = datetime.now(timezone.utc)
        filename = _format_backup_filename(database_path=database_path, now_utc=now_utc)
        backup_path = backup_directory / filename
        if backup_path.exists():
            raise FileExistsError(f"Backup already exists: {backup_path}")

        _copy_database(database_path, backup_path)

        related_file_database_path = _resolve_related_file_database_path(database_path)
        if related_file_database_path.exists():
            if not related_file_database_path.is_file():
                raise ValueError(f"Related file database path is not a file: {related_file_database_path}")
            related_file_backup_filename = _format_backup_filename(
                database_path=related_file_database_path,
                now_utc=now_utc,
            )
            related_file_backup_path = backup_directory / related_file_backup_filename
            if related_file_backup_path.exists():
                raise FileExistsError(f"Backup already exists: {related_file_backup_path}")
            _copy_database(related_file_database_path, related_file_backup_path)

        related_search_history_database_path = _resolve_related_search_history_database_path(database_path)
        if related_search_history_database_path.exists():
            if not related_search_history_database_path.is_file():
                raise ValueError(
                    "Related search history database path is not a file: "
                    f"{related_search_history_database_path}"
                )
            related_search_history_backup_filename = _format_backup_filename(
                database_path=related_search_history_database_path,
                now_utc=now_utc,
            )
            related_search_history_backup_path = backup_directory / related_search_history_backup_filename
            if related_search_history_backup_path.exists():
                raise FileExistsError(f"Backup already exists: {related_search_history_backup_path}")
            _copy_database(related_search_history_database_path, related_search_history_backup_path)

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
        related_file_backup_path = _resolve_related_file_backup_path(
            backup_path.parent,
            backup_path.name,
            database_path=database_path,
        )
        if related_file_backup_path.exists():
            _copy_database(related_file_backup_path, related_file_database_path)
            file_target_connection = sqlite3.connect(str(related_file_database_path), check_same_thread=False)
            try:
                file_target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                file_target_connection.close()
        else:
            _reset_file_database_to_empty(related_file_database_path)

        related_search_history_database_path = _resolve_related_search_history_database_path(database_path)
        related_search_history_backup_path = _resolve_related_search_history_backup_path(
            backup_path.parent,
            backup_path.name,
            database_path=database_path,
        )
        if related_search_history_backup_path.exists():
            _copy_database(related_search_history_backup_path, related_search_history_database_path)
            search_history_target_connection = sqlite3.connect(
                str(related_search_history_database_path),
                check_same_thread=False,
            )
            try:
                search_history_target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                search_history_target_connection.close()
        else:
            _reset_search_history_database_to_empty(related_search_history_database_path)


def create_timestamped_backup() -> BackupFileInfo:
    database_path = resolve_live_database_path()
    backup_directory = resolve_backup_directory_for_database(database_path)
    return create_timestamped_backup_for_paths(database_path, backup_directory)


def list_backups() -> list[BackupFileInfo]:
    database_path = resolve_live_database_path()
    backup_directory = resolve_backup_directory_for_database(database_path)
    return list_backups_in_directory(backup_directory, database_path=database_path)


def delete_oldest_backups_in_directory(
    backup_directory: Path,
    count: int,
    *,
    database_path: Path | None,
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
        backups_newest_first = list_backups_in_directory(backup_directory, database_path=database_path)
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

            if database_path is None:
                related_file_backup_filename = _derive_any_file_backup_filename(backup.filename)
            else:
                related_file_backup_filename = _derive_file_backup_filename(
                    filename=backup.filename,
                    database_path=database_path,
                )
            related_file_backup_path = backup_directory / related_file_backup_filename
            if related_file_backup_path.exists():
                if not related_file_backup_path.is_file():
                    raise ValueError(f"Backup path is not a file: {related_file_backup_path}")
                related_file_backup_path.unlink()

            if database_path is None:
                related_search_history_backup_filename = _derive_any_search_history_backup_filename(
                    backup.filename
                )
            else:
                related_search_history_backup_filename = _derive_search_history_backup_filename(
                    filename=backup.filename,
                    database_path=database_path,
                )
            related_search_history_backup_path = backup_directory / related_search_history_backup_filename
            if related_search_history_backup_path.exists():
                if not related_search_history_backup_path.is_file():
                    raise ValueError(f"Backup path is not a file: {related_search_history_backup_path}")
                related_search_history_backup_path.unlink()

            deleted_backups.append(backup)

        return deleted_backups


def delete_oldest_backups(count: int) -> list[BackupFileInfo]:
    database_path = resolve_live_database_path()
    backup_directory = resolve_backup_directory_for_database(database_path)
    return delete_oldest_backups_in_directory(
        backup_directory,
        count,
        database_path=database_path,
    )


def resolve_backup_path_by_filename(filename: str) -> Path:
    database_path = resolve_live_database_path()
    validated_filename = _validate_backup_filename(filename=filename, database_path=database_path)
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
