"""AES-256-GCM encryption service for note content."""

import base64
import json
import os
from typing import Optional, Dict, Any, Tuple
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from app.core.config import PW_PBKDF2_ITERATIONS


class EncryptionService:
    """Service for encrypting and decrypting note content using AES-256-GCM with DEK architecture."""
    
    def __init__(self):
        self.master_key: Optional[bytes] = None  # Derived from password, used to encrypt DEK
        self.dek: Optional[bytes] = None  # Data Encryption Key, used for note encryption
        
    def derive_master_key(self, password: str, salt: bytes, iterations: int = None) -> bytes:
        """Derive master key from password using PBKDF2 with configurable iteration count.
        
        Args:
            password: User's password
            salt: Random salt for key derivation
            iterations: Number of PBKDF2 iterations (defaults to config value)
            
        Returns:
            32-byte master key
        """
        if iterations is None:
            iterations = PW_PBKDF2_ITERATIONS
            
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits for AES-256
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
    
    def generate_dek(self) -> bytes:
        """Generate a new random Data Encryption Key.
        
        Returns:
            32-byte random key for AES-256
        """
        return os.urandom(32)
    
    def encrypt_dek(self, dek: bytes, master_key: bytes) -> Tuple[bytes, bytes, bytes]:
        """Encrypt the DEK with the master key.
        
        Args:
            dek: Data Encryption Key to encrypt
            master_key: Master key derived from password
            
        Returns:
            Tuple of (encrypted_dek, nonce, tag)
        """
        # Generate random nonce
        nonce = os.urandom(12)
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(master_key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        
        # Encrypt the DEK
        ciphertext = encryptor.update(dek) + encryptor.finalize()
        
        # Get the authentication tag
        tag = encryptor.tag
        
        return (ciphertext, nonce, tag)
    
    def decrypt_dek(self, encrypted_dek: bytes, nonce: bytes, tag: bytes, master_key: bytes) -> bytes:
        """Decrypt the DEK using the master key.
        
        Args:
            encrypted_dek: Encrypted DEK bytes
            nonce: Nonce used for encryption
            tag: Authentication tag
            master_key: Master key derived from password
            
        Returns:
            Decrypted DEK
        """
        cipher = Cipher(
            algorithms.AES(master_key),
            modes.GCM(nonce, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        
        # Decrypt the DEK
        dek = decryptor.update(encrypted_dek) + decryptor.finalize()
        return dek
    
    def set_master_key_and_dek(self, password: str, salt: bytes, encrypted_dek: bytes = None, 
                               dek_nonce: bytes = None, dek_tag: bytes = None) -> None:
        """Set both master key and DEK for this session.
        
        Args:
            password: User's password
            salt: Salt for key derivation
            encrypted_dek: Encrypted DEK from database (optional)
            dek_nonce: Nonce for DEK decryption (optional)
            dek_tag: Tag for DEK decryption (optional)
        """
        # Derive master key
        self.master_key = self.derive_master_key(password, salt)
        
        # If DEK is provided, decrypt it; otherwise generate new one
        if encrypted_dek and dek_nonce and dek_tag:
            self.dek = self.decrypt_dek(encrypted_dek, dek_nonce, dek_tag, self.master_key)
        else:
            self.dek = self.generate_dek()
    
    def clear_keys(self) -> None:
        """Clear all encryption keys from memory."""
        self.master_key = None
        self.dek = None
    
    def encrypt(self, plaintext: str) -> tuple[str, bytes, bytes]:
        """Encrypt plaintext using AES-256-GCM with the DEK.
        
        Args:
            plaintext: Plain text content to encrypt
            
        Returns:
            Tuple of (ciphertext_base64, nonce_bytes, tag_bytes) for separate DB storage
                
        Raises:
            ValueError: If no DEK is set
        """
        if not self.dek:
            raise ValueError("No DEK set - ensure password has been provided")
            
        # Generate random nonce (96 bits for GCM)
        nonce = os.urandom(12)
        
        # Create cipher using DEK
        cipher = Cipher(
            algorithms.AES(self.dek),
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
        """Decrypt AES-256-GCM encrypted data from separate database fields using DEK.
        
        Args:
            ciphertext_base64: Base64 encoded ciphertext
            nonce: Nonce bytes
            tag: Authentication tag bytes
            
        Returns:
            Decrypted plain text content
            
        Raises:
            ValueError: If no DEK is set
            Exception: If decryption fails (wrong password or corrupted data)
        """
        if not self.dek:
            raise ValueError("No DEK set - ensure password has been provided")
            
        try:
            # Decode ciphertext from base64
            ciphertext = base64.b64decode(ciphertext_base64)
            
            # Create cipher with tag using DEK
            cipher = Cipher(
                algorithms.AES(self.dek),
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