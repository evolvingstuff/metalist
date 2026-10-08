"""A private, temporary copy of one namespace database.

The live database is opened read-only and copied with SQLite's online backup,
which is safe while MetaList is running. Everything the experiment does
(unlocking, loading) happens on the copy, which is deleted afterwards. The
copy is a scratch file, not a backup: it lives only in a fresh temporary
directory and nothing else reads it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def live_database_path(*, data_directory: Path, namespace: str) -> Path:
    assert namespace != "" and "/" not in namespace and namespace not in {".", ".."}
    path = data_directory / "namespaces" / namespace / f"{namespace}.metalist.db"
    if not path.is_file():
        raise FileNotFoundError(f"No database for namespace {namespace!r} at {path}")
    return path


def copy_database(*, source: Path, scratch_data_directory: Path, namespace: str) -> Path:
    """Copy `source` into a namespace layout under `scratch_data_directory`."""
    destination = scratch_data_directory / "namespaces" / namespace / f"{namespace}.metalist.db"
    destination.parent.mkdir(parents=True, exist_ok=False)
    source_connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    with source_connection, destination_connection:
        source_connection.backup(destination_connection)
    source_connection.close()
    destination_connection.close()
    return destination
