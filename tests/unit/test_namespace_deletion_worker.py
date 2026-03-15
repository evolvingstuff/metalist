from __future__ import annotations

import signal

import app.services.namespace_deletion_worker as namespace_deletion_worker


def test_stop_process_sends_sigterm_before_sigkill(monkeypatch) -> None:
    wait_results = iter([False, True])
    sent_signals: list[int] = []

    monkeypatch.setattr(
        namespace_deletion_worker,
        "_wait_for_process_exit",
        lambda *, pid, timeout_seconds: next(wait_results),
    )
    monkeypatch.setattr(
        namespace_deletion_worker,
        "_send_signal_if_running",
        lambda *, pid, signal_number: sent_signals.append(signal_number),
    )

    namespace_deletion_worker._stop_process(pid=1234)

    assert sent_signals == [signal.SIGTERM]


def test_stop_process_escalates_to_sigkill(monkeypatch) -> None:
    wait_results = iter([False, False, True])
    sent_signals: list[int] = []

    monkeypatch.setattr(
        namespace_deletion_worker,
        "_wait_for_process_exit",
        lambda *, pid, timeout_seconds: next(wait_results),
    )
    monkeypatch.setattr(
        namespace_deletion_worker,
        "_send_signal_if_running",
        lambda *, pid, signal_number: sent_signals.append(signal_number),
    )

    namespace_deletion_worker._stop_process(pid=1234)

    assert sent_signals == [signal.SIGTERM, signal.SIGKILL]


def test_is_process_running_treats_zombie_as_not_running(monkeypatch) -> None:
    monkeypatch.setattr(namespace_deletion_worker.os, "kill", lambda pid, signal_number: None)
    monkeypatch.setattr(namespace_deletion_worker, "_read_process_state", lambda *, pid: "Z")

    assert namespace_deletion_worker._is_process_running(pid=1234) is False
