"""Utility layer for direct sqlite access."""

from .engine import (
    GuardedConnection,
    begin_writer,
    connect_reader,
    allow_reads,
    enable_read_guard,
    disable_read_guard,
)
from .schema import (
    APP_SETTINGS_TABLE,
    NOTES_TABLE,
    initialize_schema,
)

__all__ = [
    "GuardedConnection",
    "begin_writer",
    "connect_reader",
    "allow_reads",
    "enable_read_guard",
    "disable_read_guard",
    "APP_SETTINGS_TABLE",
    "NOTES_TABLE",
    "initialize_schema",
]
