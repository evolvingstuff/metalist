"""Unified encryption facade.

Exports:
- EncryptionService (crypto core) from services/encryption
- High-level helpers (encrypt/decrypt, key management) from utils/encryption

This module is the canonical import path for encryption concerns.
"""

from __future__ import annotations

# Core service (AES-256-GCM, PBKDF2, DEK handling)
from app.services.encryption import EncryptionService

# High-level helpers and session-aware utilities re-exported for convenience
from app.utils.encryption import (
    get_encryption_service_with_token,
    get_encryption_service,
    encrypt,
    decrypt,
    set_session_dek,
    clear_encryption_key,
    is_encryption_available,
    get_encryption_status,
)

__all__ = [
    "EncryptionService",
    "get_encryption_service_with_token",
    "get_encryption_service",
    "encrypt",
    "decrypt",
    "set_session_dek",
    "clear_encryption_key",
    "is_encryption_available",
    "get_encryption_status",
]
