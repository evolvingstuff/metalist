from __future__ import annotations

from app.services.login_rate_limit import LoginRateLimiter


def test_rate_limiter_blocks_after_max_attempts(monkeypatch) -> None:
    clock = {"now": 100.0}

    def fake_now() -> float:
        return clock["now"]

    monkeypatch.setattr("app.services.login_rate_limit.time.monotonic", fake_now)

    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, block_seconds=120)
    key = "ip:127.0.0.1"

    assert limiter.check_allowed(key) == (True, 0)
    limiter.record_failure(key)
    limiter.record_failure(key)
    limiter.record_failure(key)

    allowed, retry_after = limiter.check_allowed(key)
    assert allowed is False
    assert retry_after == 120

    clock["now"] = 221.0
    assert limiter.check_allowed(key) == (True, 0)


def test_rate_limiter_attempt_window_expires(monkeypatch) -> None:
    clock = {"now": 100.0}

    def fake_now() -> float:
        return clock["now"]

    monkeypatch.setattr("app.services.login_rate_limit.time.monotonic", fake_now)

    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, block_seconds=120)
    key = "ip:127.0.0.1"

    limiter.record_failure(key)
    clock["now"] = 161.0
    limiter.record_failure(key)
    assert limiter.check_allowed(key) == (True, 0)


def test_rate_limiter_success_clears_state(monkeypatch) -> None:
    clock = {"now": 100.0}

    def fake_now() -> float:
        return clock["now"]

    monkeypatch.setattr("app.services.login_rate_limit.time.monotonic", fake_now)

    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, block_seconds=120)
    key = "ip:127.0.0.1"

    limiter.record_failure(key)
    limiter.record_success(key)
    assert limiter.check_allowed(key) == (True, 0)
