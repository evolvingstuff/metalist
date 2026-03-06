"""AES-256-GCM encryption service for note content and file payloads."""

import base64
import os
from typing import Optional, Tuple
from argon2.low_level import ARGON2_VERSION, Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from app.config import (
    KDF_MEMORY_COST_KIB,
    KDF_PARALLELISM,
    KDF_TIME_COST,
)


class EncryptionService:
    """Service for encrypting and decrypting note content using AES-256-GCM with DEK architecture."""
    
    def __init__(self):
        self.master_key: Optional[bytes] = None  # Derived from password, used to encrypt DEK
        self.dek: Optional[bytes] = None  # Data Encryption Key, used for note encryption
        
    def derive_master_key(
        self,
        password: str,
        salt: bytes,
        time_cost: int,
        memory_cost_kib: int,
        parallelism: int,
    ) -> bytes:
        """Derive master key from password using Argon2id.
        
        Args:
            password: User's password
            salt: Random salt for key derivation
            time_cost: Argon2id time-cost parameter
            memory_cost_kib: Argon2id memory-cost parameter
            parallelism: Argon2id parallelism parameter
            
        Returns:
            32-byte master key
        """
        if not isinstance(time_cost, int):
            raise TypeError(f"time_cost must be an int: {type(time_cost)}")
        if time_cost <= 0:
            raise ValueError(f"time_cost must be positive: {time_cost}")
        if not isinstance(memory_cost_kib, int):
            raise TypeError(f"memory_cost_kib must be an int: {type(memory_cost_kib)}")
        if memory_cost_kib <= 0:
            raise ValueError(f"memory_cost_kib must be positive: {memory_cost_kib}")
        if not isinstance(parallelism, int):
            raise TypeError(f"parallelism must be an int: {type(parallelism)}")
        if parallelism <= 0:
            raise ValueError(f"parallelism must be positive: {parallelism}")

        return hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            hash_len=32,
            type=Type.ID,
            version=ARGON2_VERSION,
        )
    
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
    
    def set_master_key_and_dek(
        self,
        password: str,
        salt: bytes,
        encrypted_dek: Optional[bytes],
        dek_nonce: Optional[bytes],
        dek_tag: Optional[bytes],
    ) -> None:
        """Set both master key and DEK for this session.
        
        Args:
            password: User's password
            salt: Salt for key derivation
            encrypted_dek: Encrypted DEK from database (optional)
            dek_nonce: Nonce for DEK decryption (optional)
            dek_tag: Tag for DEK decryption (optional)
        """
        # Derive master key
        self.master_key = self.derive_master_key(
            password,
            salt,
            KDF_TIME_COST,
            KDF_MEMORY_COST_KIB,
            KDF_PARALLELISM,
        )
        
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
        if self.dek is None:
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

    def encrypt_bytes(self, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
        if self.dek is None:
            raise ValueError("No DEK set - ensure password has been provided")
        if not isinstance(plaintext, bytes):
            raise TypeError(f"plaintext must be bytes, got {type(plaintext)}")

        nonce = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(self.dek),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        tag = encryptor.tag
        return ciphertext, nonce, tag
    
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
        if self.dek is None:
            raise ValueError("No DEK set - ensure password has been provided")
            
        # Normalize padding for base64 strings
        normalized = ciphertext_base64.strip()
        missing_padding = (-len(normalized)) % 4
        if missing_padding:
            normalized += "=" * missing_padding

        ciphertext = base64.b64decode(normalized)

        cipher = Cipher(
            algorithms.AES(self.dek),
            modes.GCM(nonce, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        plaintext_bytes = decryptor.update(ciphertext) + decryptor.finalize()
        return plaintext_bytes.decode('utf-8')

    def decrypt_bytes(self, ciphertext: bytes, nonce: bytes, tag: bytes) -> bytes:
        if self.dek is None:
            raise ValueError("No DEK set - ensure password has been provided")
        if not isinstance(ciphertext, bytes):
            raise TypeError(f"ciphertext must be bytes, got {type(ciphertext)}")

        cipher = Cipher(
            algorithms.AES(self.dek),
            modes.GCM(nonce, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()
    
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

    def encrypt_bytes_for_storage(self, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
        return self.encrypt_bytes(plaintext)
    
    def decrypt_from_storage(self, content: str, nonce: Optional[bytes], tag: Optional[bytes]) -> str:
        """Decrypt content from database storage format.
        
        Args:
            content: Base64 ciphertext or plain text from database
            nonce: Nonce bytes (None if not encrypted)
            tag: Tag bytes (None if not encrypted)
            
        Returns:
            Decrypted content or original if not encrypted
        """
        # If no nonce/tag, assume it's unencrypted plaintext
        if nonce is None and tag is None:
            return content

        if (nonce is None) != (tag is None):
            raise ValueError(
                "Encrypted content provided with incomplete metadata: "
                f"nonce={nonce is not None} tag={tag is not None}"
            )
            
        # Otherwise decrypt using separate parameters
        return self.decrypt(content, nonce, tag)

    def decrypt_bytes_from_storage(
        self,
        content: bytes,
        nonce: Optional[bytes],
        tag: Optional[bytes],
    ) -> bytes:
        if nonce is None and tag is None:
            return content

        if (nonce is None) != (tag is None):
            raise ValueError(
                "Encrypted content provided with incomplete metadata: "
                f"nonce={nonce is not None} tag={tag is not None}"
            )

        return self.decrypt_bytes(content, nonce, tag)
