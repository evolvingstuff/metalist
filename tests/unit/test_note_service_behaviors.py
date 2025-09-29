import pytest

from tests.unit.common import DBNote, transaction_scope
from tests.unit.common import db  # noqa: F401
from app.models.linked_list import LinkedListManager
from app.services.note_service import NoteService
from app.services.transaction_manager import TransactionManager
from app.services.content_cache import clear_cache, get_cached_content
from app.services import sync_state


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def transaction_manager():
    return TransactionManager()


def _create_note(db, note_id: str, parent_id: str | None = None):
    LinkedListManager.create_note_top(db, note_id, parent_id)
    db.commit()


def test_set_note_collapse_noop_returns_unchanged(db, transaction_manager):
    _create_note(db, "root")
    with transaction_scope(db):
        note = db.get(DBNote, "root")
        note.is_collapsed = True

    with NoteService(db, transaction_manager, client_id="test-client") as service:
        result = service.set_note_collapse("root", True)

    assert result == {"status": "unchanged", "isCollapsed": True}

    with transaction_scope(db):
        persisted = db.get(DBNote, "root")
        assert persisted.is_collapsed is True


def test_delete_note_sets_all_deleted_flag(db, transaction_manager):
    _create_note(db, "root")

    with NoteService(db, transaction_manager, client_id="test-client") as service:
        result = service.delete_note("root")

    assert result["status"] == "deleted"
    assert result["all_deleted"] is True
    assert "updateUUID" in result

    with transaction_scope(db):
        remaining = LinkedListManager.get_ordered_child_list(db, None)
        assert remaining == []


def test_create_note_populates_search_comment(db, transaction_manager):
    sync_state.set_server_sync_uuid("seed")

    with NoteService(db, transaction_manager, client_id="test-client") as service:
        response = service.create_note(search_query="  example text  ")

    assert response["status"] == "created"
    assert response["updateUUID"] == sync_state.get_current_sync_uuid()

    cached = get_cached_content(response["id"])
    assert cached.endswith('/* text search: "example text" */</div>')
    assert "updateUUID" in response
