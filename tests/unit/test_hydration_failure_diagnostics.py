from __future__ import annotations

from concurrent.futures import Future
import logging

from app.api.routes import auth as auth_routes


def test_hydration_worker_failure_keeps_type_without_exception_message(
    monkeypatch,
    caplog,
) -> None:
    captured_messages: list[str] = []
    monkeypatch.setattr(auth_routes.hydration_state, "fail", captured_messages.append)
    future: Future[None] = Future()
    future.set_exception(AssertionError())

    with caplog.at_level(logging.ERROR, logger=auth_routes.__name__):
        auth_routes._on_hydration_done(future)

    assert captured_messages == ["AssertionError"]
    assert "Hydration worker failed: AssertionError" in caplog.text
    assert "AssertionError" in caplog.text
