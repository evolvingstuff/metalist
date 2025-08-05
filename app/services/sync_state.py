import uuid

# Global in-memory sync state - THIS IS MUTABLE SERVER STATE
_current_update_uuid = str(uuid.uuid4())


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