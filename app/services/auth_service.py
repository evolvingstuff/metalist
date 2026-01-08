from __future__ import annotations

import secrets
from types import SimpleNamespace
from typing import Optional, Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.models.database import SafeSession
from app.config import PW_PBKDF2_ITERATIONS
from app.db.notes_sql import fetch_all_for_cache, update_note_fields
from app.db.settings_sql import (
    clear_password_settings,
    fetch_settings,
    insert_default_settings,
    update_password_settings,
)
from app.services.content_cache import cache_note, cache_note_tags
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
        if not settings or not settings.encryption_enabled:
            return False

        # New scheme: auth_verifier is separate from KEK derivation.
        if getattr(settings, "auth_verifier", None) is not None:
            if settings.auth_salt is None:
                raise RuntimeError("auth_verifier set but auth_salt is NULL")
            stored_iterations = settings.auth_iterations or PW_PBKDF2_ITERATIONS
            candidate = self.hash_password(password, settings.auth_salt, stored_iterations)
            return secrets.compare_digest(candidate, settings.auth_verifier)

        # Legacy scheme: password_hash is PBKDF2 output using the same salt/iters
        # as the KEK, which allows offline unwrap with DB access. This path exists
        # only to support automatic migration on next successful login.
        if not settings.password_hash:
            return False
        if settings.password_salt is None:
            raise RuntimeError("password_hash set but password_salt is NULL")
        stored_iterations = settings.password_iterations or 250_000
        candidate = self.hash_password(password, settings.password_salt, stored_iterations)
        return secrets.compare_digest(candidate, settings.password_hash)

    def check_password_strength(self, password: str) -> bool:
        """Return True when password meets minimal strength requirements."""
        return len(password) > 3

    def has_password(self) -> bool:
        """Return True if password protection is enabled."""
        settings = self.get_settings()
        return settings is not None and bool(settings.encryption_enabled)

    def _is_legacy_password_settings(self, settings: SimpleNamespace) -> bool:
        return (
            getattr(settings, "auth_verifier", None) is None
            and getattr(settings, "kek_salt", None) is None
            and getattr(settings, "password_hash", None) is not None
        )

    def _derive_kek_from_settings(self, password: str, settings: SimpleNamespace) -> bytes:
        if getattr(settings, "kek_salt", None) is not None:
            kek_iterations = settings.kek_iterations or PW_PBKDF2_ITERATIONS
            return self.encryption.derive_master_key(password, settings.kek_salt, kek_iterations)

        if settings.password_salt is None:
            raise RuntimeError("No KEK salt available (neither kek_salt nor password_salt)")
        legacy_iterations = settings.password_iterations or 250_000
        return self.encryption.derive_master_key(password, settings.password_salt, legacy_iterations)

    def unwrap_dek_for_password(self, password: str) -> bytes:
        """Return the decrypted DEK for a verified password.

        If the database is on the legacy scheme, this will migrate settings to the
        split verifier + KEK salts scheme, clearing the legacy password_hash fields.
        """
        settings = self.get_settings()
        if not settings:
            raise RuntimeError("Failed to retrieve settings")
        if not settings.encryption_enabled:
            raise RuntimeError("Encryption is not enabled")

        if settings.encrypted_dek is None or settings.dek_nonce is None or settings.dek_tag is None:
            raise RuntimeError("Encryption enabled but DEK metadata is missing")

        kek = self._derive_kek_from_settings(password, settings)
        dek = self.encryption.decrypt_dek(
            settings.encrypted_dek,
            settings.dek_nonce,
            settings.dek_tag,
            kek,
        )

        if self._is_legacy_password_settings(settings):
            algorithm = settings.encryption_algorithm or "AES-256-GCM"
            self._migrate_legacy_password_settings(password, dek, algorithm)

        return dek

    def _migrate_legacy_password_settings(
        self,
        password: str,
        dek: bytes,
        encryption_algorithm: str,
    ) -> None:
        """Migrate from legacy (password_hash == KEK) to split verifier + KEK salts."""
        auth_salt = self.encryption.generate_salt()
        kek_salt = self.encryption.generate_salt()
        auth_iterations = PW_PBKDF2_ITERATIONS
        kek_iterations = PW_PBKDF2_ITERATIONS

        auth_verifier = self.hash_password(password, auth_salt, auth_iterations)
        kek = self.encryption.derive_master_key(password, kek_salt, kek_iterations)
        encrypted_dek, dek_nonce, dek_tag = self.encryption.encrypt_dek(dek, kek)

        connection = self.db.connection()
        update_password_settings(
            connection,
            auth_verifier=auth_verifier,
            auth_salt=auth_salt,
            auth_iterations=auth_iterations,
            kek_salt=kek_salt,
            kek_iterations=kek_iterations,
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            dek_tag=dek_tag,
            encryption_algorithm=encryption_algorithm,
        )
        self.db.commit()

    def set_password(self, password: str) -> Tuple[bool, str]:
        """Enable password protection by encrypting all existing content."""
        if self.has_password():
            return False, "Password already exists. Use change_password instead."
        if not self.check_password_strength(password):
            return False, "Password is too weak (must be > 3 characters)"

        self.initialize_settings()
        auth_salt = self.encryption.generate_salt()
        kek_salt = self.encryption.generate_salt()
        auth_iterations = PW_PBKDF2_ITERATIONS
        kek_iterations = PW_PBKDF2_ITERATIONS

        auth_verifier = self.hash_password(password, auth_salt, auth_iterations)

        dek = self.encryption.generate_dek()
        kek = self.encryption.derive_master_key(password, kek_salt, kek_iterations)
        encrypted_dek, dek_nonce, dek_tag = self.encryption.encrypt_dek(dek, kek)

        self.encryption.master_key = None
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
                tags = note["tags"]
                if content is None:
                    raise RuntimeError(
                        f"Password setup failed: Note {note_id} has NULL content."
                    )
                if tags is None:
                    raise RuntimeError(
                        f"Password setup failed: Note {note_id} has NULL tags."
                    )

                content_encrypted = note.get("encryption_nonce") is not None or note.get("encryption_tag") is not None
                tags_encrypted = note.get("tags_encryption_nonce") is not None or note.get("tags_encryption_tag") is not None

                if content_encrypted and tags_encrypted:
                    continue
                try:
                    update_payload: dict[str, object] = {}

                    if not content_encrypted:
                        ciphertext_base64, nonce_bytes, tag_bytes = self.encryption.encrypt_for_storage(content)
                        update_payload.update(
                            {
                                "content": ciphertext_base64,
                                "encryption_nonce": nonce_bytes,
                                "encryption_tag": tag_bytes,
                            }
                        )
                        cache_note(note_id, content)

                    if not tags_encrypted:
                        tags_ciphertext, tags_nonce, tags_tag = self.encryption.encrypt_for_storage(tags)
                        update_payload.update(
                            {
                                "tags": tags_ciphertext,
                                "tags_encryption_nonce": tags_nonce,
                                "tags_encryption_tag": tags_tag,
                            }
                        )
                        cache_note_tags(note_id, tags)

                    update_note_fields(connection, note_id, **update_payload)
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
                auth_verifier=auth_verifier,
                auth_salt=auth_salt,
                auth_iterations=auth_iterations,
                kek_salt=kek_salt,
                kek_iterations=kek_iterations,
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
        if not settings:
            raise RuntimeError("App settings missing during password change")

        if settings.kek_salt is not None:
            old_kek_iterations = settings.kek_iterations or PW_PBKDF2_ITERATIONS
            old_kek = self.encryption.derive_master_key(
                current_password,
                settings.kek_salt,
                old_kek_iterations,
            )
        else:
            if settings.password_salt is None:
                raise RuntimeError("Legacy password_salt missing during password change")
            old_kek_iterations = settings.password_iterations or 250_000
            old_kek = self.encryption.derive_master_key(
                current_password,
                settings.password_salt,
                old_kek_iterations,
            )

        dek = self.encryption.decrypt_dek(
            settings.encrypted_dek,
            settings.dek_nonce,
            settings.dek_tag,
            old_kek,
        )

        if iterations is None:
            iterations = PW_PBKDF2_ITERATIONS
        if not (100_000 <= iterations <= 10_000_000):
            return False, "Iterations must be between 100,000 and 10,000,000"

        auth_salt = self.encryption.generate_salt()
        kek_salt = self.encryption.generate_salt()
        auth_iterations = iterations
        kek_iterations = iterations

        auth_verifier = self.hash_password(new_password, auth_salt, auth_iterations)
        new_kek = self.encryption.derive_master_key(new_password, kek_salt, kek_iterations)
        encrypted_dek, dek_nonce, dek_tag = self.encryption.encrypt_dek(dek, new_kek)

        connection = self.db.connection()
        update_password_settings(
            connection,
            auth_verifier=auth_verifier,
            auth_salt=auth_salt,
            auth_iterations=auth_iterations,
            kek_salt=kek_salt,
            kek_iterations=kek_iterations,
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            dek_tag=dek_tag,
            encryption_algorithm=settings.encryption_algorithm or "AES-256-GCM",
        )
        self.db.commit()

        self.encryption.master_key = None
        self.encryption.dek = dek
        return True, "Password changed successfully. Notes remain encrypted with the same key."

    def remove_password(self, current_password: str) -> Tuple[bool, str]:
        """Disable password protection by decrypting notes and clearing settings."""
        if not self.has_password():
            return False, "No password is currently set"
        if not self.verify_password(current_password):
            return False, "Password is incorrect"

        settings = self.get_settings()
        if not settings:
            raise RuntimeError("App settings missing during password removal")

        if settings.kek_salt is not None:
            kek_iterations = settings.kek_iterations or PW_PBKDF2_ITERATIONS
            kek = self.encryption.derive_master_key(
                current_password,
                settings.kek_salt,
                kek_iterations,
            )
        else:
            if settings.password_salt is None:
                raise RuntimeError("Legacy password_salt missing during password removal")
            kek_iterations = settings.password_iterations or 250_000
            kek = self.encryption.derive_master_key(
                current_password,
                settings.password_salt,
                kek_iterations,
            )
        dek = self.encryption.decrypt_dek(
            settings.encrypted_dek,
            settings.dek_nonce,
            settings.dek_tag,
            kek,
        )
        self.encryption.master_key = None
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
                tags = note["tags"]
                tags_nonce = note.get("tags_encryption_nonce")
                tags_tag = note.get("tags_encryption_tag")

                content_encrypted = nonce is not None or tag is not None
                tags_encrypted = tags_nonce is not None or tags_tag is not None
                if not content_encrypted and not tags_encrypted:
                    continue

                if content_encrypted:
                    if nonce is None or tag is None:
                        raise RuntimeError(
                            "Password removal failed: encrypted note has incomplete metadata: "
                            f"note_id={note_id} nonce={nonce is not None} tag={tag is not None}"
                        )
                    if content is None:
                        raise RuntimeError(
                            f"Password removal failed: encrypted note {note_id} has NULL content"
                        )

                if tags_encrypted:
                    if tags_nonce is None or tags_tag is None:
                        raise RuntimeError(
                            "Password removal failed: encrypted tags have incomplete metadata: "
                            f"note_id={note_id} nonce={tags_nonce is not None} tag={tags_tag is not None}"
                        )
                    if tags is None:
                        raise RuntimeError(
                            f"Password removal failed: encrypted note {note_id} has NULL tags"
                        )

                try:
                    update_payload: dict[str, object] = {}

                    if content_encrypted:
                        plaintext = self.encryption.decrypt_from_storage(content, nonce, tag)
                        update_payload.update(
                            {
                                "content": plaintext,
                                "encryption_nonce": None,
                                "encryption_tag": None,
                            }
                        )
                        cache_note(note_id, plaintext)

                    if tags_encrypted:
                        tags_plaintext = self.encryption.decrypt_from_storage(tags, tags_nonce, tags_tag)
                        update_payload.update(
                            {
                                "tags": tags_plaintext,
                                "tags_encryption_nonce": None,
                                "tags_encryption_tag": None,
                            }
                        )
                        cache_note_tags(note_id, tags_plaintext)

                    update_note_fields(connection, note_id, **update_payload)
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
