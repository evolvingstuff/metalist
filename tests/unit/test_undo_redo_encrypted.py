import pytest

from app.services.transaction_manager import get_transaction_manager
from app.services.note_service import NoteService
from app.services.undo_service import UndoRedoService
from app.models.database import DBNote
from tests.unit.common import db  # noqa: F401


class DummyService:
    def __init__(self):
        self.dek = True

    def encrypt_for_storage(self, content: str):
        return content[::-1], b"nonce", b"tag"

    def decrypt_from_storage(self, content: str, nonce: bytes, tag: bytes) -> str:
        return content[::-1]


@pytest.fixture(autouse=True)
def mock_encryption_service(monkeypatch):
    monkeypatch.setattr("app.utils.encryption._encryption_service", DummyService())
    monkeypatch.setattr("app.utils.encryption._current_token", None)
    monkeypatch.setattr(
        "app.utils.encryption.get_encryption_service", lambda: DummyService()
    )
    yield
    monkeypatch.setattr("app.utils.encryption._encryption_service", None)


def test_undo_fails_with_encryption(db):
    tm = get_transaction_manager()
    tm.command_stack.clear_all()

    client_id = "encrypted-test"

    with NoteService(db, tm, client_id) as service:
        created = service.create_note()
        note_id = created["id"]

    with NoteService(db, tm, client_id) as service:
        service.update_note(note_id, "secret")

    result = UndoRedoService(db, tm).undo(client_id)
    assert result["status"] == "success"
