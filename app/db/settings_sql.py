"""SQL helpers for the app_settings table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from .engine import GuardedConnection
from .schema import app_settings_table


def _conn(connection: GuardedConnection | Connection) -> Connection:
    return connection.raw_connection if isinstance(connection, GuardedConnection) else connection


def fetch_settings(connection: GuardedConnection | Connection) -> Optional[dict]:
    stmt = select(app_settings_table).where(app_settings_table.c.id == 1)
    row = _conn(connection).execute(stmt).mappings().first()
    return dict(row) if row else None


def insert_default_settings(connection: GuardedConnection | Connection) -> None:
    now = datetime.now(timezone.utc)
    stmt = insert(app_settings_table).values(
        id=1,
        encryption_enabled=False,
        created_at=now,
        updated_at=now,
    )
    _conn(connection).execute(stmt)


def update_password_settings(
    connection: GuardedConnection | Connection,
    *,
    password_hash: bytes,
    password_salt: bytes,
    password_iterations: int,
    encrypted_dek: bytes,
    dek_nonce: bytes,
    dek_tag: bytes,
    encryption_algorithm: str,
) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        update(app_settings_table)
        .where(app_settings_table.c.id == 1)
        .values(
            password_hash=password_hash,
            password_salt=password_salt,
            password_iterations=password_iterations,
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            dek_tag=dek_tag,
            encryption_enabled=True,
            encryption_algorithm=encryption_algorithm,
            updated_at=now,
        )
    )
    _conn(connection).execute(stmt)
