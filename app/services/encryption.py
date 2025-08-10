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
    
    def encrypt(self, plaintext: str) -> Dict[str, Any]:
        """Encrypt plaintext using AES-256-GCM.
        
        Args:
            plaintext: Plain text content to encrypt
            
        Returns:
            Dictionary containing encrypted data:
                - version: Encryption version (1)
                - algorithm: "AES-256-GCM"
                - ciphertext: Base64 encoded encrypted content
                - nonce: Base64 encoded nonce
                - tag: Base64 encoded authentication tag
                
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
        
        # Return as dictionary with base64 encoded values
        return {
            "version": 1,
            "algorithm": "AES-256-GCM",
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "tag": base64.b64encode(tag).decode('utf-8')
        }
    
    def decrypt(self, encrypted_data: Dict[str, Any]) -> str:
        """Decrypt AES-256-GCM encrypted data.
        
        Args:
            encrypted_data: Dictionary containing encrypted data
            
        Returns:
            Decrypted plain text content
            
        Raises:
            ValueError: If no encryption key is set or data format is invalid
            Exception: If decryption fails (wrong password or corrupted data)
        """
        if not self.key:
            raise ValueError("No encryption key set")
            
        # Validate data format
        if not isinstance(encrypted_data, dict):
            raise ValueError("Invalid encrypted data format")
            
        required_fields = ["ciphertext", "nonce", "tag"]
        for field in required_fields:
            if field not in encrypted_data:
                raise ValueError(f"Missing required field: {field}")
        
        try:
            # Decode from base64
            ciphertext = base64.b64decode(encrypted_data["ciphertext"])
            nonce = base64.b64decode(encrypted_data["nonce"])
            tag = base64.b64decode(encrypted_data["tag"])
            
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
    
    def encrypt_for_storage(self, plaintext: str) -> str:
        """Encrypt plaintext and return as JSON string for database storage.
        
        Args:
            plaintext: Plain text content to encrypt
            
        Returns:
            JSON string containing encrypted data
        """
        encrypted_dict = self.encrypt(plaintext)
        return json.dumps(encrypted_dict)
    
    def decrypt_from_storage(self, stored_content: str) -> str:
        """Decrypt content from database storage format.
        
        Args:
            stored_content: JSON string or plain text from database
            
        Returns:
            Decrypted content or original if not encrypted
        """
        try:
            # Try to parse as JSON
            encrypted_data = json.loads(stored_content)
            
            # Check if it's our encryption format
            if isinstance(encrypted_data, dict) and "algorithm" in encrypted_data:
                return self.decrypt(encrypted_data)
            else:
                # Not our format, return as-is
                return stored_content
        except (json.JSONDecodeError, ValueError):
            # Not JSON, return as-is (unencrypted content)
            return stored_content