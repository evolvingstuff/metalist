import httpx
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    from app.models.database import SafeSession
    from app.services.content_cache import clear_cache
    from app.services import sync_state
    from app.services.tokens import token_service
    from app.utils import encryption as encryption_utils
    from app.main import app

    SafeSession.use_memory_db()
    clear_cache()
    sync_state._note_locks.clear()
    sync_state._client_clipboards.clear()
    sync_state.set_server_sync_uuid(sync_state.generate_new_uuid())
    token_service.revoke_all_tokens()
    encryption_utils.clear_encryption_key()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    token_service.revoke_all_tokens()
    clear_cache()
    sync_state._note_locks.clear()
    sync_state._client_clipboards.clear()
    encryption_utils.clear_encryption_key()
