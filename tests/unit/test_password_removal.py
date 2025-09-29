import pytest

from app.services.auth import AuthService
from app.models.database import DBNote
from app.utils import encryption as encryption_utils
from tests.unit.common import db  # noqa: F401


def test_remove_password_decrypts_notes(db):
    note = DBNote(id="n1", content="hello world")
    db.add(note)
    db.commit()

    auth = AuthService(db)

    success, message = auth.set_password("secret123")
    assert success, message

    # Mirror middleware behavior: expose session encryption service globally for cache listeners
    encryption_utils._encryption_service = auth.encryption

    db.refresh(note)
    assert note.encryption_nonce is not None
    encrypted_content = note.content

    success, message = auth.remove_password("secret123")
    assert success, message

    db.refresh(note)
    assert note.encryption_nonce is None
    assert note.encryption_tag is None
    assert note.content == "hello world"
    assert note.content != encrypted_content
