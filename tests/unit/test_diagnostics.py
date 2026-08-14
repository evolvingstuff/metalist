from io import StringIO

import pytest

from app.security.authenticated_logging import decrypt_log_record
from app.security.authenticated_logging import decrypt_log_records
from app.services import diagnostics


def test_recycle_direct_append_log_file_keeps_tail_for_oversized_log(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(diagnostics, "_DIRECT_APPEND_LOG_MAX_BYTES", 20)
    monkeypatch.setattr(diagnostics, "_DIRECT_APPEND_LOG_TAIL_BYTES", 8)
    log_path = tmp_path / "namespace-work.log"
    log_path.write_bytes(b"0123456789abcdefghijklmnopqrstuvwxyz")

    recycled = diagnostics.recycle_direct_append_log_file(path=log_path)

    contents = log_path.read_bytes()
    assert recycled is True
    assert contents.endswith(b"stuvwxyz")
    assert b"log compacted" in contents


def test_recycle_direct_append_log_file_leaves_small_log_unchanged(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(diagnostics, "_DIRECT_APPEND_LOG_MAX_BYTES", 100)
    log_path = tmp_path / "namespace-work.log"
    log_path.write_bytes(b"small log")

    recycled = diagnostics.recycle_direct_append_log_file(path=log_path)

    assert recycled is False
    assert log_path.read_bytes() == b"small log"


def test_assert_log_disk_usage_within_bounds_fails_when_total_exceeds_cap(
    tmp_path,
    monkeypatch,
) -> None:
    logs_directory = tmp_path / "logs"
    logs_directory.mkdir()
    (logs_directory / "namespace-work.log").write_bytes(b"1234567890")
    (logs_directory / "work-server.log").write_bytes(b"abcdefghij")
    monkeypatch.setattr(diagnostics, "resolve_runtime_logs_directory", lambda: logs_directory)
    monkeypatch.setattr(diagnostics, "_LOG_DIRECTORY_MAX_BYTES", 15)
    monkeypatch.setattr(diagnostics, "_DIRECT_APPEND_LOG_MAX_BYTES", 100)

    with pytest.raises(RuntimeError, match="Log directory exceeds disk bound"):
        diagnostics.assert_log_disk_usage_within_bounds()


def test_assert_log_disk_usage_within_bounds_fails_when_direct_append_file_stays_large(
    tmp_path,
    monkeypatch,
) -> None:
    logs_directory = tmp_path / "logs"
    logs_directory.mkdir()
    log_path = logs_directory / "namespace-work.log"
    log_path.write_bytes(b"1234567890")
    monkeypatch.setattr(diagnostics, "resolve_runtime_logs_directory", lambda: logs_directory)
    monkeypatch.setattr(diagnostics, "_DIRECT_APPEND_LOG_MAX_BYTES", 5)
    monkeypatch.setattr(diagnostics, "_DIRECT_APPEND_LOG_TAIL_BYTES", 8)
    monkeypatch.setattr(diagnostics, "_LOG_DIRECTORY_MAX_BYTES", 100)

    with pytest.raises(RuntimeError, match="Log file exceeds direct append cap"):
        diagnostics.assert_log_disk_usage_within_bounds()


def test_request_tracking_records_and_removes_active_request() -> None:
    diagnostics.begin_request(
        request_id="abc123",
        method="POST",
        path="/api2/notes/view",
        has_query=False,
        client="127.0.0.1",
        user_agent="pytest",
        started_at=100.0,
    )

    snapshot = diagnostics.snapshot_active_requests()
    assert "abc123" in snapshot
    assert snapshot["abc123"].path == "/api2/notes/view"
    assert snapshot["abc123"].has_query is False
    assert not hasattr(snapshot["abc123"], "query")

    duration_ms = diagnostics.finish_request(request_id="abc123", ended_at=100.25)

    assert duration_ms == 250.0
    assert "abc123" not in diagnostics.snapshot_active_requests()


def test_collect_slow_request_logs_rate_limits_repeated_reports() -> None:
    diagnostics.begin_request(
        request_id="slow1",
        method="PUT",
        path="/api2/notes/root/save",
        has_query=True,
        client="127.0.0.1",
        user_agent="pytest",
        started_at=10.0,
    )

    first_logs = diagnostics.collect_slow_request_logs(
        now=25.0,
        threshold_seconds=10.0,
    )
    repeated_logs = diagnostics.collect_slow_request_logs(
        now=30.0,
        threshold_seconds=10.0,
    )
    later_logs = diagnostics.collect_slow_request_logs(
        now=36.0,
        threshold_seconds=10.0,
    )
    diagnostics.finish_request(request_id="slow1", ended_at=40.0)

    assert len(first_logs) == 1
    assert first_logs[0].request_id == "slow1"
    assert first_logs[0].has_query is True
    assert not hasattr(first_logs[0], "query")
    assert first_logs[0].duration_seconds == 15.0
    assert repeated_logs == []
    assert len(later_logs) == 1


def test_authenticated_logging_encrypts_process_streams_and_diagnostic_sink(
    tmp_path,
    monkeypatch,
) -> None:
    dek = b"a" * 32
    secret = "decrypted note content must never persist as plaintext"
    plaintext_stdout = StringIO()
    plaintext_stderr = StringIO()
    monkeypatch.setattr(diagnostics, "resolve_runtime_logs_directory", lambda: tmp_path)
    monkeypatch.setattr(diagnostics, "_disable_plaintext_fault_logging", lambda: None)
    monkeypatch.setattr(diagnostics, "_enable_plaintext_fault_logging", lambda: None)
    monkeypatch.setattr(diagnostics.sys, "stdout", plaintext_stdout)
    monkeypatch.setattr(diagnostics.sys, "stderr", plaintext_stderr)

    encrypted_path = diagnostics.activate_authenticated_logging(namespace="work", dek=dek)
    try:
        print(secret)
        assert diagnostics._authenticated_log_sink is not None
        diagnostics._authenticated_log_sink.write(secret)
    finally:
        diagnostics.deactivate_authenticated_logging()

    stdout_bytes = plaintext_stdout.getvalue().encode("ascii")
    assert secret.encode("utf-8") not in stdout_bytes
    assert secret.encode("utf-8") not in plaintext_stderr.getvalue().encode("ascii")
    assert secret.encode("utf-8") not in encrypted_path.read_bytes()
    stdout_records = [
        decrypt_log_record(envelope=line, dek=dek)
        for line in stdout_bytes.splitlines()
    ]
    assert secret in stdout_records
    assert secret in decrypt_log_records(path=encrypted_path, dek=dek)
    assert diagnostics.sys.stdout is plaintext_stdout
    assert diagnostics.sys.stderr is plaintext_stderr
