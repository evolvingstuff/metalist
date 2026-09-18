import asyncio
import json
from types import SimpleNamespace

import pytest
import httpx
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.routes import ai as ai_routes
from app.services.agent.actions import ScopedRouteEnvelope
from app.services.agent.context import AgentContextBuilder
from app.services.agent.help_catalog import HELP_TOPICS, MENU_ACTIONS, MetaListHelpResponse
from app.services.agent.menu_actions import MenuActionStore, MenuResult, menu_action_store
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS, resolve_agent_skill_set
from test_agent_history import install_transport, chunk, response, USAGE
from test_agent_scoped_runtime import _FakeInference, _runtime, _snapshot


@pytest.mark.parametrize('topic', HELP_TOPICS)
def test_each_help_skill_loads_only_for_its_selected_call(topic):
    builder = AgentContextBuilder()
    canonical = [{'role': 'user', 'content': 'Explain this feature.'}]
    kwargs = dict(canonical_messages=canonical, prompts=DEFAULT_AGENT_PROMPTS)
    route = builder.build_scoped_route_messages(**kwargs, snapshot=_snapshot(large_tail=False))
    help_messages = builder.build_help_messages(**kwargs, skills=DEFAULT_AGENT_SKILLS, topics=[topic])
    skill = DEFAULT_AGENT_SKILLS.for_action(f'help_{topic}')
    assert skill.content in help_messages[1]['content']
    assert 'ROOT_ALPHA' not in json.dumps(help_messages)
    assert all('ACTIVE_SKILL' not in m['content'] for m in route)
    assert len([m for m in help_messages if m['content'].startswith('ACTIVE_SKILL')]) == 1
    assert builder.build_initial_messages(**kwargs) == [dict(role='system', content=DEFAULT_AGENT_PROMPTS.system_prompt), *canonical]
    assert canonical == [{'role': 'user', 'content': 'Explain this feature.'}]


def test_selected_help_overrides_are_used_and_other_skills_are_not_loaded():
    skills = resolve_agent_skill_set(preferences={'pref.ai.skill.help_ai_v1': 'CUSTOM AI INSTRUCTIONS'})
    messages = AgentContextBuilder().build_help_messages(
        canonical_messages=[{'role': 'user', 'content': 'AI privacy'}], prompts=DEFAULT_AGENT_PROMPTS,
        skills=skills, topics=['ai', 'privacy'])
    text = json.dumps(messages)
    assert 'CUSTOM AI INSTRUCTIONS' in text
    assert 'ACTIVE_SKILL help_privacy_v1' in text
    assert 'ACTIVE_SKILL help_notes_v1' not in text


@pytest.mark.parametrize('payload', [
    dict(kind='metalist_help', help_topics=[], reason='Empty'),
    dict(kind='respond', help_topics=['ai'], reason='Irrelevant fields'),
    dict(kind='metalist_help', help_topics=['unknown'], reason='Unknown'),
    dict(kind='metalist_help', help_topics=['ai', 'ai'], reason='Duplicate'),
])
def test_help_route_schema_enforces_supported_unique_topics(payload):
    with pytest.raises(ValidationError):
        ScopedRouteEnvelope.model_validate(payload)


@pytest.mark.parametrize('menu', MENU_ACTIONS, ids=lambda menu: menu['id'])
def test_every_menu_target_has_a_valid_help_response(menu):
    response = MetaListHelpResponse(answer='Here is how.', menu_id=menu['id'])
    assert response.menu_id == menu['id']
    assert menu['presentation'] in {'dialog', 'palette'}


@pytest.mark.parametrize('menu_id', ['delete_notes', 'javascript:alert(1)', '../../anything', '', 'form.unknown'])
def test_unknown_menu_commands_are_not_executable(menu_id):
    with pytest.raises(ValidationError):
        MetaListHelpResponse(answer='Try this', menu_id=menu_id)


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


class HelpInference(_FakeInference):
    def __init__(self, menu_id):
        super().__init__(route_kind='metalist_help')
        self.menu_id = menu_id
        self.calls = []

    async def infer_structured(self, **kwargs):
        self.calls.append(kwargs['messages'])
        if kwargs['response_model'] is ScopedRouteEnvelope:
            result = ScopedRouteEnvelope(kind='metalist_help', help_topics=['ai'], reason='Product help')
        else:
            assert kwargs['response_model'] is MetaListHelpResponse
            result = MetaListHelpResponse(answer='Set Maximum approximate evidence tokens to 250000.', menu_id=self.menu_id)
        return SimpleNamespace(content=result.model_dump_json(), attempts=[])


@pytest.mark.parametrize('menu_id,status', [
    ('none', 'opened'), ('form.ai_agent_settings', 'opened'),
    ('form.ai_agent_settings', 'unavailable'), ('form.ai_agent_settings', 'cancelled'),
    ('action.create_backup', 'opened'),
])
def test_real_runtime_two_calls_and_actual_menu_result(menu_id, status):
    inference = HelpInference(menu_id)
    runtime = _runtime(inference)
    async def run():
        events = []
        async for event in runtime.stream_scoped(
            tag_handler=None, session_key='session-1', base_url='https://api.openai.com/v1',
            selected_model='gpt-5.6-luna', thinking_level='off',
            canonical_messages=[{'role': 'user', 'content': 'Where is the context limit?'}],
            prompts=DEFAULT_AGENT_PROMPTS, skills=DEFAULT_AGENT_SKILLS,
            retrieval_settings=AgentRetrievalSettings(max_page_approximate_tokens=24000),
            frozen_scope=_snapshot(large_tail=False),
        ):
            events.append(event)
            if event['type'] == 'menu_open':
                menu_action_store.acknowledge(session_key='session-1', result=MenuResult(
                    request_id=event['request_id'], status=status, detail='Fixture browser result'))
        return events
    events = asyncio.run(run())
    assert len(inference.calls) == 2
    assert 'ACTIVE_SKILL' not in json.dumps(inference.calls[0])
    assert 'ACTIVE_SKILL help_ai_v1' in json.dumps(inference.calls[1])
    assert 'ROOT_ALPHA' not in json.dumps(inference.calls)
    assert events[-1]['type'] == 'done'
    assert menu_action_store._pending == {}
    text = ''.join(e['text'] for e in events if e['type'] == 'content_delta')
    if menu_id == 'none':
        assert not any(e['type'] == 'menu_open' for e in events)
    elif status != 'opened':
        assert 'Could not open' in text
        assert 'Opened **' not in text
    elif menu_id == 'action.create_backup':
        assert 'command has not been executed' in text
    else:
        assert 'Opened **AI agent settings**' in text


def test_real_instructor_history_captures_selected_skill_and_menu_ack(monkeypatch):
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            payload = dict(kind='metalist_help', help_topics=['ai'], reason='Settings question')
        else:
            payload = dict(answer='The evidence limit is in AI agent settings.', menu_id='form.ai_agent_settings')
        return response([chunk(json.dumps(payload), None, None), chunk(None, 'stop', USAGE)])
    runtime = _runtime(install_transport(monkeypatch, handle))
    async def run():
        async for event in runtime.stream_scoped(
            tag_handler=None, session_key='session-1', base_url='https://api.openai.com/v1',
            selected_model='gpt-5.6-luna', thinking_level='off',
            canonical_messages=[{'role': 'user', 'content': 'Open AI settings'}],
            prompts=DEFAULT_AGENT_PROMPTS, skills=DEFAULT_AGENT_SKILLS,
            retrieval_settings=AgentRetrievalSettings(max_page_approximate_tokens=24000),
            frozen_scope=_snapshot(large_tail=False),
        ):
            if event['type'] == 'menu_open':
                menu_action_store.acknowledge(session_key='session-1', result=MenuResult(
                    request_id=event['request_id'], status='opened', detail='Visible browser dialog'))
    asyncio.run(run())
    pairs = runtime._trace_store.export_history(session_key='session-1')
    assert len(pairs) == 2
    assert 'ACTIVE_SKILL' not in json.dumps(pairs[0])
    assert DEFAULT_AGENT_SKILLS.for_action('help_ai').content in pairs[1][0]['invocation']['messages'][1]['content']
    assert [e['type'] for e in pairs[1][1]['application_events']] == ['MENU_REQUESTED', 'MENU_RESULT']
    assert pairs[1][1]['application_events'][-1]['detail']['status'] == 'opened'
    assert 'sk-test-not-exported' not in json.dumps(pairs)
    assert 'ROOT_ALPHA' not in json.dumps(pairs)


def test_closing_stream_at_menu_request_cleans_pending_ack_immediately():
    runtime = _runtime(HelpInference('form.ai_agent_settings'))
    async def run():
        stream = runtime.stream_scoped(
            tag_handler=None, session_key='session-1', base_url='https://api.openai.com/v1',
            selected_model='gpt-5.6-luna', thinking_level='off',
            canonical_messages=[{'role': 'user', 'content': 'Open AI settings'}],
            prompts=DEFAULT_AGENT_PROMPTS, skills=DEFAULT_AGENT_SKILLS,
            retrieval_settings=AgentRetrievalSettings(max_page_approximate_tokens=24000),
            frozen_scope=_snapshot(large_tail=False),
        )
        async for event in stream:
            if event['type'] == 'menu_open':
                assert event['request_id'] in menu_action_store._pending
                await stream.aclose()
                assert menu_action_store._pending == {}
                return
        pytest.fail('Missing menu request')
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
