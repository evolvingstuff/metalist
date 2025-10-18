"""Composable SQL helpers for the notes table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Select

from .engine import GuardedConnection
from .schema import notes_table


def _conn(connection: GuardedConnection | Connection) -> Connection:
    return connection.raw_connection if isinstance(connection, GuardedConnection) else connection


def insert_note(
    connection: GuardedConnection | Connection,
    *,
    note_id: str,
    content: str,
    encryption_nonce: Optional[bytes],
    encryption_tag: Optional[bytes],
    parent_id: Optional[str],
    prev_id: Optional[str],
    next_id: Optional[str],
    is_collapsed: bool = False,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        insert(notes_table)
        .values(
            id=note_id,
            content=content,
            encryption_nonce=encryption_nonce,
            encryption_tag=encryption_tag,
            parent_id=parent_id,
            prev_id=prev_id,
            next_id=next_id,
            is_collapsed=is_collapsed,
            created_at=created_at or now,
            updated_at=updated_at or now,
        )
    )
    _conn(connection).execute(stmt)


def update_note_content(
    connection: GuardedConnection | Connection,
    note_id: str,
    *,
    content: str,
    encryption_nonce: Optional[bytes],
    encryption_tag: Optional[bytes],
    updated_at: Optional[datetime] = None,
) -> None:
    stmt = (
        update(notes_table)
        .where(notes_table.c.id == note_id)
        .values(
            content=content,
            encryption_nonce=encryption_nonce,
            encryption_tag=encryption_tag,
            updated_at=updated_at or datetime.now(timezone.utc),
        )
    )
    _conn(connection).execute(stmt)


_UNSET = object()


def update_links(
    connection: GuardedConnection | Connection,
    note_id: str,
    *,
    parent_id: Optional[str] = _UNSET,
    prev_id: Optional[str] = _UNSET,
    next_id: Optional[str] = _UNSET,
    is_collapsed: Optional[bool] = _UNSET,
    updated_at: Optional[datetime] = None,
) -> None:
    values = {
        "updated_at": updated_at or datetime.now(timezone.utc),
    }
    if parent_id is not _UNSET:
        values["parent_id"] = parent_id
    if prev_id is not _UNSET:
        values["prev_id"] = prev_id
    if next_id is not _UNSET:
        values["next_id"] = next_id
    if is_collapsed is not _UNSET:
        values["is_collapsed"] = is_collapsed

    stmt = update(notes_table).where(notes_table.c.id == note_id).values(**values)
    _conn(connection).execute(stmt)


def delete_notes(
    connection: GuardedConnection | Connection,
    note_ids: Iterable[str],
) -> None:
    identifiers = list(note_ids)
    if not identifiers:
        return
    stmt = delete(notes_table).where(notes_table.c.id.in_(identifiers))
    _conn(connection).execute(stmt)


def fetch_note(
    connection: GuardedConnection | Connection,
    note_id: str,
) -> Optional[dict]:
    stmt = select(notes_table).where(notes_table.c.id == note_id)
    result = _conn(connection).execute(stmt).mappings().first()
    return dict(result) if result else None


def fetch_children_ordered(
    connection: GuardedConnection | Connection,
    parent_id: Optional[str],
) -> list[dict]:
    stmt: Select
    if parent_id is None:
        stmt = select(notes_table).where(notes_table.c.parent_id.is_(None))
    else:
        stmt = select(notes_table).where(notes_table.c.parent_id == parent_id)

    rows = _conn(connection).execute(stmt).mappings().all()
    if not rows:
        return []

    # Preserve linked-list ordering by chasing prev pointers.
    by_id = {row["id"]: dict(row) for row in rows}
    head = next((row for row in rows if row["prev_id"] is None), None)
    if not head:
        return list(by_id.values())

    ordered: list[dict] = []
    current = dict(head)
    seen: set[str] = set()
    while current["id"] not in seen:
        ordered.append(current)
        seen.add(current["id"])
        next_id = current.get("next_id")
        if next_id is None:
            break
        next_row = by_id.get(next_id)
        if not next_row:
            break
        current = next_row
    return ordered


def fetch_all_for_cache(connection: GuardedConnection | Connection) -> list[dict]:
    stmt = select(notes_table)
    rows = _conn(connection).execute(stmt).mappings().all()
    return [dict(row) for row in rows]
