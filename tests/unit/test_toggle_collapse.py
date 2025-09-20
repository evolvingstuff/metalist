from tests.unit.common import *  # brings in db fixture and helpers
from app.models.database import DBNote
from app.services.transaction_manager import get_transaction_manager
from app.services.note_service import NoteService
from app.services.undo_service import UndoRedoService
from app.models.linked_list import LinkedListManager


def reset_transaction_manager(transaction_manager):
    transaction_manager.command_stack.clear_all()
    transaction_manager.active_client_id = None
    transaction_manager.last_search_query = None
    transaction_manager.end_transaction()


def test_collapse_expand_tracks_undo(db):
    transaction_manager = get_transaction_manager()
    reset_transaction_manager(transaction_manager)

    note_id = "toggle-note"

    with transaction_scope(db):
        db.add(DBNote(id=note_id, content=""))

    with NoteService(db, transaction_manager, client_id="client-1") as service:
        service.set_note_collapse(note_id, True)

    note = LinkedListManager.get_note(db, note_id)
    assert note.is_collapsed is True

    with UndoRedoService(db, transaction_manager) as undo_service:
        undo_service.undo(client_id="client-1")

    note = LinkedListManager.get_note(db, note_id)
    assert note.is_collapsed is False

    with UndoRedoService(db, transaction_manager) as redo_service:
        redo_service.redo(client_id="client-1")

    note = LinkedListManager.get_note(db, note_id)
    assert note.is_collapsed is True
