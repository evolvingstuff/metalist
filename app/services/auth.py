"""Authentication and password management service."""

import secrets
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from app.core.config import PBKDF2_ITERATIONS
from app.models.database import AppSettings, DBNote
from app.services.encryption import EncryptionService


class AuthService:
    """Service for managing passwords and authentication."""
    
    def __init__(self, db: Session):
        self.db = db
        self.encryption = EncryptionService()
    
    def get_settings(self) -> Optional[AppSettings]:
        """Get the app settings from database.
        
        Returns:
            AppSettings object or None if not exists
        """
        return self.db.query(AppSettings).filter(AppSettings.id == 1).first()
    
    def initialize_settings(self) -> AppSettings:
        """Initialize app settings if they don't exist.
        
        Returns:
            AppSettings object
        """
        settings = self.get_settings()
        if not settings:
            settings = AppSettings(
                id=1,
                encryption_enabled=False,
                encryption_algorithm=None
            )
            self.db.add(settings)
            self.db.commit()
        return settings
    
    def hash_password(self, password: str, salt: bytes) -> str:
        """Create PBKDF2 hash for storage.
        
        Args:
            password: Plain text password
            salt: Random salt
            
        Returns:
            Hex string of password hash
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        return key.hex()
    
    def verify_password(self, password: str) -> bool:
        """Check if provided password is correct.
        
        Args:
            password: Password to verify
            
        Returns:
            True if password is correct, False otherwise
        """
        settings = self.get_settings()
        if not settings or not settings.password_hash:
            return False
            
        # Hash the provided password with stored salt
        password_hash = self.hash_password(password, settings.password_salt)
        
        # Use constant-time comparison
        return secrets.compare_digest(password_hash, settings.password_hash)
    
    def check_password_strength(self, password: str) -> bool:
        """Check password strength (stub for now).
        
        TODO: Implement real strength checking
        
        Args:
            password: Password to check
            
        Returns:
            True if password meets requirements
        """
        return len(password) > 3
    
    def has_password(self) -> bool:
        """Check if a password is currently set.
        
        Returns:
            True if password is set, False otherwise
        """
        settings = self.get_settings()
        return settings is not None and settings.password_hash is not None
    
    def set_password(self, password: str) -> Tuple[bool, str]:
        """Set initial password (when none exists).
        
        Args:
            password: New password to set
            
        Returns:
            Tuple of (success, message)
        """
        if self.has_password():
            return False, "Password already exists. Use change_password instead."
        
        if not self.check_password_strength(password):
            return False, "Password is too weak (must be > 3 characters)"
        
        # Initialize settings if needed
        settings = self.initialize_settings()
        
        # Generate salt and hash password
        salt = self.encryption.generate_salt()
        password_hash = self.hash_password(password, salt)
        
        # Update settings
        settings.password_salt = salt
        settings.password_hash = password_hash
        settings.encryption_enabled = True
        settings.encryption_algorithm = "AES-256-GCM"
        
        # Set encryption key for this session
        self.encryption.set_key(password, salt)
        
        # Encrypt all existing notes
        notes = self.db.query(DBNote).all()
        encrypted_count = 0
        
        for note in notes:
            if note.content and note.encryption_nonce is None:
                # Only encrypt if not already encrypted (no nonce means unencrypted)
                try:
                    # Encrypt the content using separate field approach
                    ciphertext_base64, nonce_bytes, tag_bytes = self.encryption.encrypt_for_storage(note.content)
                    note.content = ciphertext_base64
                    note.encryption_nonce = nonce_bytes
                    note.encryption_tag = tag_bytes
                    encrypted_count += 1
                except Exception as e:
                    print(f"Failed to encrypt note {note.id}: {e}")
        
        self.db.commit()
        
        return True, f"Password set successfully. Encrypted {encrypted_count} notes."
    
    def change_password(self, current_password: str, new_password: str) -> Tuple[bool, str]:
        """Change existing password (re-encrypts all notes).
        
        Args:
            current_password: Current password for verification
            new_password: New password to set
            
        Returns:
            Tuple of (success, message)
        """
        if not self.has_password():
            return False, "No password is currently set. Use set_password instead."
        
        if not self.verify_password(current_password):
            return False, "Current password is incorrect"
        
        if not self.check_password_strength(new_password):
            return False, "New password is too weak (must be > 3 characters)"
        
        settings = self.get_settings()
        
        # Set up decryption with old password
        self.encryption.set_key(current_password, settings.password_salt)
        
        # Generate new salt and hash
        new_salt = self.encryption.generate_salt()
        new_password_hash = self.hash_password(new_password, new_salt)
        
        # Create new encryption service for re-encryption
        new_encryption = EncryptionService()
        new_encryption.set_key(new_password, new_salt)
        
        # Re-encrypt all notes
        notes = self.db.query(DBNote).all()
        re_encrypted_count = 0
        
        for note in notes:
            if note.content and note.encryption_nonce is not None:
                try:
                    # Decrypt with old password using separate fields
                    plaintext = self.encryption.decrypt_from_storage(note.content, note.encryption_nonce, note.encryption_tag)
                    # Re-encrypt with new password
                    ciphertext_base64, nonce_bytes, tag_bytes = new_encryption.encrypt_for_storage(plaintext)
                    note.content = ciphertext_base64
                    note.encryption_nonce = nonce_bytes
                    note.encryption_tag = tag_bytes
                    re_encrypted_count += 1
                except Exception as e:
                    # Log error but continue
                    print(f"Failed to re-encrypt note {note.id}: {e}")
        
        # Update settings with new password
        settings.password_salt = new_salt
        settings.password_hash = new_password_hash
        
        self.db.commit()
        
        # Clear old key and set new one
        self.encryption.clear_key()
        self.encryption = new_encryption
        
        return True, f"Password changed successfully. Re-encrypted {re_encrypted_count} notes."
    
    def remove_password(self, current_password: str) -> Tuple[bool, str]:
        """Remove password protection (decrypts all notes).
        
        Args:
            current_password: Current password for verification
            
        Returns:
            Tuple of (success, message)
        """
        if not self.has_password():
            return False, "No password is currently set"
        
        if not self.verify_password(current_password):
            return False, "Password is incorrect"
        
        settings = self.get_settings()
        
        # Set up decryption
        self.encryption.set_key(current_password, settings.password_salt)
        
        # Decrypt all notes
        notes = self.db.query(DBNote).all()
        decrypted_count = 0
        
        for note in notes:
            if note.content and note.encryption_nonce is not None:
                try:
                    # Decrypt the content using separate fields
                    plaintext = self.encryption.decrypt_from_storage(note.content, note.encryption_nonce, note.encryption_tag)
                    note.content = plaintext
                    # Clear encryption fields
                    note.encryption_nonce = None
                    note.encryption_tag = None
                    decrypted_count += 1
                except Exception as e:
                    # Log error but continue
                    print(f"Failed to decrypt note {note.id}: {e}")
        
        # Clear password from settings
        settings.password_salt = None
        settings.password_hash = None
        settings.encryption_enabled = False
        settings.encryption_algorithm = None
        
        self.db.commit()
        
        # Clear encryption key
        self.encryption.clear_key()
        
        return True, f"Password removed successfully. Decrypted {decrypted_count} notes."