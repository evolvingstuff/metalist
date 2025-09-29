import pytest

from app.services import sync_state


@pytest.fixture(autouse=True)
def reset_sync_globals():
    original_uuid = sync_state.get_current_sync_uuid()
    sync_state._note_locks.clear()
    sync_state._client_clipboards.clear()
    yield
    sync_state._note_locks.clear()
    sync_state._client_clipboards.clear()
    sync_state.set_server_sync_uuid(original_uuid)


class FakeTime:
    def __init__(self, start: float):
        self.value = start

    def time(self) -> float:
        return self.value


def test_acquire_lock_expires_and_cleans(monkeypatch):
    clock = FakeTime(start=1_000.0)
    monkeypatch.setattr(sync_state, "time", clock)

    acquired, expired = sync_state.acquire_note_lock("note-1", "client-a")
    assert acquired is True
    assert expired is False

    clock.value = 1_002.0
    reacquired, expired = sync_state.acquire_note_lock("note-1", "client-a")
    assert reacquired is True
    assert expired is False

    clock.value = 1_003.0
    blocked, expired = sync_state.acquire_note_lock("note-1", "client-b")
    assert blocked is False
    assert expired is False

    clock.value = 1_009.2  # beyond 5 second timeout
    takeover, expired = sync_state.acquire_note_lock("note-1", "client-b")
    assert takeover is True
    assert expired is True
    assert sync_state.get_note_lock_owner("note-1") == "client-b"

    # Advance time again and ensure cleanup removes stale locks
    clock.value = 1_020.0
    removed = sync_state.cleanup_expired_locks()
    assert removed is True
    assert sync_state.get_all_locks() == {}


def test_clipboard_round_trip():
    payload = {"id": "n1", "content": "hello"}
    sync_state.set_client_clipboard("client-a", payload)
    assert sync_state.get_client_clipboard("client-a") == payload

    sync_state.clear_client_clipboard("client-a")
    assert sync_state.get_client_clipboard("client-a") is None


def test_sync_uuid_tracking():
    previous = sync_state.get_current_sync_uuid()
    new_uuid = sync_state.generate_new_uuid()
    sync_state.set_server_sync_uuid(new_uuid)
    assert sync_state.get_current_sync_uuid() == new_uuid
    assert sync_state.get_current_sync_uuid() != previous
