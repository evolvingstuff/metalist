from __future__ import annotations

from pathlib import Path
from io import StringIO

from app.security.authenticated_logging import EncryptedLogSink
from app.security.authenticated_logging import EncryptedTextStream
from app.security.authenticated_logging import decrypt_log_record
from app.security.authenticated_logging import decrypt_log_records


def test_encrypted_log_sink_never_persists_plaintext(tmp_path: Path) -> None:
    log_path = tmp_path / "default-server.auth.log.enc"
    dek = b"l" * 32
    secret = "private note body: routing number 021000021"
    sink = EncryptedLogSink(path=log_path, dek=dek)

    sink.write(secret)
    sink.close()

    persisted = log_path.read_bytes()
    assert secret.encode("utf-8") not in persisted
    assert decrypt_log_records(path=log_path, dek=dek) == [secret]


def test_encrypted_log_sink_uses_a_fresh_nonce_for_identical_records(tmp_path: Path) -> None:
    log_path = tmp_path / "default-server.auth.log.enc"
    dek = b"n" * 32
    sink = EncryptedLogSink(path=log_path, dek=dek)

    sink.write("same record")
    sink.write("same record")
    sink.close()

    encrypted_lines = log_path.read_bytes().splitlines()
    assert len(encrypted_lines) == 2
    assert encrypted_lines[0] != encrypted_lines[1]
    assert decrypt_log_records(path=log_path, dek=dek) == ["same record", "same record"]


def test_encrypted_log_file_is_owner_only(tmp_path: Path) -> None:
    log_path = tmp_path / "default-server.auth.log.enc"
    sink = EncryptedLogSink(path=log_path, dek=b"p" * 32)

    sink.write("record")
    sink.close()

    assert log_path.stat().st_mode & 0o777 == 0o600


def test_authenticated_stdout_stream_never_writes_plaintext() -> None:
    destination = StringIO()
    dek = b"s" * 32
    secret = "decrypted runtime value"
    stream = EncryptedTextStream(destination=destination, dek=dek)

    stream.write(secret)

    persisted = destination.getvalue()
    assert secret not in persisted
    assert decrypt_log_record(envelope=persisted.encode("ascii"), dek=dek) == secret
