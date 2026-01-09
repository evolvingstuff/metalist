"""Guard-aware sqlite connection helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional, Type

if True:  # pragma: no cover - typing helper
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:  # pragma: no cover
        from app.models.database import SafeSession as _SafeSession


def _safe_session() -> Type["_SafeSession"]:
    from app.models.database import SafeSession  # local import to avoid circular init

    return SafeSession


def _is_select(statement: str) -> bool:
    return statement.lstrip().lower().startswith("select")


class GuardedConnection:
    """Lightweight wrapper enforcing the post-startup read guard."""

    __slots__ = ("_connection",)

    def __init__(self, connection) -> None:
        self._connection = connection

    def execute(self, statement: str, parameters: Optional[tuple] = None):
        SafeSession = _safe_session()
        if not SafeSession._reads_enabled and _is_select(statement):  # type: ignore[attr-defined]
            raise RuntimeError("Post-startup DB read forbidden")
        if parameters is None:
            return self._connection.execute(statement)
        return self._connection.execute(statement, parameters)

    def executemany(self, statement: str, seq_of_parameters):  # pragma: no cover - thin wrapper
        SafeSession = _safe_session()
        if not SafeSession._reads_enabled and _is_select(statement):  # type: ignore[attr-defined]
            raise RuntimeError("Post-startup DB read forbidden")
        return self._connection.executemany(statement, seq_of_parameters)

    def __getattr__(self, item):
        return getattr(self._connection, item)

    @property
    def raw_connection(self):
        return self._connection


def enable_read_guard() -> None:
    _safe_session().enable_read_guard()


def disable_read_guard() -> None:
    _safe_session().disable_read_guard()


@contextmanager
def allow_reads(reason: str) -> Iterator[None]:
    with _safe_session().allow_reads(reason):
        yield


@contextmanager
def begin_writer() -> Iterator[GuardedConnection]:
    SessionCls = _safe_session()
    session = SessionCls()
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
    SessionCls = _safe_session()
    with SessionCls.allow_reads(reason or "reader"):
        session = SessionCls()
        connection = session.connection()
        guard = GuardedConnection(connection)
        try:
            yield guard
        finally:
            session.close()
