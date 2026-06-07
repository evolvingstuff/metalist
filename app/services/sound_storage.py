"""Memory-first reusable sound storage backed by the files database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
from threading import RLock
import uuid
import wave

from mutagen import File as read_audio_metadata

from app.db.file_session import begin_file_writer, connect_file_reader
from app.db.sounds_sql import (
    delete_sound as delete_sound_row,
    fetch_all_sounds,
    insert_sound,
    update_sound_storage_fields,
)
from app.security.encryption import (
    get_encryption_service,
    get_encryption_service_with_token,
    is_encryption_required,
)
from app.services.reminders import reminder_store

BUILTIN_DEFAULT_SOUND_ID = "builtin.default_chime"
MAX_SOUND_BYTES = 2 * 1024 * 1024
MAX_SOUND_DURATION_SECONDS = 10.0
MAX_SOUND_LIBRARY_BYTES = 50 * 1024 * 1024

ALLOWED_SOUND_MIME_TYPES = frozenset(
    {
        "audio/aac",
        "audio/flac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-wav",
    }
)


@dataclass(frozen=True)
class SoundRecord:
    id: str
    title: str
    original_filename: str
    mime_type: str
    size_bytes: int
    duration_seconds: float
    is_builtin: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredSound:
    record: SoundRecord
    content_bytes: bytes


@dataclass(frozen=True)
class SoundLibrarySnapshot:
    sounds: list[SoundRecord]
    uploaded_bytes: int
    max_uploaded_bytes: int
    max_sound_bytes: int
    max_duration_seconds: float


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_builtin_chime() -> bytes:
    sample_rate = 44_100
    duration_seconds = 0.42
    frame_count = int(sample_rate * duration_seconds)
    amplitude = 12_000
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            elapsed = index / sample_rate
            envelope = max(0.0, 1.0 - elapsed / duration_seconds)
            tone = math.sin(2.0 * math.pi * 659.25 * elapsed)
            overtone = 0.45 * math.sin(2.0 * math.pi * 987.77 * elapsed)
            sample = int(amplitude * envelope * (tone + overtone) / 1.45)
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


_BUILTIN_CHIME_BYTES = _generate_builtin_chime()
_BUILTIN_CREATED_AT = datetime(2000, 1, 1, tzinfo=timezone.utc)
_BUILTIN_DEFAULT_SOUND = StoredSound(
    record=SoundRecord(
        id=BUILTIN_DEFAULT_SOUND_ID,
        title="Default chime",
        original_filename="default-chime.wav",
        mime_type="audio/wav",
        size_bytes=len(_BUILTIN_CHIME_BYTES),
        duration_seconds=0.42,
        is_builtin=True,
        created_at=_BUILTIN_CREATED_AT,
        updated_at=_BUILTIN_CREATED_AT,
    ),
    content_bytes=_BUILTIN_CHIME_BYTES,
)


class SoundStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._uploaded_sounds_by_id: dict[str, StoredSound] = {}
        self._loaded = False

    @property
    def loaded(self) -> bool:
        with self._lock:
            return self._loaded

    def reset(self) -> None:
        with self._lock:
            self._uploaded_sounds_by_id = {}
            self._loaded = False

    def bootstrap(self, *, token: str) -> None:
        if not isinstance(token, str):
            raise TypeError("token must be a string")
        with begin_file_writer():
            pass
        encryption_service = _resolve_encryption_service(token)
        uploaded_sounds_by_id: dict[str, StoredSound] = {}
        with connect_file_reader() as connection:
            rows = fetch_all_sounds(connection)
        for row in rows:
            stored_sound = _stored_sound_from_row(
                row=row,
                encryption_service=encryption_service,
            )
            uploaded_sounds_by_id[stored_sound.record.id] = stored_sound
        with self._lock:
            self._uploaded_sounds_by_id = uploaded_sounds_by_id
            self._loaded = True

    def list_sounds(self) -> SoundLibrarySnapshot:
        with self._lock:
            self._assert_loaded()
            uploaded = sorted(
                self._uploaded_sounds_by_id.values(),
                key=lambda stored: (stored.record.created_at, stored.record.title.lower(), stored.record.id),
            )
            sounds = [_BUILTIN_DEFAULT_SOUND.record]
            sounds.extend(stored.record for stored in uploaded)
            uploaded_bytes = sum(stored.record.size_bytes for stored in uploaded)
        return SoundLibrarySnapshot(
            sounds=sounds,
            uploaded_bytes=uploaded_bytes,
            max_uploaded_bytes=MAX_SOUND_LIBRARY_BYTES,
            max_sound_bytes=MAX_SOUND_BYTES,
            max_duration_seconds=MAX_SOUND_DURATION_SECONDS,
        )

    def get_sound(self, *, sound_id: str) -> StoredSound:
        if not isinstance(sound_id, str) or sound_id == "":
            raise TypeError("sound_id must be a non-empty string")
        if sound_id == BUILTIN_DEFAULT_SOUND_ID:
            return _BUILTIN_DEFAULT_SOUND
        with self._lock:
            self._assert_loaded()
            stored = self._uploaded_sounds_by_id.get(sound_id)
            if stored is None:
                raise KeyError(f"Sound not found: {sound_id}")
            return stored

    def create_sound(
        self,
        *,
        title: str,
        original_filename: str,
        mime_type: str,
        content_bytes: bytes,
        token: str,
    ) -> SoundRecord:
        if not isinstance(token, str):
            raise TypeError("token must be a string")
        with self._lock:
            self._assert_loaded()
            existing_uploaded_bytes = sum(
                stored.record.size_bytes for stored in self._uploaded_sounds_by_id.values()
            )
        normalized_title = _normalize_title(title)
        normalized_filename = _normalize_original_filename(original_filename)
        normalized_mime_type = _normalize_mime_type(mime_type)
        _validate_content_size(content_bytes)
        duration_seconds = _read_audio_duration_seconds(content_bytes)
        _validate_duration(duration_seconds)
        if existing_uploaded_bytes + len(content_bytes) > MAX_SOUND_LIBRARY_BYTES:
            raise ValueError(
                "Sound library size limit exceeded: "
                f"max={MAX_SOUND_LIBRARY_BYTES} requested={existing_uploaded_bytes + len(content_bytes)}"
            )

        now = _utc_now()
        record = SoundRecord(
            id=_generate_sound_id(),
            title=normalized_title,
            original_filename=normalized_filename,
            mime_type=normalized_mime_type,
            size_bytes=len(content_bytes),
            duration_seconds=duration_seconds,
            is_builtin=False,
            created_at=now,
            updated_at=now,
        )
        stored = StoredSound(record=record, content_bytes=content_bytes)
        encryption_service = _resolve_encryption_service(token)
        with begin_file_writer() as connection:
            _insert_stored_sound(
                connection=connection,
                stored_sound=stored,
                encryption_service=encryption_service,
            )
        with self._lock:
            self._uploaded_sounds_by_id[record.id] = stored
        return record

    def update_sound_title(self, *, sound_id: str, title: str, token: str) -> SoundRecord:
        if not isinstance(token, str):
            raise TypeError("token must be a string")
        if sound_id == BUILTIN_DEFAULT_SOUND_ID:
            raise ValueError("Built-in sounds cannot be renamed")
        normalized_title = _normalize_title(title)
        with self._lock:
            self._assert_loaded()
            current = self._uploaded_sounds_by_id.get(sound_id)
            if current is None:
                raise KeyError(f"Sound not found: {sound_id}")
            updated_record = SoundRecord(
                id=current.record.id,
                title=normalized_title,
                original_filename=current.record.original_filename,
                mime_type=current.record.mime_type,
                size_bytes=current.record.size_bytes,
                duration_seconds=current.record.duration_seconds,
                is_builtin=False,
                created_at=current.record.created_at,
                updated_at=_utc_now(),
            )
            updated = StoredSound(record=updated_record, content_bytes=current.content_bytes)
        encryption_service = _resolve_encryption_service(token)
        with begin_file_writer() as connection:
            _update_stored_sound(
                connection=connection,
                stored_sound=updated,
                encryption_service=encryption_service,
            )
        with self._lock:
            self._uploaded_sounds_by_id[sound_id] = updated
        return updated.record

    def delete_sound(self, *, sound_id: str) -> None:
        if sound_id == BUILTIN_DEFAULT_SOUND_ID:
            raise ValueError("Built-in sounds cannot be deleted")
        if not isinstance(sound_id, str) or sound_id == "":
            raise TypeError("sound_id must be a non-empty string")
        _assert_sound_not_selected(sound_id)
        with self._lock:
            self._assert_loaded()
            if sound_id not in self._uploaded_sounds_by_id:
                raise KeyError(f"Sound not found: {sound_id}")
        with begin_file_writer() as connection:
            deleted_count = delete_sound_row(connection, sound_id)
        if deleted_count != 1:
            raise RuntimeError(f"Sound delete removed unexpected row count: {deleted_count}")
        with self._lock:
            del self._uploaded_sounds_by_id[sound_id]

    def _assert_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("Sound store is not loaded")


def encrypt_all_sounds_for_active_dek(*, encryption_service: object) -> int:
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError("Sound encryption migration requires an active DEK")
    rewritten_count = 0
    with begin_file_writer() as connection:
        rows = fetch_all_sounds(connection)
        for row in rows:
            if _row_is_fully_encrypted(row):
                continue
            _rewrite_sound_row(
                connection=connection,
                row=row,
                decrypt_encryption_service=service,
                encrypt_encryption_service=service,
            )
            rewritten_count += 1
    return rewritten_count


def decrypt_all_sounds_for_plaintext(*, encryption_service: object) -> int:
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError("Sound decryption migration requires an active DEK")
    rewritten_count = 0
    with begin_file_writer() as connection:
        rows = fetch_all_sounds(connection)
        for row in rows:
            if _row_is_fully_plaintext(row):
                continue
            _rewrite_sound_row(
                connection=connection,
                row=row,
                decrypt_encryption_service=service,
                encrypt_encryption_service=None,
            )
            rewritten_count += 1
    return rewritten_count


def _generate_sound_id() -> str:
    for _ in range(100):
        candidate = str(uuid.uuid4())
        with sound_store._lock:
            exists = candidate in sound_store._uploaded_sounds_by_id
        if not exists:
            return candidate
    raise RuntimeError("Failed to generate a unique sound UUID")


def _normalize_title(title: str) -> str:
    if not isinstance(title, str):
        raise TypeError("title must be a string")
    normalized = title.strip()
    if normalized == "":
        raise ValueError("Sound title is required")
    if len(normalized) > 120:
        raise ValueError("Sound title must be 120 characters or fewer")
    return normalized


def _normalize_original_filename(original_filename: str) -> str:
    if not isinstance(original_filename, str) or original_filename == "":
        raise ValueError("Uploaded sound must include a filename")
    normalized = Path(original_filename).name
    if normalized == "":
        raise ValueError("Uploaded sound filename must resolve to a basename")
    return normalized


def _normalize_mime_type(mime_type: str) -> str:
    if not isinstance(mime_type, str):
        raise TypeError("mime_type must be a string")
    normalized = mime_type.strip().lower()
    if normalized == "":
        raise ValueError("Uploaded sound must include a MIME type")
    if normalized not in ALLOWED_SOUND_MIME_TYPES:
        raise ValueError(f"Unsupported sound MIME type: {mime_type}")
    return normalized


def _validate_content_size(content_bytes: bytes) -> None:
    if not isinstance(content_bytes, bytes):
        raise TypeError(f"content_bytes must be bytes, got {type(content_bytes)}")
    if len(content_bytes) == 0:
        raise ValueError("Uploaded sound must not be empty")
    if len(content_bytes) > MAX_SOUND_BYTES:
        raise ValueError(f"Sound file exceeds {MAX_SOUND_BYTES} byte limit")


def _read_audio_duration_seconds(content_bytes: bytes) -> float:
    metadata = read_audio_metadata(fileobj=BytesIO(content_bytes))
    if metadata is None:
        raise ValueError("Uploaded file is not a supported audio file")
    info = getattr(metadata, "info", None)
    length = getattr(info, "length", None)
    if not isinstance(length, (float, int)):
        raise ValueError("Uploaded audio duration could not be read")
    duration = float(length)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Uploaded audio duration is invalid")
    return duration


def _validate_duration(duration_seconds: float) -> None:
    if not isinstance(duration_seconds, float):
        raise TypeError("duration_seconds must be a float")
    if duration_seconds > MAX_SOUND_DURATION_SECONDS:
        raise ValueError(
            "Sound duration exceeds limit: "
            f"max={MAX_SOUND_DURATION_SECONDS:.1f}s actual={duration_seconds:.2f}s"
        )


def _sound_metadata_json(record: SoundRecord) -> str:
    metadata = {
        "original_filename": record.original_filename,
        "mime_type": record.mime_type,
        "size_bytes": record.size_bytes,
        "duration_seconds": record.duration_seconds,
    }
    return json.dumps(metadata, separators=(",", ":"), ensure_ascii=False)


def _parse_sound_metadata(metadata_json: str, *, sound_id: str) -> dict[str, object]:
    metadata = json.loads(metadata_json)
    if not isinstance(metadata, dict):
        raise TypeError(f"sounds.metadata_json must decode to an object for sound {sound_id}")
    required = ("original_filename", "mime_type", "size_bytes", "duration_seconds")
    for key in required:
        if key not in metadata:
            raise TypeError(f"sounds.metadata_json {key} missing for sound {sound_id}")
    original_filename = metadata["original_filename"]
    mime_type = metadata["mime_type"]
    size_bytes = metadata["size_bytes"]
    duration_seconds = metadata["duration_seconds"]
    if not isinstance(original_filename, str) or original_filename == "":
        raise TypeError(f"sounds.metadata_json original_filename invalid for sound {sound_id}")
    if not isinstance(mime_type, str) or mime_type == "":
        raise TypeError(f"sounds.metadata_json mime_type invalid for sound {sound_id}")
    if not isinstance(size_bytes, int) or size_bytes < 1:
        raise TypeError(f"sounds.metadata_json size_bytes invalid for sound {sound_id}")
    if not isinstance(duration_seconds, (float, int)) or float(duration_seconds) <= 0:
        raise TypeError(f"sounds.metadata_json duration_seconds invalid for sound {sound_id}")
    return {
        "original_filename": original_filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "duration_seconds": float(duration_seconds),
    }


def _stored_sound_from_row(*, row: dict[str, object], encryption_service: object) -> StoredSound:
    sound_id = row["id"]
    if not isinstance(sound_id, str) or sound_id == "":
        raise TypeError(f"sounds.id must be a non-empty string, got {sound_id!r}")
    title = _decrypt_text_field(
        encryption_service=encryption_service,
        value=row["title"],
        nonce=row["title_encryption_nonce"],
        tag=row["title_encryption_tag"],
        field_name="title",
        sound_id=sound_id,
    )
    metadata_json = _decrypt_text_field(
        encryption_service=encryption_service,
        value=row["metadata_json"],
        nonce=row["metadata_encryption_nonce"],
        tag=row["metadata_encryption_tag"],
        field_name="metadata_json",
        sound_id=sound_id,
    )
    content_bytes = _decrypt_blob_field(
        encryption_service=encryption_service,
        value=row["blob_data"],
        nonce=row["blob_encryption_nonce"],
        tag=row["blob_encryption_tag"],
        field_name="blob_data",
        sound_id=sound_id,
    )
    metadata = _parse_sound_metadata(metadata_json, sound_id=sound_id)
    created_at = row["created_at"]
    updated_at = row["updated_at"]
    if not isinstance(created_at, datetime):
        raise TypeError(f"sounds.created_at must be datetime for sound {sound_id}")
    if not isinstance(updated_at, datetime):
        raise TypeError(f"sounds.updated_at must be datetime for sound {sound_id}")
    record = SoundRecord(
        id=sound_id,
        title=title,
        original_filename=metadata["original_filename"],
        mime_type=metadata["mime_type"],
        size_bytes=metadata["size_bytes"],
        duration_seconds=metadata["duration_seconds"],
        is_builtin=False,
        created_at=created_at,
        updated_at=updated_at,
    )
    if len(content_bytes) != record.size_bytes:
        raise RuntimeError(
            f"Sound blob size mismatch: sound_id={sound_id} "
            f"metadata={record.size_bytes} blob={len(content_bytes)}"
        )
    return StoredSound(record=record, content_bytes=content_bytes)


def _insert_stored_sound(*, connection, stored_sound: StoredSound, encryption_service: object) -> None:
    storage = _encode_stored_sound(stored_sound=stored_sound, encryption_service=encryption_service)
    insert_sound(connection, **storage)


def _update_stored_sound(*, connection, stored_sound: StoredSound, encryption_service: object) -> None:
    storage = _encode_stored_sound(stored_sound=stored_sound, encryption_service=encryption_service)
    del storage["created_at"]
    update_sound_storage_fields(connection, **storage)


def _encode_stored_sound(*, stored_sound: StoredSound, encryption_service: object) -> dict[str, object]:
    record = stored_sound.record
    title, title_nonce, title_tag = _encrypt_text_for_storage(
        encryption_service=encryption_service,
        plaintext=record.title,
    )
    metadata_json, metadata_nonce, metadata_tag = _encrypt_text_for_storage(
        encryption_service=encryption_service,
        plaintext=_sound_metadata_json(record),
    )
    blob_data, blob_nonce, blob_tag = _encrypt_bytes_for_storage(
        encryption_service=encryption_service,
        plaintext=stored_sound.content_bytes,
    )
    return {
        "sound_id": record.id,
        "title": title,
        "title_encryption_nonce": title_nonce,
        "title_encryption_tag": title_tag,
        "metadata_json": metadata_json,
        "metadata_encryption_nonce": metadata_nonce,
        "metadata_encryption_tag": metadata_tag,
        "blob_data": blob_data,
        "blob_encryption_nonce": blob_nonce,
        "blob_encryption_tag": blob_tag,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _rewrite_sound_row(
    *,
    connection,
    row: dict[str, object],
    decrypt_encryption_service: object,
    encrypt_encryption_service: object | None,
) -> None:
    stored = _stored_sound_from_row(row=row, encryption_service=decrypt_encryption_service)
    if encrypt_encryption_service is None:
        update_sound_storage_fields(
            connection,
            sound_id=stored.record.id,
            title=stored.record.title,
            title_encryption_nonce=None,
            title_encryption_tag=None,
            metadata_json=_sound_metadata_json(stored.record),
            metadata_encryption_nonce=None,
            metadata_encryption_tag=None,
            blob_data=stored.content_bytes,
            blob_encryption_nonce=None,
            blob_encryption_tag=None,
            updated_at=_utc_now(),
        )
        return
    _update_stored_sound(
        connection=connection,
        stored_sound=stored,
        encryption_service=encrypt_encryption_service,
    )


def _field_has_encryption(*, nonce: object, tag: object, sound_id: object, field_name: str) -> bool:
    if nonce is None and tag is None:
        return False
    if not isinstance(nonce, bytes) or not isinstance(tag, bytes):
        raise RuntimeError(
            "Encrypted sound field metadata invalid: "
            f"sound_id={sound_id} field={field_name} nonce={nonce is not None} tag={tag is not None}"
        )
    return True


def _row_is_fully_plaintext(row: dict[str, object]) -> bool:
    return (
        _field_has_encryption(
            nonce=row["title_encryption_nonce"],
            tag=row["title_encryption_tag"],
            sound_id=row["id"],
            field_name="title",
        )
        is False
        and _field_has_encryption(
            nonce=row["metadata_encryption_nonce"],
            tag=row["metadata_encryption_tag"],
            sound_id=row["id"],
            field_name="metadata_json",
        )
        is False
        and _field_has_encryption(
            nonce=row["blob_encryption_nonce"],
            tag=row["blob_encryption_tag"],
            sound_id=row["id"],
            field_name="blob_data",
        )
        is False
    )


def _row_is_fully_encrypted(row: dict[str, object]) -> bool:
    return (
        _field_has_encryption(
            nonce=row["title_encryption_nonce"],
            tag=row["title_encryption_tag"],
            sound_id=row["id"],
            field_name="title",
        )
        is True
        and _field_has_encryption(
            nonce=row["metadata_encryption_nonce"],
            tag=row["metadata_encryption_tag"],
            sound_id=row["id"],
            field_name="metadata_json",
        )
        is True
        and _field_has_encryption(
            nonce=row["blob_encryption_nonce"],
            tag=row["blob_encryption_tag"],
            sound_id=row["id"],
            field_name="blob_data",
        )
        is True
    )


def _resolve_encryption_service(token: str):
    service = None
    if token != "":
        service = get_encryption_service_with_token(token)
    if service is None:
        service = get_encryption_service()
    return service


def _coerce_encryption_service(encryption_service: object):
    if encryption_service is None:
        return None
    dek = getattr(encryption_service, "dek", None)
    if not isinstance(dek, bytes):
        return None
    return encryption_service


def _encrypt_text_for_storage(
    *,
    encryption_service: object,
    plaintext: str,
) -> tuple[str, bytes | None, bytes | None]:
    if not isinstance(plaintext, str):
        raise TypeError(f"plaintext must be a string, got {type(plaintext)}")
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        if is_encryption_required():
            raise RuntimeError("Encryption is required but no DEK is available")
        return plaintext, None, None
    return service.encrypt_for_storage(plaintext)


def _encrypt_bytes_for_storage(
    *,
    encryption_service: object,
    plaintext: bytes,
) -> tuple[bytes, bytes | None, bytes | None]:
    if not isinstance(plaintext, bytes):
        raise TypeError(f"plaintext must be bytes, got {type(plaintext)}")
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        if is_encryption_required():
            raise RuntimeError("Encryption is required but no DEK is available")
        return plaintext, None, None
    return service.encrypt_bytes_for_storage(plaintext)


def _decrypt_text_field(
    *,
    encryption_service: object,
    value: object,
    nonce: object,
    tag: object,
    field_name: str,
    sound_id: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"sounds.{field_name} must be a string for sound {sound_id}")
    if nonce is None and tag is None:
        return value
    if (nonce is None) != (tag is None):
        raise RuntimeError(
            "Encrypted sound text metadata missing: "
            f"sound_id={sound_id} field={field_name} nonce={nonce is not None} tag={tag is not None}"
        )
    if not isinstance(nonce, bytes) or not isinstance(tag, bytes):
        raise RuntimeError(
            f"Encrypted sound text metadata invalid: sound_id={sound_id} field={field_name}"
        )
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError(f"Encrypted sound metadata requires an active DEK: sound_id={sound_id}")
    return service.decrypt_from_storage(value, nonce, tag)


def _decrypt_blob_field(
    *,
    encryption_service: object,
    value: object,
    nonce: object,
    tag: object,
    field_name: str,
    sound_id: str,
) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError(f"sounds.{field_name} must be bytes for sound {sound_id}")
    if nonce is None and tag is None:
        return value
    if (nonce is None) != (tag is None):
        raise RuntimeError(
            "Encrypted sound blob metadata missing: "
            f"sound_id={sound_id} field={field_name} nonce={nonce is not None} tag={tag is not None}"
        )
    if not isinstance(nonce, bytes) or not isinstance(tag, bytes):
        raise RuntimeError(
            f"Encrypted sound blob metadata invalid: sound_id={sound_id} field={field_name}"
        )
    service = _coerce_encryption_service(encryption_service)
    if service is None:
        raise RuntimeError(f"Encrypted sound blob requires an active DEK: sound_id={sound_id}")
    return service.decrypt_bytes_from_storage(value, nonce, tag)


def _assert_sound_not_selected(sound_id: str) -> None:
    if reminder_store.sound_is_referenced(sound_id=sound_id):
        raise ValueError("Sound is selected by a reminder; choose another sound before deleting it")


sound_store = SoundStore()
