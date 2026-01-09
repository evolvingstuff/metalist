"""Canonical DB session and guard helpers.

This module centralizes access to the sqlite connection via SafeSession and
exposes thin helpers used across the app (writers/readers + read guard).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from app.models.database import SafeSession


def _is_select(statement: str) -> bool:
    return statement.lstrip().lower().startswith("select")


class GuardedConnection:
    """Lightweight wrapper enforcing the post-startup read guard."""

    __slots__ = ("_connection",)

    def __init__(self, connection) -> None:
        self._connection = connection

    def execute(self, statement: str, parameters: Optional[tuple] = None):
        if not SafeSession._reads_enabled and _is_select(statement):  # type: ignore[attr-defined]
            raise RuntimeError("Post-startup DB read forbidden")
        if parameters is None:
            return self._connection.execute(statement)
        return self._connection.execute(statement, parameters)

    def executemany(self, statement: str, seq_of_parameters):  # pragma: no cover - thin wrapper
        if not SafeSession._reads_enabled and _is_select(statement):  # type: ignore[attr-defined]
            raise RuntimeError("Post-startup DB read forbidden")
        return self._connection.executemany(statement, seq_of_parameters)

    def __getattr__(self, item):
        return getattr(self._connection, item)

    @property
    def raw_connection(self):
        return self._connection


def enable_read_guard() -> None:
    SafeSession.enable_read_guard()


def disable_read_guard() -> None:
    SafeSession.disable_read_guard()


@contextmanager
def allow_reads(reason: str) -> Iterator[None]:
    with SafeSession.allow_reads(reason):
        yield


@contextmanager
def begin_writer() -> Iterator[GuardedConnection]:
    session = SafeSession()
    connection = session.connection()
    guard = GuardedConnection(connection)
    try:
        yield guard
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def connect_reader(reason: Optional[str]) -> Iterator[GuardedConnection]:
    with SafeSession.allow_reads(reason or "reader"):
        session = SafeSession()
        connection = session.connection()
        guard = GuardedConnection(connection)
        try:
            yield guard
        finally:
            session.close()

