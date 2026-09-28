from __future__ import annotations

import sqlite3

from app.db.notes_sql import delete_notes
from app.db.schema import NOTES_TABLE, initialize_schema


def _insert_notes(connection: sqlite3.Connection, count: int) -> list[str]:
    note_ids = [f"note-{index:06d}" for index in range(count)]
    connection.executemany(
        f"INSERT INTO {NOTES_TABLE} (id, content, tags, created_at, updated_at) VALUES (?, '', '', 'now', 'now')",
        [(note_id,) for note_id in note_ids],
    )
    return note_ids


# SQLite's default bound-variable limit since 3.32; older builds allow 999.
# Connection.getlimit() would read the real limit but needs Python 3.11+.
_DEFAULT_SQLITE_VARIABLE_LIMIT = 32766
_LEGACY_SQLITE_VARIABLE_LIMIT = 999


def test_delete_notes_handles_more_ids_than_sqlite_variable_limit() -> None:
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)
    note_ids = _insert_notes(connection, _DEFAULT_SQLITE_VARIABLE_LIMIT + 5)
    kept_id = note_ids.pop()
    delete_statements: list[str] = []
    connection.set_trace_callback(
        lambda statement: delete_statements.append(statement) if statement.startswith("DELETE") else None
    )

    delete_notes(connection, note_ids)

    connection.set_trace_callback(None)
    remaining = [row[0] for row in connection.execute(f"SELECT id FROM {NOTES_TABLE}")]
    assert remaining == [kept_id]
    # Every statement stays within even the smallest limit SQLite builds use.
    assert len(delete_statements) > 1
    assert all(statement.count("'note-") <= _LEGACY_SQLITE_VARIABLE_LIMIT for statement in delete_statements)
