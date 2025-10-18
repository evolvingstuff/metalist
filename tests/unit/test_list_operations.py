import uuid

import pytest

from app.db import begin_writer
from app.db.notes_sql import insert_note, fetch_children_ordered
from app.models.enums import MovePosition
from app.models.list_operations import ListOperations
from app.models.utils import paste_note_from_memory
from app.services import content_cache
from app.services.note_store import store
from app.models.database import SafeSession


@pytest.fixture(autouse=True)
def use_memory_db():
    SafeSession.use_memory_db()
    yield
    SafeSession.use_file_db()


def reset_store_and_cache():
    with store._lock:
        store._note_map.clear()
        store._children.clear()
        store._hash_tree.clear()
        store._loaded = False
    content_cache.clear_cache()


def test_move_note_with_store_after_paste():
    reset_store_and_cache()

    root_id = str(uuid.uuid4())
    with begin_writer() as connection:
        insert_note(
            connection,
            note_id=root_id,
            content="<div>root</div>",
            encryption_nonce=None,
            encryption_tag=None,
            parent_id=None,
            prev_id=None,
            next_id=None,
            is_collapsed=False,
        )

    content_cache.cache_note(root_id, "<div>root</div>")

    session = SafeSession(bind=SafeSession.get_engine())
    try:
        store.load_from_db(session)

        clipboard_data = {
            "content": "<div>parent</div>",
            "children": [
                {
                    "content": "<div>child</div>",
                    "children": [],
                }
            ],
        }

        with SafeSession.allow_reads("test:paste"):
            new_note_id = paste_note_from_memory(session, clipboard_data, None)

        with SafeSession.allow_reads("test:fetch_children"):
            new_children = fetch_children_ordered(session.connection(), new_note_id)
        assert len(new_children) == 1

        store.load_from_db(session)
        assert new_note_id in store.get_children(None)

        ListOperations.move_note(
            session,
            note_id=new_note_id,
            new_parent_id=None,
            sibling_id=root_id,
            position=MovePosition.AFTER,
        )
        session.commit()

        store.load_from_db(session)
        root_children = store.get_children(None)
        assert root_children[:2] == [root_id, new_note_id]
        new_children = store.get_children(new_note_id)
        assert len(new_children) == 1
    finally:
        session.close()
