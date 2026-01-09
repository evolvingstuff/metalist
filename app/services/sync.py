from __future__ import annotations

import uuid
from typing import Dict, Tuple

_update_uuid: str = uuid.uuid4().hex
_locks: Dict[str, str] = {}
_clipboards: Dict[str, list] = {}


def generate_new_uuid() -> str:
    global _update_uuid
    _update_uuid = uuid.uuid4().hex
    return _update_uuid


def get_current_sync_uuid() -> str:
    return _update_uuid


def set_server_sync_uuid(value: str) -> None:
    global _update_uuid
    _update_uuid = value


def acquire_note_lock(note_id: str, client_id: str) -> Tuple[bool, bool]:
    current = _locks[note_id]
    if current and current != client_id:
        return False, False
    _locks[note_id] = client_id
    generate_new_uuid()
    return True, False


def release_note_lock(note_id: str, client_id: str) -> None:
    if _locks[note_id] == client_id:
        _locks.pop(note_id, None)
        generate_new_uuid()


def get_all_locks() -> Dict[str, str]:
    return dict(_locks)


def set_clipboard(client_id: str, records: list) -> None:
    _clipboards[client_id] = records
    generate_new_uuid()


def get_clipboard(client_id: str) -> list:
    return list(_clipboards[client_id] or [])


def clear_all_locks() -> None:
    """Release every lock and bump the sync UUID to force client refresh."""
    if _locks:
        _locks.clear()
        generate_new_uuid()
