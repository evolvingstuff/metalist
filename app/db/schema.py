"""SQLAlchemy Core metadata used by the helper layer."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
)

metadata = MetaData()

notes_table = Table(
    "notes",
    metadata,
    Column("id", String, primary_key=True),
    Column("content", String, nullable=False),
    Column("is_collapsed", Boolean, nullable=False, default=False),
    Column("encryption_nonce", LargeBinary, nullable=True),
    Column("encryption_tag", LargeBinary, nullable=True),
    Column("parent_id", String, ForeignKey("notes.id"), nullable=True),
    Column("prev_id", String, ForeignKey("notes.id"), nullable=True),
    Column("next_id", String, ForeignKey("notes.id"), nullable=True),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    ),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    ),
)

app_settings_table = Table(
    "app_settings",
    metadata,
    Column("id", Integer, primary_key=True, default=1),
    Column("password_hash", String, nullable=True),
    Column("password_salt", LargeBinary, nullable=True),
    Column("password_iterations", Integer, nullable=True),
    Column("encryption_enabled", Boolean, nullable=False, default=False),
    Column("encryption_algorithm", String, nullable=True),
    Column("encrypted_dek", LargeBinary, nullable=True),
    Column("dek_nonce", LargeBinary, nullable=True),
    Column("dek_tag", LargeBinary, nullable=True),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    ),
    Column(
        "updated_at",
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    ),
)

__all__ = ["metadata", "notes_table", "app_settings_table"]
