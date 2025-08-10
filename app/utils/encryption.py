"""Compatibility layer for encryption utilities.

This module provides backward compatibility for the old encryption interface.
It now delegates to the new EncryptionService in app.services.encryption.
"""

from typing import Optional
from app.services.encryption import EncryptionService
from app.services.auth import AuthService
from app.models.database import get_db

# Global encryption service instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> Optional[EncryptionService]:
    """Get the global encryption service if password is set.
    
    Returns:
        EncryptionService instance or None if no password is set
    """
    global _encryption_service
    
    if _encryption_service is None:
        # Check if encryption is enabled in database
        try:
            db = next(get_db())
            auth = AuthService(db)
            settings = auth.get_settings()
            
            if settings and settings.encryption_enabled and settings.password_hash:
                # Note: This requires the password to be set in the current session
                # The actual key should be set when user logs in
                _encryption_service = EncryptionService()
        except:
            pass
    
    return _encryption_service


def encrypt(content: str) -> tuple[str, bytes, bytes]:
    """Encrypt note content.
    
    This is a compatibility function for the old interface, now returning separate fields.
    
    Args:
        content: Plain text content to encrypt
        
    Returns:
        Tuple of (ciphertext_base64, nonce_bytes, tag_bytes) or (content, None, None) if no encryption
    """
    if not content:
        return content, None, None
    
    service = get_encryption_service()
    if service and service.key:
        try:
            return service.encrypt_for_storage(content)
        except:
            # If encryption fails, return original with no encryption fields
            return content, None, None
    
    # No encryption available, return as-is
    return content, None, None


def decrypt(encrypted_content: str, nonce: bytes = None, tag: bytes = None) -> str:
    """Decrypt note content.
    
    This is a compatibility function for the old interface, now using separate fields.
    
    Args:
        encrypted_content: Encrypted content to decrypt or plain text
        nonce: Nonce bytes (None if not encrypted)
        tag: Tag bytes (None if not encrypted)
        
    Returns:
        Decrypted plain text content or original if decryption not available
    """
    if not encrypted_content:
        return encrypted_content
    
    # If no nonce/tag, assume unencrypted content
    if nonce is None or tag is None:
        return encrypted_content
    
    service = get_encryption_service()
    if service and service.key:
        try:
            return service.decrypt_from_storage(encrypted_content, nonce, tag)
        except:
            # If decryption fails, return original
            return encrypted_content
    
    # No decryption available, return as-is
    return encrypted_content


def set_encryption_key(password: str, salt: bytes) -> None:
    """Set the encryption key for the current session.
    
    This should be called after successful authentication.
    
    Args:
        password: User's password
        salt: Salt from database
    """
    global _encryption_service
    
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    
    _encryption_service.set_key(password, salt)


def clear_encryption_key() -> None:
    """Clear the encryption key from memory.
    
    This should be called on logout.
    """
    global _encryption_service
    
    if _encryption_service:
        _encryption_service.clear_key()
        _encryption_service = None