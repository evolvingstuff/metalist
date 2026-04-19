from __future__ import annotations

import sqlite3

from app.config import TEST_MODE
from app.db.schema import APP_SETTINGS_TABLE, NOTES_TABLE
from app.db.search_history_session import begin_search_history_writer
from app.db.session import begin_writer
from app.db.settings_sql import insert_default_settings
from app.services.content_cache import populate_cache_from_db
from app.services.note_store import store as note_store
from app.services.sync import reset_state as reset_sync_state
from app.services.tab_state import tab_state_store
from app.services.tokens import token_service
from app.services.view_cache import view_cache


def _execute_sql(connection, statement: str) -> None:
    raw_connection = getattr(connection, "raw_connection", None)
    if isinstance(raw_connection, sqlite3.Connection):
        raw_connection.execute(statement)
        return
    assert isinstance(connection, sqlite3.Connection)
    connection.execute(statement)


def reset_state_for_tests() -> None:
    assert TEST_MODE, "reset_state_for_tests is only valid in TEST_MODE"

    with begin_writer() as connection:
        _execute_sql(connection, f"DELETE FROM {NOTES_TABLE}")
        _execute_sql(connection, f"DELETE FROM {APP_SETTINGS_TABLE}")
        insert_default_settings(connection)

    with begin_search_history_writer() as connection:
        _execute_sql(connection, "DELETE FROM search_interaction_history")

    reset_sync_state()
    view_cache.clear()
    tab_state_store.clear_persisted_state_for_tests()
    token_service.reset()

    prefetched_rows = populate_cache_from_db(None)
    note_store.load_from_db(None, prefetched_rows=prefetched_rows)
