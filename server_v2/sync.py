from __future__ import annotations

import uuid
from typing import Dict, Tuple

_update_uuid: str = uuid.uuid4().hex
_locks: Dict[str, str] = {}


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
    current = _locks.get(note_id)
    if current and current != client_id:
        return False, False
    _locks[note_id] = client_id
    generate_new_uuid()
    return True, False


def release_note_lock(note_id: str, client_id: str) -> None:
    if _locks.get(note_id) == client_id:
        _locks.pop(note_id, None)
        generate_new_uuid()


def get_all_locks() -> Dict[str, str]:
    return dict(_locks)

