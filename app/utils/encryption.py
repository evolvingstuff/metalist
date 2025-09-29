"""Compatibility layer for encryption utilities.

This module provides backward compatibility for the old encryption interface.
It now uses the token-based DEK system for encryption operations.
"""

import logging
from typing import Optional, Tuple

from app.services.encryption import EncryptionService
from app.services.tokens import token_service
from app.services.auth import AuthService
from app.models.database import get_db

# Global encryption service instance (per-request)
_encryption_service: Optional[EncryptionService] = None
_current_token: Optional[str] = None

logger = logging.getLogger(__name__)


def get_encryption_service_with_token(token: str = None) -> Optional[EncryptionService]:
    """Get encryption service with DEK loaded from token.
    
    Args:
        token: Authentication token to get DEK from
        
    Returns:
        EncryptionService instance with DEK loaded or None
    """
    global _encryption_service, _current_token
    
    # If we have a cached service for this token, return it
    if _encryption_service and _current_token == token and token:
        return _encryption_service
    
    if not token:
        return None
        
    # Get encryption keys from token
    keys = token_service.get_encryption_keys(token)
    if not keys:
        return None
        
    master_key, dek = keys
    
    # Create new encryption service with keys
    _encryption_service = EncryptionService()
    _encryption_service.master_key = master_key
    _encryption_service.dek = dek
    _current_token = token
    
    return _encryption_service


def get_encryption_service() -> Optional[EncryptionService]:
    """Get the global encryption service if encryption is available.
    
    Returns:
        EncryptionService instance or None if no encryption available
    """
    # This is kept for backward compatibility but requires active session
    global _encryption_service
    return _encryption_service


def encrypt(content: str, token: str = None) -> Tuple[str, Optional[bytes], Optional[bytes]]:
    """Encrypt note content using DEK from token.
    
    Args:
        content: Plain text content to encrypt
        token: Authentication token (optional, uses global service if not provided)
        
    Returns:
        Tuple of (ciphertext_base64, nonce_bytes, tag_bytes) or (content, None, None) if no encryption
    """
    if not content:
        return content, None, None
    
    # Try to get service with token first
    if token:
        service = get_encryption_service_with_token(token)
    else:
        service = get_encryption_service()
    
    if service and service.dek:
        try:
            return service.encrypt_for_storage(content)
        except Exception as e:
            raise RuntimeError(f"Encryption failed: {e}") from e
    
    # No encryption available, return as-is
    return content, None, None


def decrypt(encrypted_content: str, nonce: bytes = None, tag: bytes = None, token: str = None) -> str:
    """Decrypt note content using DEK from token.
    
    Args:
        encrypted_content: Encrypted content to decrypt or plain text
        nonce: Nonce bytes (None if not encrypted)
        tag: Tag bytes (None if not encrypted)
        token: Authentication token (optional, uses global service if not provided)
        
    Returns:
        Decrypted plain text content or original if decryption not available
    """
    if not encrypted_content:
        return encrypted_content
    
    # If no nonce/tag, assume unencrypted content
    if nonce is None or tag is None:
        return encrypted_content
    
    # Try to get service with token first
    if token:
        service = get_encryption_service_with_token(token)
    else:
        service = get_encryption_service()
    
    if service and service.dek:
        try:
            return service.decrypt_from_storage(encrypted_content, nonce, tag)
        except Exception as e:
            nonce_preview = nonce.hex()[:16] if nonce else 'None'
            tag_preview = tag.hex()[:16] if tag else 'None'
            logger.error(
                "Decrypt failed for content len=%s nonce=%s tag=%s: %s",
                len(encrypted_content) if encrypted_content else 0,
                nonce_preview,
                tag_preview,
                e,
            )
            raise RuntimeError(f"Decryption failed: {e}") from e

    raise RuntimeError("Encrypted content provided but no encryption key is available")


def set_encryption_key(password: str, salt: bytes) -> None:
    """Set the encryption key for the current session.
    
    DEPRECATED: This function is kept for backward compatibility.
    The new DEK system uses token-based key management.
    
    Args:
        password: User's password
        salt: Salt from database
    """
    global _encryption_service
    
    # For backward compatibility, create a service and derive master key
    # But we can't get the DEK without the database settings
    db_gen = get_db()
    db = next(db_gen)
    try:
        auth = AuthService(db)
        settings = auth.get_settings()

        if settings and settings.encrypted_dek:
            _encryption_service = EncryptionService()
            try:
                master_key = _encryption_service.derive_master_key(password, salt)
                dek = _encryption_service.decrypt_dek(
                    settings.encrypted_dek,
                    settings.dek_nonce,
                    settings.dek_tag,
                    master_key
                )
            except Exception as e:
                _encryption_service = None
                raise RuntimeError(f"Failed to set encryption key: {e}") from e

            _encryption_service.master_key = master_key
            _encryption_service.dek = dek
        else:
            # Legacy mode - no DEK in database yet
            _encryption_service = None
    finally:
        db_gen.close()


def clear_encryption_key() -> None:
    """Clear the encryption key from memory.
    
    This clears the global encryption service.
    """
    global _encryption_service, _current_token
    if _encryption_service:
        _encryption_service.clear_keys()
    _encryption_service = None
    _current_token = None


def is_encryption_available(token: str = None) -> bool:
    """Check if encryption is available.
    
    Args:
        token: Authentication token to check
        
    Returns:
        True if encryption is available, False otherwise
    """
    if token:
        service = get_encryption_service_with_token(token)
        return service is not None and service.dek is not None
    else:
        service = get_encryption_service()
        return service is not None and service.dek is not None


def get_encryption_status() -> dict:
    """Get current encryption status.
    
    Returns:
        Dictionary with encryption status information
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        auth = AuthService(db)
        settings = auth.get_settings()

        return {
            "encryption_enabled": settings.encryption_enabled if settings else False,
            "has_dek": bool(settings and settings.encrypted_dek),
            "algorithm": settings.encryption_algorithm if settings else None,
            "global_service_active": _encryption_service is not None and _encryption_service.dek is not None
        }
    finally:
        db_gen.close()
