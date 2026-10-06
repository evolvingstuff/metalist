import asyncio

import pytest
import httpx
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.routes import ai as ai_routes
from app.services.agent.agent_tools import OpenMenuArguments
from app.services.agent.help_catalog import MENU_ACTIONS
from app.services.agent.menu_actions import MenuActionStore, MenuResult, menu_action_store


@pytest.mark.parametrize('menu', MENU_ACTIONS, ids=lambda menu: menu['id'])
def test_every_menu_in_the_catalog_can_be_opened_by_the_agent(menu):
    assert OpenMenuArguments(menu_id=menu['id']).menu_id == menu['id']


@pytest.mark.parametrize('menu_id', ['none', 'command_palette.execute', 'action.delete_everything'])
def test_unknown_menu_destinations_are_rejected(menu_id):
    with pytest.raises(ValidationError):
        OpenMenuArguments(menu_id=menu_id)


def test_menu_acknowledgments_are_session_bound_single_use_and_cleaned_up():
    async def run():
        store = MenuActionStore()
        pending = store.create(session_key='a', menu_id='form.ai_agent_settings')
        result = MenuResult(request_id=pending.request_id, status='opened', detail='Visible')
        with pytest.raises(ValueError, match='session'):
            store.acknowledge(session_key='b', result=result)
        store.acknowledge(session_key='a', result=result)
        with pytest.raises(ValueError):
            store.acknowledge(session_key='a', result=result)
        assert await store.wait(pending) == result
        with pytest.raises(ValueError):
            store.acknowledge(session_key='a', result=result)
        assert store._pending == {}
    asyncio.run(run())


def test_menu_wait_cancellation_removes_request():
    async def run():
        store = MenuActionStore()
        pending = store.create(session_key='a', menu_id='form.ai_agent_settings')
        task = asyncio.create_task(store.wait(pending))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert store._pending == {}
    asyncio.run(run())


def test_missing_browser_ack_is_unavailable_not_opened(monkeypatch):
    async def timeout(*args, **kwargs):
        raise asyncio.TimeoutError
    monkeypatch.setattr(asyncio, 'wait_for', timeout)
    async def run():
        store = MenuActionStore()
        pending = store.create(session_key='a', menu_id='form.ai_agent_settings')
        result = await store.wait(pending)
        assert result.status == 'unavailable'
        assert store._pending == {}
    asyncio.run(run())


def test_menu_ack_api_requires_auth_session_and_single_use(monkeypatch):
    application = FastAPI()
    application.include_router(ai_routes.router)
    monkeypatch.setattr(ai_routes.token_service, 'get_session_key', lambda token: token)
    async def run():
        pending = menu_action_store.create(session_key='owner', menu_id='form.ai_agent_settings')
        payload = dict(request_id=pending.request_id, status='opened', detail='Visible')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
            assert (await client.post('/ai/menu-result', json=payload)).status_code == 401
            assert (await client.post('/ai/menu-result', json=payload, headers={'Authorization': 'Bearer other'})).status_code == 409
            headers = {'Authorization': 'Bearer owner'}
            assert (await client.post('/ai/menu-result', json={**payload, 'status': 'invented'}, headers=headers)).status_code == 422
            assert (await client.post('/ai/menu-result', json=payload, headers=headers)).status_code == 200
            assert (await client.post('/ai/menu-result', json=payload, headers=headers)).status_code == 409
        assert (await menu_action_store.wait(pending)).status == 'opened'
    asyncio.run(run())
