from __future__ import annotations

from datetime import datetime, timezone
import json

from app.db.backup_settings_sql import fetch_backup_settings_row, upsert_backup_settings_row
from app.db.session import begin_writer
from app.models.database import SafeSession
from app.security.encryption import get_encryption_service
from app.security.encryption import get_encryption_service_with_token
from app.security.encryption import is_encryption_required


_DEFAULT_RETENTION_COUNT = 30


def _default_backup_settings() -> dict[str, object]:
    return {
        "retention_count": _DEFAULT_RETENTION_COUNT,
        "local_enabled": True,
        "folder_enabled": False,
        "folder_path": "",
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

    folder_enabled = False
    if "folder_enabled" in settings:
        folder_enabled = settings["folder_enabled"]
        if not isinstance(folder_enabled, bool):
            raise RuntimeError("backup settings folder_enabled must be a bool")

    folder_path = ""
    if "folder_path" in settings:
        folder_path = settings["folder_path"]
        if not isinstance(folder_path, str):
            raise RuntimeError("backup settings folder_path must be a string")
    if folder_enabled and folder_path == "":
        raise RuntimeError("backup settings folder_path must be configured when folder_enabled is true")

    return {
        "retention_count": retention_count,
        "local_enabled": local_enabled,
        "folder_enabled": folder_enabled,
        "folder_path": folder_path,
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
    folder_enabled: bool,
    folder_path: str,
    retention_count: int,
) -> dict[str, object]:
    if not isinstance(local_enabled, bool):
        raise TypeError("local_enabled must be a bool")
    if not isinstance(folder_enabled, bool):
        raise TypeError("folder_enabled must be a bool")
    if not isinstance(folder_path, str):
        raise TypeError("folder_path must be a string")
    if not isinstance(retention_count, int) or retention_count <= 0:
        raise ValueError("retention_count must be a positive integer")

    settings = load_backup_settings(token=token)
    settings["local_enabled"] = local_enabled
    settings["folder_enabled"] = folder_enabled
    settings["folder_path"] = folder_path
    settings["retention_count"] = retention_count
    return save_backup_settings(token=token, settings=settings)
