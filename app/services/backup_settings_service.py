from __future__ import annotations

from datetime import datetime, timezone
import json

from app.db.backup_settings_sql import fetch_backup_settings_row, upsert_backup_settings_row
from app.db.session import begin_writer
from app.models.database import SafeSession
from app.security.encryption import (
    get_encryption_service,
    get_encryption_service_with_token,
    is_encryption_required,
)


_GOOGLE_DRIVE_STATUS_DISCONNECTED = "disconnected"
_GOOGLE_DRIVE_STATUS_CONNECTED = "connected"
_GOOGLE_DRIVE_STATUS_NEEDS_RECONNECT = "needs_reconnect"
_GOOGLE_DRIVE_STATUSES = {
    _GOOGLE_DRIVE_STATUS_DISCONNECTED,
    _GOOGLE_DRIVE_STATUS_CONNECTED,
    _GOOGLE_DRIVE_STATUS_NEEDS_RECONNECT,
}
_DEFAULT_RETENTION_COUNT = 30


def _default_backup_settings() -> dict[str, object]:
    return {
        "retention_count": _DEFAULT_RETENTION_COUNT,
        "local_enabled": True,
        "google_drive_enabled": False,
        "google_drive": {
            "status": _GOOGLE_DRIVE_STATUS_DISCONNECTED,
            "account_email": "",
            "access_token": "",
            "refresh_token": "",
            "token_expiry": "",
            "root_folder_id": "",
            "root_folder_name": "",
        },
    }


def _serialize_settings_payload(settings: dict[str, object]) -> str:
    validated = _validate_backup_settings(settings)
    return json.dumps(validated, separators=(",", ":"), sort_keys=True)


def _deserialize_settings_payload(payload_json: str) -> dict[str, object]:
    if not isinstance(payload_json, str) or payload_json == "":
        raise RuntimeError("backup settings payload must be a non-empty string")
    parsed = json.loads(payload_json)
    if not isinstance(parsed, dict):
        raise RuntimeError("backup settings payload must be an object")
    return _validate_backup_settings(parsed)


def _validate_backup_settings(settings: dict[str, object]) -> dict[str, object]:
    if "retention_count" not in settings:
        raise RuntimeError("backup settings missing retention_count")
    retention_count = settings["retention_count"]
    if not isinstance(retention_count, int) or retention_count <= 0:
        raise RuntimeError("backup settings retention_count must be a positive integer")

    if "local_enabled" not in settings:
        raise RuntimeError("backup settings missing local_enabled")
    local_enabled = settings["local_enabled"]
    if not isinstance(local_enabled, bool):
        raise RuntimeError("backup settings local_enabled must be a bool")

    if "google_drive_enabled" not in settings:
        raise RuntimeError("backup settings missing google_drive_enabled")
    google_drive_enabled = settings["google_drive_enabled"]
    if not isinstance(google_drive_enabled, bool):
        raise RuntimeError("backup settings google_drive_enabled must be a bool")

    if "google_drive" not in settings:
        raise RuntimeError("backup settings missing google_drive")
    google_drive = settings["google_drive"]
    if not isinstance(google_drive, dict):
        raise RuntimeError("backup settings google_drive must be an object")

    required_google_keys = (
        "status",
        "account_email",
        "access_token",
        "refresh_token",
        "token_expiry",
        "root_folder_id",
        "root_folder_name",
    )
    for key in required_google_keys:
        if key not in google_drive:
            raise RuntimeError(f"backup settings google_drive missing {key}")

    status = google_drive["status"]
    if status not in _GOOGLE_DRIVE_STATUSES:
        raise RuntimeError(f"backup settings google_drive status invalid: {status!r}")

    account_email = google_drive["account_email"]
    access_token = google_drive["access_token"]
    refresh_token = google_drive["refresh_token"]
    token_expiry = google_drive["token_expiry"]
    root_folder_id = google_drive["root_folder_id"]
    root_folder_name = google_drive["root_folder_name"]
    string_values = (
        ("account_email", account_email),
        ("access_token", access_token),
        ("refresh_token", refresh_token),
        ("token_expiry", token_expiry),
        ("root_folder_id", root_folder_id),
        ("root_folder_name", root_folder_name),
    )
    for field_name, field_value in string_values:
        if not isinstance(field_value, str):
            raise RuntimeError(f"backup settings google_drive {field_name} must be a string")

    return {
        "retention_count": retention_count,
        "local_enabled": local_enabled,
        "google_drive_enabled": google_drive_enabled,
        "google_drive": {
            "status": status,
            "account_email": account_email,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": token_expiry,
            "root_folder_id": root_folder_id,
            "root_folder_name": root_folder_name,
        },
    }


def _resolve_encryption_service(*, token: str):
    if token:
        return get_encryption_service_with_token(token)
    return get_encryption_service()


def load_backup_settings(*, token: str) -> dict[str, object]:
    if not isinstance(token, str):
        raise TypeError("token must be a string")
    session = SafeSession()
    try:
        with SafeSession.allow_reads("backup_settings:load"):
            row = fetch_backup_settings_row(session.connection())
        if row is None:
            raise RuntimeError("app_settings row missing while loading backup settings")

        stored_json = row["backup_settings_json"]
        if stored_json is None:
            return _default_backup_settings()
        if not isinstance(stored_json, str):
            raise RuntimeError("backup_settings_json must be a string")

        nonce = row["backup_settings_encryption_nonce"]
        tag = row["backup_settings_encryption_tag"]
        if (nonce is None) != (tag is None):
            raise RuntimeError(
                "backup settings row has incomplete encryption metadata: "
                f"nonce={nonce is not None} tag={tag is not None}"
            )

        if nonce is None:
            return _deserialize_settings_payload(stored_json)

        service = _resolve_encryption_service(token=token)
        if service is None:
            raise RuntimeError("backup settings decryption requires an active DEK")
        decrypt_fn = getattr(service, "decrypt_from_storage", None)
        if not callable(decrypt_fn):
            raise TypeError("encryption service must expose decrypt_from_storage")
        plaintext = decrypt_fn(stored_json, nonce, tag)
        if not isinstance(plaintext, str):
            raise TypeError("decrypted backup settings payload must be a string")
        return _deserialize_settings_payload(plaintext)
    finally:
        session.close()


def save_backup_settings(*, token: str, settings: dict[str, object]) -> dict[str, object]:
    if not isinstance(token, str):
        raise TypeError("token must be a string")
    normalized_settings = _validate_backup_settings(settings)
    plaintext_json = _serialize_settings_payload(normalized_settings)
    stored_json = plaintext_json
    nonce: bytes | None = None
    tag: bytes | None = None

    service = _resolve_encryption_service(token=token)
    if service is not None:
        encrypt_fn = getattr(service, "encrypt_for_storage", None)
        if not callable(encrypt_fn):
            raise TypeError("encryption service must expose encrypt_for_storage")
        stored_json, nonce, tag = encrypt_fn(plaintext_json)
    elif is_encryption_required():
        raise RuntimeError("backup settings persistence requires an active DEK")

    with begin_writer() as connection:
        upsert_backup_settings_row(
            connection,
            backup_settings_json=stored_json,
            backup_settings_encryption_nonce=nonce,
            backup_settings_encryption_tag=tag,
            updated_at=datetime.now(timezone.utc),
        )
    return normalized_settings


def update_backup_settings(
    *,
    token: str,
    local_enabled: bool,
    google_drive_enabled: bool,
    retention_count: int,
) -> dict[str, object]:
    if not isinstance(local_enabled, bool):
        raise TypeError("local_enabled must be a bool")
    if not isinstance(google_drive_enabled, bool):
        raise TypeError("google_drive_enabled must be a bool")
    if not isinstance(retention_count, int) or retention_count <= 0:
        raise ValueError("retention_count must be a positive integer")

    settings = load_backup_settings(token=token)
    settings["local_enabled"] = local_enabled
    settings["google_drive_enabled"] = google_drive_enabled
    settings["retention_count"] = retention_count
    return save_backup_settings(token=token, settings=settings)


def set_google_drive_connection(
    *,
    token: str,
    status: str,
    account_email: str,
    access_token: str,
    refresh_token: str,
    token_expiry: str,
    root_folder_id: str,
    root_folder_name: str,
) -> dict[str, object]:
    settings = load_backup_settings(token=token)
    google_drive = settings["google_drive"]
    assert isinstance(google_drive, dict)
    google_drive["status"] = status
    google_drive["account_email"] = account_email
    google_drive["access_token"] = access_token
    google_drive["refresh_token"] = refresh_token
    google_drive["token_expiry"] = token_expiry
    google_drive["root_folder_id"] = root_folder_id
    google_drive["root_folder_name"] = root_folder_name
    return save_backup_settings(token=token, settings=settings)


def clear_google_drive_connection(*, token: str) -> dict[str, object]:
    settings = load_backup_settings(token=token)
    google_drive = settings["google_drive"]
    assert isinstance(google_drive, dict)
    google_drive["status"] = _GOOGLE_DRIVE_STATUS_DISCONNECTED
    google_drive["account_email"] = ""
    google_drive["access_token"] = ""
    google_drive["refresh_token"] = ""
    google_drive["token_expiry"] = ""
    google_drive["root_folder_id"] = ""
    google_drive["root_folder_name"] = ""
    settings["google_drive_enabled"] = False
    return save_backup_settings(token=token, settings=settings)
