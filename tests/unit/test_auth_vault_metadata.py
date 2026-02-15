from __future__ import annotations

import pytest

from app.config import (
    KDF_ALGORITHM,
    KDF_MEMORY_COST_KIB,
    KDF_PARALLELISM,
    KDF_TIME_COST,
    VAULT_VERSION,
)
from app.db.session import begin_writer
from app.db.settings_sql import fetch_settings
from app.models.database import SafeSession
from app.security.encryption import set_encryption_required
from app.services.auth_service import AuthService


def test_set_password_persists_vault_metadata() -> None:
    set_encryption_required(False)
    SafeSession.use_memory_db()
    try:
        session = SafeSession()
        try:
            auth = AuthService(session)
            success, message = auth.set_password("abcd", KDF_TIME_COST)
            assert success, message

            with SafeSession.allow_reads("tests:auth_vault_metadata:fetch_settings"):
                settings = fetch_settings(session.connection())
            assert settings is not None
            assert settings["encryption_enabled"] is True
            assert settings["vault_version"] == VAULT_VERSION
            assert settings["kdf_algorithm"] == KDF_ALGORITHM
            assert settings["auth_iterations"] == KDF_TIME_COST
            assert settings["kek_iterations"] == KDF_TIME_COST
            assert settings["kdf_memory_cost_kib"] == KDF_MEMORY_COST_KIB
            assert settings["kdf_parallelism"] == KDF_PARALLELISM

            assert auth.verify_password("abcd") is True
            dek = auth.unwrap_dek_for_password("abcd")
            assert len(dek) == 32
        finally:
            session.close()
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_verify_password_fails_for_unsupported_kdf_profile() -> None:
    set_encryption_required(False)
    SafeSession.use_memory_db()
    try:
        session = SafeSession()
        try:
            auth = AuthService(session)
            success, message = auth.set_password("abcd", KDF_TIME_COST)
            assert success, message

            with begin_writer() as connection:
                connection.execute(
                    """
                    UPDATE app_settings
                    SET kdf_algorithm = ?
                    WHERE id = 1
                    """,
                    ("UNSUPPORTED-KDF",),
                )

            with pytest.raises(RuntimeError, match="Unsupported kdf_algorithm"):
                auth.verify_password("abcd")
        finally:
            session.close()
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_verify_password_fails_when_kdf_memory_metadata_missing() -> None:
    set_encryption_required(False)
    SafeSession.use_memory_db()
    try:
        session = SafeSession()
        try:
            auth = AuthService(session)
            success, message = auth.set_password("abcd", KDF_TIME_COST)
            assert success, message

            with begin_writer() as connection:
                connection.execute(
                    """
                    UPDATE app_settings
                    SET kdf_memory_cost_kib = NULL
                    WHERE id = 1
                    """,
                    (),
                )

            with pytest.raises(RuntimeError, match="kdf_memory_cost_kib is NULL"):
                auth.verify_password("abcd")
        finally:
            session.close()
    finally:
        set_encryption_required(False)
        SafeSession.use_file_db()
