from datetime import datetime, timedelta, timezone

import pytest

from app.services.tokens import TokenService


class FrozenDatetime(datetime):
    """Deterministic datetime replacement."""

    current = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current
        return cls.current.astimezone(tz)


@pytest.fixture
def service(monkeypatch):
    FrozenDatetime.current = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    svc = TokenService()

    import app.services.tokens as tokens_module
    monkeypatch.setattr(tokens_module, "datetime", FrozenDatetime)
    monkeypatch.setattr(tokens_module, "timedelta", timedelta)

    return svc


def advance(minutes):
    FrozenDatetime.current += timedelta(minutes=minutes)


def test_create_and_verify_token(service):
    token = service.create_token("client-info")
    assert service.verify_token(token) is True
    assert service.get_token_info(token)["client_info"] == "client-info"


def test_token_expiry(service):
    token = service.create_token("client-info")
    assert service.verify_token(token) is True

    advance(31)
    assert service.verify_token(token) is False


def test_refresh_extends_expiry(service):
    token = service.create_token("client-info")
    advance(20)
    assert service.refresh_token(token) == token

    advance(20)
    assert service.verify_token(token) is True


def test_revoke_and_cleanup(service):
    token = service.create_token("client-info")
    assert service.revoke_token(token) is True
    assert service.verify_token(token) is False

    t1 = service.create_token("client-1")
    t2 = service.create_token("client-2")
    assert service.verify_token(t1)
    assert service.verify_token(t2)

    advance(61)
    removed = service.cleanup_expired_tokens()
    assert removed >= 2
    assert service.tokens == {}


def test_list_active_sessions(service):
    service.create_token("client-info")
    sessions = service.list_active_sessions()
    assert len(sessions) == 1
    assert sessions[0]["client_info"] == "client-info"
