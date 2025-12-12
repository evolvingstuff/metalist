from __future__ import annotations

import secrets
from types import SimpleNamespace
from typing import Optional, Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.models.database import SafeSession
from app.config import PW_PBKDF2_ITERATIONS
from app.db.notes_sql import fetch_all_for_cache, update_note_content
from app.db.settings_sql import (
    clear_password_settings,
    fetch_settings,
    insert_default_settings,
    update_password_settings,
)
from app.services.content_cache import cache_note
from app.services.encryption import EncryptionService
from app.services.maintenance_mode import maintenance_service
from app.services.note_store import store as note_store


class AuthService:
    """Service for managing passwords and authentication."""

    def __init__(self, db: SafeSession):
        self.db = db
        self.encryption = EncryptionService()

    def get_settings(self) -> Optional[SimpleNamespace]:
        """Fetch application settings from the database."""
        with SafeSession.allow_reads("auth:get_settings"):
            row = fetch_settings(self.db.connection())
        if not row:
            return None
        return SimpleNamespace(**row)

    def initialize_settings(self) -> SimpleNamespace:
        """Ensure settings exist before continuing."""
        settings = self.get_settings()
        if settings:
            return settings
        insert_default_settings(self.db.connection())
        self.db.commit()
        settings = self.get_settings()
        if not settings:
            raise RuntimeError("App settings initialization failed")
        return settings

    def hash_password(self, password: str, salt: bytes, iterations: Optional[int] = None) -> str:
        """Return PBKDF2 hash used for password storage."""
        if iterations is None:
            iterations = PW_PBKDF2_ITERATIONS
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
            backend=default_backend(),
        )
        key = kdf.derive(password.encode("utf-8"))
        return key.hex()

    def verify_password(self, password: str) -> bool:
        """Return True if supplied password matches stored hash."""
        settings = self.get_settings()
        if not settings or not settings.password_hash:
            return False
        stored_iterations = settings.password_iterations or 250_000
        password_hash = self.hash_password(password, settings.password_salt, stored_iterations)
        return secrets.compare_digest(password_hash, settings.password_hash)

    def check_password_strength(self, password: str) -> bool:
        """Return True when password meets minimal strength requirements."""
        return len(password) > 3

    def has_password(self) -> bool:
        """Return True if password protection is enabled."""
        settings = self.get_settings()
        return settings is not None and settings.password_hash is not None

    def set_password(self, password: str) -> Tuple[bool, str]:
        """Enable password protection by encrypting all existing content."""
        if self.has_password():
            return False, "Password already exists. Use change_password instead."
        if not self.check_password_strength(password):
            return False, "Password is too weak (must be > 3 characters)"

        self.initialize_settings()
        salt = self.encryption.generate_salt()
        password_hash = self.hash_password(password, salt)

        dek = self.encryption.generate_dek()
        master_key = self.encryption.derive_master_key(password, salt)
        encrypted_dek, dek_nonce, dek_tag = self.encryption.encrypt_dek(dek, master_key)

        self.encryption.master_key = master_key
        self.encryption.dek = dek

        maintenance_service.enter_maintenance("Encrypting all notes with new password")
        connection = self.db.connection()
        encrypted_count = 0
        try:
            with SafeSession.allow_reads("auth:set_password:fetch_notes"):
                notes = fetch_all_for_cache(connection)

            for note in notes:
                note_id = note["id"]
                content = note["content"]
                if content is None:
                    raise RuntimeError(
                        f"Password setup failed: Note {note_id} has NULL content."
                    )
                if note.get("encryption_nonce") is not None:
                    continue
                try:
                    ciphertext_base64, nonce_bytes, tag_bytes = self.encryption.encrypt_for_storage(content)
                    update_note_content(
                        connection,
                        note_id,
                        content=ciphertext_base64,
                        encryption_nonce=nonce_bytes,
                        encryption_tag=tag_bytes,
                    )
                    cache_note(note_id, content)
                    encrypted_count += 1
                except Exception as exc:
                    print(f"🚨 FATAL: Failed to encrypt note {note_id}: {exc}")
                    print("🚨 Cannot continue password setup with broken encryption!")
                    print("🚨 CRASHING IMMEDIATELY")
                    raise RuntimeError(
                        f"Password setup failed: Could not encrypt note {note_id}: {exc}"
                    ) from exc

            update_password_settings(
                connection,
                password_hash=password_hash,
                password_salt=salt,
                password_iterations=PW_PBKDF2_ITERATIONS,
                encrypted_dek=encrypted_dek,
                dek_nonce=dek_nonce,
                dek_tag=dek_tag,
                encryption_algorithm="AES-256-GCM",
            )
            self.db.commit()
        finally:
            maintenance_service.exit_maintenance()

        if note_store.loaded:
            with SafeSession.allow_reads("auth:set_password:refresh_store"):
                note_store.load_from_db(self.db)

        return True, f"Password set successfully. Encrypted {encrypted_count} notes."

    def change_password(
        self,
        current_password: str,
        new_password: str,
        iterations: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Change the password while keeping the existing DEK."""
        if not self.has_password():
            return False, "No password is currently set. Use set_password instead."
        if not self.verify_password(current_password):
            return False, "Current password is incorrect"
        if not self.check_password_strength(new_password):
            return False, "New password is too weak (must be > 3 characters)"

        settings = self.get_settings()
        old_master_key = self.encryption.derive_master_key(current_password, settings.password_salt)
        dek = self.encryption.decrypt_dek(
            settings.encrypted_dek,
            settings.dek_nonce,
            settings.dek_tag,
            old_master_key,
        )

        if iterations is None:
            iterations = PW_PBKDF2_ITERATIONS
        if not (100_000 <= iterations <= 10_000_000):
            return False, "Iterations must be between 100,000 and 10,000,000"

        new_salt = self.encryption.generate_salt()
        new_password_hash = self.hash_password(new_password, new_salt, iterations)
        new_master_key = self.encryption.derive_master_key(new_password, new_salt, iterations)
        encrypted_dek, dek_nonce, dek_tag = self.encryption.encrypt_dek(dek, new_master_key)

        connection = self.db.connection()
        update_password_settings(
            connection,
            password_hash=new_password_hash,
            password_salt=new_salt,
            password_iterations=iterations,
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            dek_tag=dek_tag,
            encryption_algorithm=settings.encryption_algorithm or "AES-256-GCM",
        )
        self.db.commit()

        self.encryption.master_key = new_master_key
        self.encryption.dek = dek
        return True, "Password changed successfully. Notes remain encrypted with the same key."

    def remove_password(self, current_password: str) -> Tuple[bool, str]:
        """Disable password protection by decrypting notes and clearing settings."""
        if not self.has_password():
            return False, "No password is currently set"
        if not self.verify_password(current_password):
            return False, "Password is incorrect"

        settings = self.get_settings()
        master_key = self.encryption.derive_master_key(current_password, settings.password_salt)
        dek = self.encryption.decrypt_dek(
            settings.encrypted_dek,
            settings.dek_nonce,
            settings.dek_tag,
            master_key,
        )
        self.encryption.master_key = master_key
        self.encryption.dek = dek

        maintenance_service.enter_maintenance("Decrypting all notes (removing password protection)")
        connection = self.db.connection()
        try:
            with SafeSession.allow_reads("auth:remove_password:fetch_notes"):
                notes = fetch_all_for_cache(connection)
            decrypted_count = 0

            for note in notes:
                note_id = note["id"]
                content = note["content"]
                nonce = note.get("encryption_nonce")
                tag = note.get("encryption_tag")

                is_encrypted = nonce is not None or tag is not None
                if not is_encrypted:
                    continue

                if nonce is None or tag is None:
                    raise RuntimeError(
                        "Password removal failed: encrypted note has incomplete metadata: "
                        f"note_id={note_id} nonce={nonce is not None} tag={tag is not None}"
                    )
                if content is None:
                    raise RuntimeError(
                        f"Password removal failed: encrypted note {note_id} has NULL content"
                    )

                try:
                    plaintext = self.encryption.decrypt_from_storage(content, nonce, tag)
                    update_note_content(
                        connection,
                        note_id,
                        content=plaintext,
                        encryption_nonce=None,
                        encryption_tag=None,
                    )
                    cache_note(note_id, plaintext)
                    decrypted_count += 1
                except Exception as exc:
                    print(f"🚨 FATAL: Failed to decrypt note {note_id}: {exc}")
                    print("🚨 Cannot remove password protection with broken decryption!")
                    print("🚨 CRASHING IMMEDIATELY")
                    raise RuntimeError(
                        f"Password removal failed: Could not decrypt note {note_id}: {exc}"
                    ) from exc

            clear_password_settings(connection)
            self.db.commit()
            self.encryption.clear_keys()
        finally:
            maintenance_service.exit_maintenance()

        if note_store.loaded:
            with SafeSession.allow_reads("auth:remove_password:refresh_store"):
                note_store.load_from_db(self.db)

        return True, f"Password removed successfully. Decrypted {decrypted_count} notes."
