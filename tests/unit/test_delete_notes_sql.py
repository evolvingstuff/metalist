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


def test_delete_notes_handles_more_ids_than_sqlite_variable_limit() -> None:
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)
    variable_limit = connection.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)
    note_ids = _insert_notes(connection, variable_limit + 5)
    kept_id = note_ids.pop()

    delete_notes(connection, note_ids)

    remaining = [row[0] for row in connection.execute(f"SELECT id FROM {NOTES_TABLE}")]
    assert remaining == [kept_id]
