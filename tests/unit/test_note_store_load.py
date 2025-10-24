import uuid

import pytest

from app.db import begin_writer
from app.db.notes_sql import insert_note
from app.services import content_cache
from app.services.note_store import store
from app.models.database import SafeSession


@pytest.fixture(autouse=True)
def use_memory_db():
    SafeSession.use_memory_db()
    yield
    SafeSession.use_file_db()


def test_note_store_loads_core_inserted_note():
    note_id = str(uuid.uuid4())

    with store._lock:
        store._note_map.clear()
        store._links.clear()
        store._heads.clear()
        store._tails.clear()
        store._loaded = False

    content_cache.clear_cache()

    with begin_writer() as connection:
        insert_note(
            connection,
            note_id=note_id,
            content="<div>hello</div>",
            encryption_nonce=None,
            encryption_tag=None,
            parent_id=None,
            prev_id=None,
            next_id=None,
            is_collapsed=False,
        )
        child_id = str(uuid.uuid4())
        insert_note(
            connection,
            note_id=child_id,
            content="<div>child</div>",
            encryption_nonce=None,
            encryption_tag=None,
            parent_id=note_id,
            prev_id=None,
            next_id=None,
            is_collapsed=False,
        )

    # Populate cache entry required by NoteStore
    content_cache.cache_note(note_id, "<div>hello</div>")
    content_cache.cache_note(child_id, "<div>child</div>")

    session = SafeSession()
    try:
        store.load_from_db(session)
    finally:
        session.close()

    record = store.get_note(note_id)
    assert record.id == note_id
    child_ids = store.get_children(note_id)
    assert child_id in child_ids
