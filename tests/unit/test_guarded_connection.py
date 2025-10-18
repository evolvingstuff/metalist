from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db import begin_writer, connect_reader, enable_read_guard
from app.db.notes_sql import insert_note
from app.db.schema import notes_table
from app.models.database import SafeSession


@pytest.fixture(autouse=True)
def memory_db():
    SafeSession.use_memory_db()
    yield
    SafeSession.use_file_db()


def test_guard_blocks_select_outside_allow_reads():
    note_id = "guard-check"

    with begin_writer() as connection:
        insert_note(
            connection,
            note_id=note_id,
            content="",
            encryption_nonce=None,
            encryption_tag=None,
            parent_id=None,
            prev_id=None,
            next_id=None,
            is_collapsed=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    enable_read_guard()

    with begin_writer() as connection:
        with pytest.raises(RuntimeError):
            connection.execute(select(notes_table))

    with connect_reader("guard-test") as connection:
        rows = connection.execute(select(notes_table)).mappings().all()

    assert len(rows) == 1
