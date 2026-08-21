from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from app.services.encryption import EncryptionService
from app.services.search_history_storage import (
    decode_search_history_payload,
    encode_search_history_payload,
    new_search_history_storage_id,
    serialize_search_history_payload,
)


def test_encrypted_search_history_payload_is_bound_to_random_storage_id() -> None:
    service = EncryptionService()
    service.dek = b"d" * 32
    storage_id = new_search_history_storage_id()
    other_storage_id = new_search_history_storage_id()
    plaintext = serialize_search_history_payload(
        counts_by_date={"2026-08-20": {"shortcut": 4}},
    )

    ciphertext, nonce, tag = encode_search_history_payload(
        storage_id=storage_id,
        payload_json=plaintext,
        encryption_service=service,
    )

    assert storage_id != other_storage_id
    assert "shortcut" not in ciphertext
    assert decode_search_history_payload(
        storage_id=storage_id,
        stored_payload=ciphertext,
        nonce=nonce,
        tag=tag,
        encryption_service=service,
    ) == plaintext
    with pytest.raises(InvalidTag):
        decode_search_history_payload(
            storage_id=other_storage_id,
            stored_payload=ciphertext,
            nonce=nonce,
            tag=tag,
            encryption_service=service,
        )
