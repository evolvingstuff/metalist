import uuid
from typing import Dict, Optional

# Global in-memory sync state - THIS IS MUTABLE SERVER STATE
_current_update_uuid = str(uuid.uuid4())

# Global in-memory note locks - THIS IS MUTABLE SERVER STATE  
# Format: {note_id: client_id}
_note_locks: Dict[str, str] = {}


def generate_new_uuid() -> str:
    """Generate a new UUID (pure function, no side effects)."""
    return str(uuid.uuid4())


def set_server_sync_uuid(new_uuid: str) -> None:
    """SIDE EFFECT: Updates the global sync UUID on the server."""
    global _current_update_uuid
    _current_update_uuid = new_uuid


def get_current_sync_uuid() -> str:
    """Get the current sync UUID from server state (read-only)."""
    return _current_update_uuid


# Note locking functions
def acquire_note_lock(note_id: str, client_id: str) -> bool:
    """SIDE EFFECT: Try to acquire a lock on a note.
    
    Returns:
        bool: True if lock acquired, False if already locked by different client
    """
    global _note_locks
    
    # Check if note is already locked by a different client
    if note_id in _note_locks and _note_locks[note_id] != client_id:
        return False
        
    # Acquire the lock
    _note_locks[note_id] = client_id
    return True


def release_note_lock(note_id: str, client_id: str) -> None:
    """SIDE EFFECT: Release a lock on a note if owned by the client."""
    global _note_locks
    
    # Only release if this client owns the lock
    if _note_locks.get(note_id) == client_id:
        del _note_locks[note_id]


def get_note_lock_owner(note_id: str) -> Optional[str]:
    """Get the client ID that owns the lock for a note (read-only)."""
    return _note_locks.get(note_id)


def get_all_locks() -> Dict[str, str]:
    """Get all current note locks (read-only)."""
    return _note_locks.copy()


def is_note_locked_by_other_client(note_id: str, client_id: str) -> bool:
    """Check if a note is locked by a different client (read-only)."""
    lock_owner = _note_locks.get(note_id)
    return lock_owner is not None and lock_owner != client_id