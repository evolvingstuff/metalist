"""Dedicated sqlite session helpers for search interaction history storage."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator, Optional

from loguru import logger

from app.db.search_history_schema import initialize_search_history_schema
from app.models.database import SafeSession

def resolve_search_history_database_path(note_database_path: Path) -> Path:
    if not isinstance(note_database_path, Path):
        raise TypeError(f"note_database_path must be a Path, got {type(note_database_path)}")
    suffix = note_database_path.suffix
    stem = note_database_path.stem
    if suffix == "":
        return note_database_path.with_name(f"{stem}.search-history")
    return note_database_path.with_name(f"{stem}.search-history{suffix}")


def _resolve_search_history_memory_uri(note_database_path: Path) -> str:
    if not isinstance(note_database_path, Path):
        raise TypeError(f"note_database_path must be a Path, got {type(note_database_path)}")
    database_key = str(note_database_path).encode("utf-8")
    digest = hashlib.sha256(database_key).hexdigest()
    return f"file:metalist_search_history_memory_{digest}?mode=memory&cache=shared"


class SearchHistorySession:
    _lock = RLock()
    _memory_anchor: Optional[sqlite3.Connection] = None
    _memory_uri: Optional[str] = None
    _use_memory = False

    def __init__(self) -> None:
        self._connection = self._create_connection()
        self._closed = False

    @classmethod
    def _sync_mode_with_notes_db(cls) -> None:
        use_memory = bool(SafeSession._use_memory)  # type: ignore[attr-defined]
        with cls._lock:
            if use_memory:
                cls._use_memory = True
                note_database_path = SafeSession._db_path  # type: ignore[attr-defined]
                if not isinstance(note_database_path, Path):
                    raise TypeError(
                        f"SafeSession._db_path must be a Path, got {type(note_database_path)}"
                    )
                target_memory_uri = _resolve_search_history_memory_uri(note_database_path)
                if cls._memory_anchor is None or cls._memory_uri != target_memory_uri:
                    if cls._memory_anchor is not None:
                        cls._memory_anchor.close()
                    anchor = sqlite3.connect(
                        target_memory_uri,
                        uri=True,
                        check_same_thread=False,
                        isolation_level="DEFERRED",
                    )
                    anchor.row_factory = sqlite3.Row
                    anchor.execute("PRAGMA journal_mode=WAL")
                    anchor.execute("PRAGMA synchronous=NORMAL")
                    initialize_search_history_schema(anchor)
                    anchor.commit()
                    cls._memory_anchor = anchor
                    cls._memory_uri = target_memory_uri
                return

            cls._use_memory = False
            if cls._memory_anchor is not None:
                cls._memory_anchor.close()
                cls._memory_anchor = None
                cls._memory_uri = None

    @classmethod
    def _create_connection(cls) -> sqlite3.Connection:
        cls._sync_mode_with_notes_db()

        if cls._use_memory:
            if cls._memory_uri is None:
                raise RuntimeError("SearchHistorySession._memory_uri must be initialized in memory mode")
            connection = sqlite3.connect(
                cls._memory_uri,
                uri=True,
                check_same_thread=False,
                isolation_level="DEFERRED",
            )
        else:
            database_path = resolve_search_history_database_path(SafeSession._db_path)  # type: ignore[attr-defined]
            database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(database_path),
                check_same_thread=False,
                isolation_level="DEFERRED",
            )

        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        initialize_search_history_schema(connection)
        connection.commit()
        return connection

    def connection(self) -> sqlite3.Connection:
        return self._connection

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()
        stack = "".join(traceback.format_stack(limit=50))
        exc_type, _, _ = sys.exc_info()
        if exc_type is None:
            logger.error(
                "FATAL: search-history DB rollback executed; crashing process",
                extra={"stack": stack},
            )
        else:
            logger.opt(exception=True).error(
                "FATAL: search-history DB rollback executed; crashing process",
                extra={"stack": stack},
            )
        sys.stderr.write("FATAL: search-history DB rollback executed; crashing process\n")
        sys.stderr.flush()
        os._exit(1)

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True


@contextmanager
def begin_search_history_writer() -> Iterator[sqlite3.Connection]:
    session = SearchHistorySession()
    try:
        yield session.connection()
    finally:
        exc_type, _, _ = sys.exc_info()
        if exc_type is None:
            session.commit()
        else:
            session.rollback()
        session.close()


@contextmanager
def connect_search_history_reader() -> Iterator[sqlite3.Connection]:
    session = SearchHistorySession()
    try:
        yield session.connection()
    finally:
        session.close()
