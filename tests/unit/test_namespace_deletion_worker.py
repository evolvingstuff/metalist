from __future__ import annotations

from types import SimpleNamespace

import app.services.namespace_deletion_worker as namespace_deletion_worker


def _select_posix_process_control(monkeypatch) -> tuple[int, int]:
    terminate_signal = 15
    kill_signal = 9
    monkeypatch.setattr(namespace_deletion_worker.sys, "platform", "linux")
    monkeypatch.setattr(namespace_deletion_worker.signal, "SIGTERM", terminate_signal)
    monkeypatch.setattr(namespace_deletion_worker.signal, "SIGKILL", kill_signal, raising=False)
    return terminate_signal, kill_signal


def test_stop_process_sends_sigterm_before_sigkill(monkeypatch) -> None:
    terminate_signal, _ = _select_posix_process_control(monkeypatch)
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

    assert sent_signals == [terminate_signal]


def test_stop_process_escalates_to_sigkill(monkeypatch) -> None:
    terminate_signal, kill_signal = _select_posix_process_control(monkeypatch)
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

    assert sent_signals == [terminate_signal, kill_signal]


def test_stop_process_uses_windows_process_control(monkeypatch) -> None:
    stopped_pids: list[int] = []
    monkeypatch.setattr(namespace_deletion_worker.sys, "platform", "win32")
    monkeypatch.setattr(
        namespace_deletion_worker,
        "stop_windows_process",
        lambda *, pid: stopped_pids.append(pid),
    )
    monkeypatch.setattr(
        namespace_deletion_worker,
        "_wait_for_process_exit",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("POSIX wait must not run")),
    )

    namespace_deletion_worker._stop_process(pid=1234)

    assert stopped_pids == [1234]


def test_is_process_running_treats_zombie_as_not_running(monkeypatch) -> None:
    monkeypatch.setattr(namespace_deletion_worker.os, "kill", lambda pid, signal_number: None)
    monkeypatch.setattr(namespace_deletion_worker, "_read_process_state", lambda *, pid: "Z")

    assert namespace_deletion_worker._is_process_running(pid=1234) is False


def test_recreate_default_namespace_saves_profile_and_launches(monkeypatch) -> None:
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(
        namespace_deletion_worker,
        "save_namespace_launch_profile",
        lambda **kwargs: events.append(("save", kwargs)),
    )
    monkeypatch.setattr(
        namespace_deletion_worker,
        "open_or_launch_namespace",
        lambda **kwargs: events.append(("launch", kwargs)),
    )
    args = SimpleNamespace(
        replacement_namespace="default",
        replacement_port=8002,
        replacement_https_port=8445,
    )

    namespace_deletion_worker._recreate_default_namespace(args=args)

    assert events[0] == (
        "save",
        {
            "namespace": "default",
            "port": 8002,
            "https_port": 8445,
            "mcp_port": None,
        },
    )
    assert events[1][0] == "launch"
    assert events[1][1]["current_namespace"] is None
    assert events[1][1]["namespace"] == "default"
