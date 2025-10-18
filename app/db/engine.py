"""Guard-aware connection helpers built on SQLAlchemy Core.

These utilities reuse the existing SafeSession guard while providing a
connection-centric API that future services can depend on without
pulling in the ORM Session machinery.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy.engine import Connection, Engine

from app.models.database import SafeSession, _is_select


class GuardedConnection:
    """Lightweight wrapper that enforces the post-startup read guard."""

    __slots__ = ("_connection",)

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def execute(self, statement, *args, **kwargs):  # type: ignore[override]
        if not SafeSession._reads_enabled and _is_select(statement):  # type: ignore[attr-defined]
            raise RuntimeError("Post-startup DB read forbidden")
        return self._connection.execute(statement, *args, **kwargs)

    def scalar(self, statement, *args, **kwargs):  # type: ignore[override]
        if not SafeSession._reads_enabled and _is_select(statement):  # type: ignore[attr-defined]
            raise RuntimeError("Post-startup DB read forbidden")
        return self._connection.scalar(statement, *args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._connection, item)

    @property
    def raw_connection(self) -> Connection:
        return self._connection


def get_engine() -> Engine:
    """Expose the current engine (file or memory) managed by SafeSession."""

    return SafeSession.get_engine()


def enable_read_guard() -> None:
    SafeSession.enable_read_guard()


def disable_read_guard() -> None:
    SafeSession.disable_read_guard()


@contextmanager
def allow_reads(reason: str = ""):
    with SafeSession.allow_reads(reason):
        yield


@contextmanager
def begin_writer() -> Iterator[GuardedConnection]:
    """Open a transactional connection for write operations."""

    with get_engine().begin() as connection:
        yield GuardedConnection(connection)


@contextmanager
def connect_reader(reason: Optional[str] = None) -> Iterator[GuardedConnection]:
    """Open a guard-aware connection for read operations."""

    ctx = allow_reads(reason or "reader")
    with ctx:
        connection = get_engine().connect()
        try:
            yield GuardedConnection(connection)
        finally:
            connection.close()
