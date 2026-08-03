from __future__ import annotations

from io import BytesIO
from pathlib import Path
import wave

import pytest

from app.config import KDF_TIME_COST
from app.db.file_schema import FILES_TABLE
from app.db.file_schema import SOUNDS_TABLE
from app.db.file_session import begin_file_writer
from app.db.file_session import connect_file_reader
from app.db.schema import initialize_schema
from app.db.session import begin_writer
from app.db.sounds_sql import fetch_sound
from app.models.database import SafeSession
from app.security.encryption import clear_encryption_key, set_encryption_required, set_session_dek
from app.services.auth_service import AuthService
from app.services.client_state_service import save_client_preferences
from app.services.reminders import PERSISTENCE_KEEP_UNTIL_SEEN
from app.services.reminders import REMINDER_STATUS_ACTIVE
from app.services.reminders import SCHEDULE_ONE_TIME
from app.services.reminders import TIME_MODE_DATE_ONLY
from app.services.reminders import reminder_store
from app.services.sound_storage import BUILTIN_DEFAULT_SOUND_ID
from app.services.sound_storage import sound_store

_TEST_SOUND_SECONDS = 0.1


def _wav_bytes(*, seconds: float) -> bytes:
    sample_rate = 8_000
    frame_count = int(sample_rate * seconds)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


@pytest.fixture
def memory_sound_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    with begin_writer() as connection:
        initialize_schema(connection)
    reminder_store.clear_persisted_state_for_tests()
    sound_store.reset()
    with begin_file_writer() as connection:
        connection.execute(f"DELETE FROM {FILES_TABLE}")
        connection.execute(f"DELETE FROM {SOUNDS_TABLE}")
    sound_store.bootstrap(token="")
    try:
        yield
    finally:
        with begin_file_writer() as connection:
            connection.execute(f"DELETE FROM {FILES_TABLE}")
            connection.execute(f"DELETE FROM {SOUNDS_TABLE}")
        sound_store.reset()
        reminder_store.clear_persisted_state_for_tests()
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()


def test_sound_store_bootstrap_includes_non_deletable_default(memory_sound_db) -> None:
    del memory_sound_db

    snapshot = sound_store.list_sounds()

    assert snapshot.sounds[0].id == BUILTIN_DEFAULT_SOUND_ID
    assert snapshot.sounds[0].is_builtin is True
    assert snapshot.uploaded_bytes == 0
    with pytest.raises(ValueError, match="Built-in sounds cannot be deleted"):
        sound_store.delete_sound(sound_id=BUILTIN_DEFAULT_SOUND_ID)


def test_create_sound_persists_and_loads_into_memory(memory_sound_db) -> None:
    del memory_sound_db
    content = _wav_bytes(seconds=_TEST_SOUND_SECONDS)

    record = sound_store.create_sound(
        title="Soft ping",
        original_filename="ping.wav",
        mime_type="audio/wav",
        content_bytes=content,
        token="",
    )

    stored = sound_store.get_sound(sound_id=record.id)
    assert stored.record.title == "Soft ping"
    assert stored.content_bytes == content
    assert sound_store.list_sounds().uploaded_bytes == len(content)

    sound_store.reset()
    sound_store.bootstrap(token="")
    reloaded = sound_store.get_sound(sound_id=record.id)
    assert reloaded.record.title == "Soft ping"
    assert reloaded.content_bytes == content


def test_create_sound_rejects_oversized_library(
    memory_sound_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del memory_sound_db
    content = _wav_bytes(seconds=_TEST_SOUND_SECONDS)
    monkeypatch.setattr("app.services.sound_storage.MAX_SOUND_LIBRARY_BYTES", len(content) + 1)
    sound_store.create_sound(
        title="First",
        original_filename="first.wav",
        mime_type="audio/wav",
        content_bytes=content,
        token="",
    )

    with pytest.raises(ValueError, match="Sound library size limit exceeded"):
        sound_store.create_sound(
            title="Second",
            original_filename="second.wav",
            mime_type="audio/wav",
            content_bytes=content,
            token="",
        )


def test_delete_sound_rejects_reminder_reference(memory_sound_db) -> None:
    del memory_sound_db
    record = sound_store.create_sound(
        title="Selected",
        original_filename="selected.wav",
        mime_type="audio/wav",
        content_bytes=_wav_bytes(seconds=_TEST_SOUND_SECONDS),
        token="",
    )
    reminder_store.create_reminder(
        payload={
            "note_id": None,
            "title": "Sound reminder",
            "attachment_type": "unattached",
            "schedule_kind": SCHEDULE_ONE_TIME,
            "time_mode": TIME_MODE_DATE_ONLY,
            "scheduled_at": None,
            "scheduled_date": "2026-06-08",
            "recurrence_rule": None,
            "persistence_mode": PERSISTENCE_KEEP_UNTIL_SEEN,
            "popup_sound_enabled": True,
            "popup_sound_id": record.id,
            "ack_sound_enabled": False,
            "ack_sound_id": BUILTIN_DEFAULT_SOUND_ID,
            "status": REMINDER_STATUS_ACTIVE,
        },
        token="",
    )

    with pytest.raises(ValueError, match="selected by a reminder"):
        sound_store.delete_sound(sound_id=record.id)


def test_delete_sound_rejects_default_sound_reference(memory_sound_db) -> None:
    del memory_sound_db
    record = sound_store.create_sound(
        title="Default",
        original_filename="default.wav",
        mime_type="audio/wav",
        content_bytes=_wav_bytes(seconds=_TEST_SOUND_SECONDS),
        token="",
    )
    save_client_preferences(
        token="",
        preferences={
            "pref.reminder_default_popup_sound_enabled": "true",
            "pref.reminder_default_popup_sound_id": record.id,
        }
    )

    with pytest.raises(ValueError, match="default popup sound"):
        sound_store.delete_sound(sound_id=record.id)


def test_sound_password_transition_rewrites_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_required(False)
    monkeypatch.setattr(SafeSession, "_db_path", tmp_path / "notes.db")
    SafeSession.use_memory_db()
    sound_store.reset()
    with begin_file_writer() as connection:
        connection.execute(f"DELETE FROM {FILES_TABLE}")
        connection.execute(f"DELETE FROM {SOUNDS_TABLE}")
    sound_store.bootstrap(token="")
    try:
        content = _wav_bytes(seconds=_TEST_SOUND_SECONDS)
        record = sound_store.create_sound(
            title="Transition",
            original_filename="transition.wav",
            mime_type="audio/wav",
            content_bytes=content,
            token="",
        )
        with connect_file_reader() as connection:
            row = fetch_sound(connection, record.id)
        assert row is not None
        assert row["title"] == "Transition"
        assert row["blob_data"] == content

        session = SafeSession()
        try:
            auth = AuthService(session)
            success, message = auth.set_password("aQ7!mZ2#vL9@xR4", KDF_TIME_COST)
            assert success, message

            with connect_file_reader() as connection:
                encrypted_row = fetch_sound(connection, record.id)
            assert encrypted_row is not None
            assert encrypted_row["title"] != "Transition"
            assert isinstance(encrypted_row["title_encryption_nonce"], bytes)
            assert encrypted_row["blob_data"] != content

            set_session_dek(auth.unwrap_dek_for_password("aQ7!mZ2#vL9@xR4"))
            sound_store.reset()
            sound_store.bootstrap(token="")
            assert sound_store.get_sound(sound_id=record.id).content_bytes == content

            success, message = auth.remove_password("aQ7!mZ2#vL9@xR4")
            assert success, message
        finally:
            session.close()

        with connect_file_reader() as connection:
            decrypted_row = fetch_sound(connection, record.id)
        assert decrypted_row is not None
        assert decrypted_row["title"] == "Transition"
        assert decrypted_row["blob_data"] == content
    finally:
        with begin_file_writer() as connection:
            connection.execute(f"DELETE FROM {FILES_TABLE}")
            connection.execute(f"DELETE FROM {SOUNDS_TABLE}")
        sound_store.reset()
        clear_encryption_key()
        set_encryption_required(False)
        SafeSession.use_file_db()
