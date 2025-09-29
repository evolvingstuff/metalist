import pytest

from app.services.tokens import token_service


@pytest.mark.anyio("asyncio")
async def test_password_setup_login_and_logout(client):
    status = await client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.json() == {
        "authenticated": False,
        "has_password": False,
        "encryption_enabled": False,
        "encryption_algorithm": None,
    }

    create_resp = await client.post(
        "/api/auth/settings/password/create",
        json={"password": "secret123"},
    )
    assert create_resp.status_code == 200
    assert "Encrypted" in create_resp.json()["message"]

    status = await client.get("/api/auth/status")
    assert status.json()["has_password"] is True
    assert status.json()["authenticated"] is False

    bad_login = await client.post("/api/auth/login", json={"password": "bad"})
    assert bad_login.status_code == 401

    login_resp = await client.post("/api/auth/login", json={"password": "secret123"})
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    assert token_service.verify_token(token) is True

    auth_status = await client.get(
        "/api/auth/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = auth_status.json()
    assert payload["authenticated"] is True
    assert payload["has_password"] is True
    assert payload["encryption_enabled"] is True

    logout = await client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout.status_code == 200

    post_logout = await client.get(
        "/api/auth/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert post_logout.json()["authenticated"] is False
    assert token_service.verify_token(token) is False
