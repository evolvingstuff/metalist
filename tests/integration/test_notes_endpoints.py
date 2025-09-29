import pytest

from app.models.database import SafeSession, SessionLocal, DBNote
from app.services import sync_state


def _get_session():
    return SessionLocal(bind=SafeSession.get_engine())


@pytest.mark.anyio("asyncio")
async def test_create_update_collapse_and_delete_note(client):
    create = await client.post("/api/notes/new", json={"clientId": "test-client"})
    assert create.status_code == 200
    note_id = create.json()["id"]

    update = await client.put(
        f"/api/notes/{note_id}",
        json={"content": "Hello", "clientId": "test-client"},
    )
    assert update.status_code == 200

    collapse = await client.post(
        f"/api/notes/{note_id}/collapse",
        json={"clientId": "test-client"},
    )
    collapse_payload = collapse.json()
    assert collapse_payload["status"] == "updated"
    assert collapse_payload["isCollapsed"] is True

    delete = await client.request(
        "DELETE",
        f"/api/notes/{note_id}",
        json={"clientId": "test-client"},
    )
    assert delete.status_code == 200

    session = _get_session()
    try:
        note = session.get(DBNote, note_id)
        assert note is None
    finally:
        session.close()


@pytest.mark.anyio("asyncio")
async def test_lock_lifecycle_and_sync_updates(client):
    create = await client.post("/api/notes/new", json={"clientId": "client-a"})
    note_id = create.json()["id"]

    initial_uuid = sync_state.get_current_sync_uuid()
    check = await client.post(
        "/api/notes/check-updates",
        json={"clientId": "client-a", "lastUpdateUUID": initial_uuid},
    )
    assert check.json() == {"needsUpdate": False, "currentUpdateUUID": initial_uuid}

    lock = await client.post(
        "/api/notes/acquire-lock",
        json={"noteId": note_id, "clientId": "client-a", "lastUpdateUUID": initial_uuid},
    )
    lock_payload = lock.json()
    assert lock_payload["success"] is True
    updated_uuid = lock_payload["updateUUID"]
    assert updated_uuid != initial_uuid

    conflict = await client.post(
        "/api/notes/acquire-lock",
        json={"noteId": note_id, "clientId": "client-b"},
    )
    assert conflict.status_code == 409

    release = await client.post(
        "/api/notes/release-lock",
        json={"noteId": note_id, "clientId": "client-a"},
    )
    release_payload = release.json()
    assert release_payload["success"] is True

    takeover = await client.post(
        "/api/notes/acquire-lock",
        json={"noteId": note_id, "clientId": "client-b"},
    )
    assert takeover.status_code == 200
    assert takeover.json()["success"] is True

    check_again = await client.post(
        "/api/notes/check-updates",
        json={"clientId": "client-b", "lastUpdateUUID": initial_uuid},
    )
    assert check_again.json()["needsUpdate"] is True
