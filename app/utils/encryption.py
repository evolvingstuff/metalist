"""Encryption utilities for note content.

Provides XOR-based encryption simulation for development and testing.
Always call encrypt() and decrypt() functions regardless of config flag.
"""

from ..core.config import ENABLE_ENCRYPTION, ENCRYPTION_KEY


def encrypt(content: str) -> str:
    """Encrypt note content.
    
    Args:
        content: Plain text content to encrypt
        
    Returns:
        Encrypted content (or passthrough if encryption disabled)
    """
    if not ENABLE_ENCRYPTION:
        return content
        
    if not content:
        return content
        
    # Simple XOR encryption for simulation
    key_bytes = ENCRYPTION_KEY.encode('utf-8')
    content_bytes = content.encode('utf-8')
    
    encrypted_bytes = bytearray()
    for i, byte in enumerate(content_bytes):
        key_byte = key_bytes[i % len(key_bytes)]
        encrypted_bytes.append(byte ^ key_byte)
    
    # Convert to hex string for storage
    return encrypted_bytes.hex()


def decrypt(encrypted_content: str) -> str:
    """Decrypt note content.
    
    Args:
        encrypted_content: Encrypted content to decrypt
        
    Returns:
        Decrypted plain text content (or passthrough if encryption disabled)
    """
    if not ENABLE_ENCRYPTION:
        return encrypted_content
        
    if not encrypted_content:
        return encrypted_content
        
    try:
        # Convert from hex string back to bytes
        encrypted_bytes = bytes.fromhex(encrypted_content)
        
        # Simple XOR decryption (same as encryption with XOR)
        key_bytes = ENCRYPTION_KEY.encode('utf-8')
        
        decrypted_bytes = bytearray()
        for i, byte in enumerate(encrypted_bytes):
            key_byte = key_bytes[i % len(key_bytes)]
            decrypted_bytes.append(byte ^ key_byte)
        
        return decrypted_bytes.decode('utf-8')
        
    except (ValueError, UnicodeDecodeError) as e:
        # If decryption fails, log error and return original content
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Decryption failed for content: {encrypted_content[:50]}... Error: {e}")
        return encrypted_content