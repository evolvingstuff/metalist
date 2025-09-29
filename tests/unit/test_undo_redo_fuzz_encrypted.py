import random
import pytest

from tests.unit.common import visualize_tree, DBNote, db  # noqa: F401
from app.services.transaction_manager import get_transaction_manager
from app.services.note_service import NoteService
from app.services.undo_service import UndoRedoService
from app.models.enums import MovePosition
from fastapi import HTTPException
from app.utils import encryption as encryption_utils


UNDO_REDO_INTERVAL = 4
CLIENT_ID = "fuzz-client-encrypted"


class DummyEncryptionService:
    def __init__(self):
        self.dek = True

    def encrypt_for_storage(self, content: str):
        return content[::-1], b"nonce", b"tag"

    def decrypt_from_storage(self, content: str, nonce: bytes, tag: bytes) -> str:
        return content[::-1]


@pytest.fixture(autouse=True)
def mock_encryption(monkeypatch):
    service = DummyEncryptionService()
    monkeypatch.setattr(encryption_utils, "_encryption_service", service)
    monkeypatch.setattr(encryption_utils, "_current_token", None)
    monkeypatch.setattr(encryption_utils, "get_encryption_service", lambda: service)
    monkeypatch.setattr(encryption_utils, "get_encryption_service_with_token", lambda token: service)
    yield
    monkeypatch.setattr(encryption_utils, "_encryption_service", None)
    monkeypatch.setattr(encryption_utils, "_current_token", None)


def refresh_active_ids(db):
    return sorted({id for (id,) in db.query(DBNote.id).all()})


def note_service(db, transaction_manager):
    return NoteService(db, transaction_manager, CLIENT_ID)


def test_fuzz_undo_redo_encrypted(db):
    seed = 7
    random.seed(seed)

    notes = []
    for i in range(3):
        note = DBNote(id=str(i), content=f"Note {i}")
        if i > 0:
            note.prev_id = str(i - 1)
            notes[i - 1].next_id = str(i)
        notes.append(note)

    db.add_all(notes)
    db.commit()

    print(f"\n=== Encrypted Undo/Redo Fuzz Seed {seed} ===")
    visualize_tree(db)

    transaction_manager = get_transaction_manager()
    transaction_manager.command_stack.clear_all()

    active_note_ids = refresh_active_ids(db)

    for step in range(50):
        db.expire_all()
        op_choice = random.random()

        if op_choice < 0.3 and active_note_ids:
            target_id = random.choice(active_note_ids)
            try:
                with note_service(db, transaction_manager) as service:
                    service.delete_note(target_id)
            except Exception:
                continue
            active_note_ids = refresh_active_ids(db)
        elif op_choice < 0.6:
            add_type = random.choice(['click', 'sibling'])
            try:
                with note_service(db, transaction_manager) as service:
                    if add_type == 'click':
                        result = service.create_note()
                    else:
                        target_id = random.choice(active_note_ids)
                        result = service.create_sibling_note(target_id)
            except Exception:
                continue
            active_note_ids = refresh_active_ids(db)
        else:
            if len(active_note_ids) < 2:
                continue
            note_id = random.choice(active_note_ids)
            sibling_id = random.choice([nid for nid in active_note_ids if nid != note_id])
            position = random.choice([MovePosition.BEFORE, MovePosition.AFTER])
            try:
                with note_service(db, transaction_manager) as service:
                    service.move_note(note_id, new_parent_id=None, sibling_id=sibling_id, position=position)
            except Exception:
                continue

        if step % UNDO_REDO_INTERVAL == 0:
            undo_service = UndoRedoService(db, transaction_manager)
            if random.choice([True, False]):
                undo_service.undo(CLIENT_ID)
            else:
                undo_service.redo(CLIENT_ID)

        active_note_ids = refresh_active_ids(db)

    visualize_tree(db)
