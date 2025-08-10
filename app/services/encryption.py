"""AES-256-GCM encryption service for note content."""

import base64
import json
import os
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from app.core.config import PBKDF2_ITERATIONS


class EncryptionService:
    """Service for encrypting and decrypting note content using AES-256-GCM."""
    
    def __init__(self):
        self.key: Optional[bytes] = None
        
    def derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password using PBKDF2.
        
        Args:
            password: User's password
            salt: Random salt for key derivation
            
        Returns:
            32-byte key suitable for AES-256
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits for AES-256
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
    
    def set_key(self, password: str, salt: bytes) -> None:
        """Set the encryption key for this session.
        
        Args:
            password: User's password
            salt: Salt for key derivation
        """
        self.key = self.derive_key(password, salt)
    
    def clear_key(self) -> None:
        """Clear the encryption key from memory."""
        self.key = None
    
    def encrypt(self, plaintext: str) -> tuple[str, bytes, bytes]:
        """Encrypt plaintext using AES-256-GCM.
        
        Args:
            plaintext: Plain text content to encrypt
            
        Returns:
            Tuple of (ciphertext_base64, nonce_bytes, tag_bytes) for separate DB storage
                
        Raises:
            ValueError: If no encryption key is set
        """
        if not self.key:
            raise ValueError("No encryption key set")
            
        # Generate random nonce (96 bits for GCM)
        nonce = os.urandom(12)
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        
        # Encrypt the plaintext
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext = encryptor.update(plaintext_bytes) + encryptor.finalize()
        
        # Get the authentication tag
        tag = encryptor.tag
        
        # Return for separate database field storage
        return (
            base64.b64encode(ciphertext).decode('utf-8'),  # ciphertext as base64 string
            nonce,  # nonce as bytes
            tag     # tag as bytes
        )
    
    def decrypt(self, ciphertext_base64: str, nonce: bytes, tag: bytes) -> str:
        """Decrypt AES-256-GCM encrypted data from separate database fields.
        
        Args:
            ciphertext_base64: Base64 encoded ciphertext
            nonce: Nonce bytes
            tag: Authentication tag bytes
            
        Returns:
            Decrypted plain text content
            
        Raises:
            ValueError: If no encryption key is set
            Exception: If decryption fails (wrong password or corrupted data)
        """
        if not self.key:
            raise ValueError("No encryption key set")
            
        try:
            # Decode ciphertext from base64
            ciphertext = base64.b64decode(ciphertext_base64)
            
            # Create cipher with tag
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.GCM(nonce, tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Decrypt
            plaintext_bytes = decryptor.update(ciphertext) + decryptor.finalize()
            
            return plaintext_bytes.decode('utf-8')
            
        except Exception as e:
            raise Exception(f"Decryption failed: {str(e)}")
    
    def generate_salt(self) -> bytes:
        """Generate cryptographically secure random salt.
        
        Returns:
            32 bytes of random data
        """
        return os.urandom(32)
    
    def encrypt_for_storage(self, plaintext: str) -> tuple[str, bytes, bytes]:
        """Encrypt plaintext for storage in separate database fields.
        
        Args:
            plaintext: Plain text content to encrypt
            
        Returns:
            Tuple of (ciphertext_base64, nonce_bytes, tag_bytes) for separate DB storage
        """
        return self.encrypt(plaintext)
    
    def decrypt_from_storage(self, content: str, nonce: bytes = None, tag: bytes = None) -> str:
        """Decrypt content from database storage format.
        
        Args:
            content: Base64 ciphertext or plain text from database
            nonce: Nonce bytes (None if not encrypted)
            tag: Tag bytes (None if not encrypted)
            
        Returns:
            Decrypted content or original if not encrypted
        """
        # If no nonce/tag, assume it's unencrypted plaintext
        if nonce is None or tag is None:
            return content
            
        # Otherwise decrypt using separate parameters
        return self.decrypt(content, nonce, tag)