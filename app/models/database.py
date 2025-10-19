from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Iterator, Optional

from app.core.config import DATABASE_URL
from app.db.schema import initialize_schema

_MEMORY_URI = "file:metalist_memory?mode=memory&cache=shared"


def _resolve_db_path(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise ValueError(f"Unsupported DATABASE_URL: {url}")
    raw_path = url.replace("sqlite:///", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _is_select(statement: str) -> bool:
    snippet = statement.lstrip().lower()
    return snippet.startswith("select")


class SafeSession:
    _db_path = _resolve_db_path(DATABASE_URL)
    _read_guard_lock = RLock()
    _reads_enabled = True
    _use_memory = False
    _memory_anchor: Optional[sqlite3.Connection] = None

    def __init__(self) -> None:
        self._connection = self._create_connection()
        self._closed = False

    @classmethod
    def _create_connection(cls) -> sqlite3.Connection:
        if cls._use_memory:
            conn = sqlite3.connect(
                _MEMORY_URI,
                uri=True,
                check_same_thread=False,
                isolation_level="DEFERRED",
            )
        else:
            cls._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(cls._db_path),
                check_same_thread=False,
                isolation_level="DEFERRED",
            )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        initialize_schema(conn)
        conn.commit()
        return conn

    @classmethod
    def use_memory_db(cls):
        if cls._memory_anchor:
            cls._memory_anchor.close()
            cls._memory_anchor = None
        cls._use_memory = True
        anchor = sqlite3.connect(
            _MEMORY_URI,
            uri=True,
            check_same_thread=False,
            isolation_level="DEFERRED",
        )
        anchor.row_factory = sqlite3.Row
        anchor.execute("PRAGMA foreign_keys = ON")
        initialize_schema(anchor)
        anchor.commit()
        cls._memory_anchor = anchor
        print("\n" + "=" * 50)
        print(
            """
🧪 SWITCHING TO TEST MODE 🧪
┌──────────────────────────┐
│   IN-MEMORY DATABASE     │
│  *All Data is Temporary  │
└──────────────────────────┘
        """
        )
        print("=" * 50 + "\n")
        return {"status": "ok", "message": "Using in-memory database"}

    @classmethod
    def use_file_db(cls):
        cls._use_memory = False
        if cls._memory_anchor:
            cls._memory_anchor.close()
            cls._memory_anchor = None
        cls._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(cls._db_path),
            check_same_thread=False,
            isolation_level="DEFERRED",
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        initialize_schema(conn)
        conn.commit()
        conn.close()
        print("\n" + "=" * 50)
        print(
            """
📝 RETURNING TO PRODUCTION MODE 📝
┌──────────────────────────┐
│      PROD DATABASE       │
│                          │
└──────────────────────────┘
        """
        )
        print("=" * 50 + "\n")
        return {"status": "ok", "message": "Using file database"}

    @classmethod
    def enable_read_guard(cls) -> None:
        with cls._read_guard_lock:
            cls._reads_enabled = False

    @classmethod
    def disable_read_guard(cls) -> None:
        with cls._read_guard_lock:
            cls._reads_enabled = True

    @classmethod
    @contextmanager
    def allow_reads(cls, reason: str = "") -> Iterator[None]:
        with cls._read_guard_lock:
            previous = cls._reads_enabled
            cls._reads_enabled = True
        try:
            yield
        finally:
            with cls._read_guard_lock:
                cls._reads_enabled = previous

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def execute(self, statement: str, parameters: Optional[tuple] = None):
        if not type(self)._reads_enabled and _is_select(statement):
            raise RuntimeError("Post-startup DB read forbidden")
        if parameters is None:
            return self._connection.execute(statement)
        return self._connection.execute(statement, parameters)

    def connection(self) -> sqlite3.Connection:
        return self._connection

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True


def SessionLocal(*_args, **_kwargs) -> SafeSession:
    """Backwards compatible factory returning a new SafeSession."""

    return SafeSession()


@dataclass
class DBNote:
    id: str
    content: str
    parent_id: Optional[str] = None
    prev_id: Optional[str] = None
    next_id: Optional[str] = None
    is_collapsed: bool = False
    encryption_nonce: Optional[bytes] = None
    encryption_tag: Optional[bytes] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AppSettings:
    id: int = 1
    password_hash: Optional[str] = None
    password_salt: Optional[bytes] = None
    password_iterations: Optional[int] = None
    encryption_enabled: bool = False
    encryption_algorithm: Optional[str] = None
    encrypted_dek: Optional[bytes] = None
    dek_nonce: Optional[bytes] = None
    dek_tag: Optional[bytes] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


__all__ = ["SafeSession", "SessionLocal", "DBNote", "AppSettings"]
