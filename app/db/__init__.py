"""Utility layer for direct SQL access.

This package exposes guard-aware connection helpers and composable SQL
functions so higher-level services can bypass the ORM while keeping the
post-startup read guard enforced.
"""

from .engine import (
    GuardedConnection,
    begin_writer,
    connect_reader,
    allow_reads,
    enable_read_guard,
    disable_read_guard,
    get_engine,
)
from .schema import metadata, notes_table, app_settings_table

__all__ = [
    "GuardedConnection",
    "begin_writer",
    "connect_reader",
    "allow_reads",
    "enable_read_guard",
    "disable_read_guard",
    "get_engine",
    "metadata",
    "notes_table",
    "app_settings_table",
]
