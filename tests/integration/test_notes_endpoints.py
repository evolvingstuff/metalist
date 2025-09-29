import pytest

from app.models.database import SafeSession, SessionLocal, DBNote
from app.services import sync_state
from app.services.content_cache import get_cached_content


async def _create_note(client, client_id: str, **extra_payload) -> str:
    payload = {"clientId": client_id}
    payload.update(extra_payload)
    response = await client.post("/api/notes/new", json=payload)
    assert response.status_code == 200
    return response.json()["id"]


def _session():
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

    session = _session()
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


@pytest.mark.anyio("asyncio")
async def test_move_and_create_sibling_flow(client):
    client_id = "arranger"
    root_a = await _create_note(client, client_id)
    root_b = await _create_note(client, client_id)

    child_resp = await client.post(
        f"/api/notes/new-child/{root_a}", json={"clientId": client_id}
    )
    child_id = child_resp.json()["id"]

    move_payload = {
        "clientId": client_id,
        "new_parent_id": root_b,
    }
    move_resp = await client.post(f"/api/notes/{child_id}/move", json=move_payload)
    assert move_resp.status_code == 200

    sibling_resp = await client.post(
        f"/api/notes/new-sibling/{child_id}", json={"clientId": client_id}
    )
    sibling_id = sibling_resp.json()["id"]

    session = _session()
    try:
        child = session.get(DBNote, child_id)
        sibling = session.get(DBNote, sibling_id)
        assert child.parent_id == root_b
        assert sibling.parent_id == root_b
        assert sibling.prev_id == child_id
    finally:
        session.close()


@pytest.mark.anyio("asyncio")
async def test_copy_paste_child_and_sibling(client):
    client_id = "clipboard"
    root = await _create_note(client, client_id)
    child_resp = await client.post(
        f"/api/notes/new-child/{root}", json={"clientId": client_id}
    )
    child_id = child_resp.json()["id"]

    await client.put(
        f"/api/notes/{child_id}",
        json={"content": "child-body", "clientId": client_id},
    )

    copy_resp = await client.post(
        f"/api/notes/{child_id}/copy", json={"clientId": client_id}
    )
    assert copy_resp.status_code == 200

    paste_child = await client.post(
        f"/api/notes/paste-child/{root}", json={"clientId": client_id}
    )
    cloned_child_id = paste_child.json()["id"]

    paste_sibling = await client.post(
        f"/api/notes/paste-sibling/{child_id}", json={"clientId": client_id}
    )
    sibling_id = paste_sibling.json()["id"]

    session = _session()
    try:
        children = session.query(DBNote).filter(DBNote.parent_id == root).all()
        ids = {note.id for note in children}
        assert {child_id, cloned_child_id, sibling_id}.issubset(ids)
    finally:
        session.close()


@pytest.mark.anyio("asyncio")
async def test_undo_redo_round_trip(client):
    client_id = "undoer"
    note_id = await _create_note(client, client_id)

    await client.put(
        f"/api/notes/{note_id}",
        json={"content": "first", "clientId": client_id},
    )
    await client.put(
        f"/api/notes/{note_id}",
        json={"content": "second", "clientId": client_id},
    )

    undo_resp = await client.post(
        "/api/notes/undo", params={"client_id": client_id}
    )
    assert undo_resp.json()["status"] == "success"
    assert get_cached_content(note_id) == "first"

    redo_resp = await client.post(
        "/api/notes/redo", params={"client_id": client_id}
    )
    assert redo_resp.json()["status"] == "success"
    assert get_cached_content(note_id) == "second"
