from app.services.auth import AuthService
from app.services.maintenance_mode import maintenance_service
from app.core.config import PW_PBKDF2_ITERATIONS
from tests.unit.common import db  # noqa: F401


def test_set_password_enables_authentication(db):
    auth = AuthService(db)

    success, message = auth.set_password("secret123")
    assert success, message
    assert auth.has_password() is True
    assert auth.verify_password("secret123") is True
    assert auth.verify_password("wrong") is False

    settings = auth.get_settings()
    assert settings.password_iterations == PW_PBKDF2_ITERATIONS
    assert settings.encryption_enabled is True
    assert maintenance_service.is_active() is False


def test_change_password_updates_iterations(db):
    auth = AuthService(db)
    auth.set_password("secret123")

    success, message = auth.change_password("secret123", "newpass456", iterations=200_000)
    assert success, message
    assert auth.verify_password("newpass456") is True
    assert auth.verify_password("secret123") is False

    settings = auth.get_settings()
    assert settings.password_iterations == 200_000
    assert settings.encryption_enabled is True
