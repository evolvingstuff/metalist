import pytest

from app.utils import encryption
from app.services.encryption import EncryptionService


def test_encrypt_empty_string_generates_auth_tag_and_roundtrips(monkeypatch):
    service = EncryptionService()
    service.dek = service.generate_dek()

    monkeypatch.setattr(encryption, "_encryption_service", service)
    monkeypatch.setattr(encryption, "_current_token", None)

    ciphertext, nonce, tag = encryption.encrypt("")

    assert isinstance(ciphertext, str)
    assert nonce is not None and len(nonce) == 12
    assert tag is not None and len(tag) == 16

    decrypted = encryption.decrypt(ciphertext, nonce, tag)
    assert decrypted == ""

    encryption.clear_encryption_key()
