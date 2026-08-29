import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

import app.api.routes.ai as ai_routes
from app.services.ai_chat import AiChatSessionStore
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.prompt_settings import SYSTEM_PROMPT_PREFERENCE_KEY
from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.trace import AgentTraceStore
from app.services.ollama_provider import OllamaProviderError


def _assert_positive_activity_token_counts(events: list[dict[str, object]]) -> None:
    activities = [event for event in events if event["type"] == "action_status"]
    assert activities
    assert all(
        isinstance(event["approx_input_tokens"], int)
        and not isinstance(event["approx_input_tokens"], bool)
        and event["approx_input_tokens"] > 0
        for event in activities
    )


def _without_activity_token_counts(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            key: value
            for key, value in event.items()
            if key != "approx_input_tokens"
        }
        for event in events
    ]


@pytest.fixture(autouse=True)
def use_fake_managed_ollama_runtime(monkeypatch):
    class FakeManagedRuntime:
        def ensure_running(self):
            return SimpleNamespace(
                base_url="http://127.0.0.1:11435",
                context_tokens=32_768,
            )

    monkeypatch.setattr(ai_routes, "managed_ollama_runtime", FakeManagedRuntime())


def test_ai_session_snapshot_uses_authenticated_session_key(monkeypatch) -> None:
    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-key",
        user_content="Hello",
        provider="ollama",
        model="qwen3:8b",
    )
    store.append_activity(
        session_key="session-key",
        turn_id=turn_id,
        action="model_request",
        status="started",
        label="Waiting for Ollama · attempt 1 of 2",
        approx_input_tokens=1_234,
    )
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(
        ai_routes.token_service,
        "get_session_key",
        lambda token: "session-key",
    )

    http_response = Response()
    response = ai_routes.get_ai_session(response=http_response, token="auth-token")

    assert len(response.messages) == 2
    assert response.messages[0].content == "Hello"
    assert response.messages[0].rendered_content == ""
    assert response.messages[0].rendered_thinking == ""
    assert response.messages[1].status == "streaming"
    assert response.messages[1].rendered_content == ""
    assert response.messages[1].rendered_thinking == ""
    assert [activity.model_dump() for activity in response.messages[1].activities] == [
        {
            "sequence": 1,
            "action": "model_request",
            "status": "started",
            "label": "Waiting for Ollama · attempt 1 of 2",
            "approx_input_tokens": 1_234,
        }
    ]
    assert http_response.headers["Cache-Control"] == "no-store"


def test_ai_prompt_defaults_returns_packaged_prompts() -> None:
    http_response = Response()

    response = ai_routes.get_ai_prompt_defaults(
        response=http_response,
        token="auth-token",
    )

    assert response.system_prompt == DEFAULT_AGENT_PROMPTS.system_prompt
    assert response.final_response_prompt == DEFAULT_AGENT_PROMPTS.final_response_prompt
    assert response.tool_result_prompt == DEFAULT_AGENT_PROMPTS.tool_result_prompt
    assert [skill.model_dump() for skill in response.skills] == [
        {
            "skill_id": skill.skill_id,
            "title": skill.title,
            "description": skill.description,
            "trigger_action": skill.trigger_action,
            "preference_key": skill.preference_key,
            "content": skill.content,
        }
        for skill in DEFAULT_AGENT_SKILLS.skills
    ]
    assert http_response.headers["Cache-Control"] == "no-store"


def test_ai_session_renders_assistant_markdown_latex_and_mermaid(monkeypatch) -> None:
    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-key",
        user_content="Explain it",
        provider="ollama",
        model="qwen3:8b",
    )
    store.append_delta(
        session_key="session-key",
        turn_id=turn_id,
        delta_kind="content",
        text=(
            "# Result\n\n"
            "Inline math: $x^2$.\n\n"
            "```mermaid\nflowchart LR\nA-->B\n```"
        ),
    )
    store.append_delta(
        session_key="session-key",
        turn_id=turn_id,
        delta_kind="thinking",
        text="## Reasoning\n\nUse $x^2$.",
    )
    store.complete_turn(
        session_key="session-key",
        turn_id=turn_id,
        final_content=(
            "# Result\n\n"
            "Inline math: $x^2$.\n\n"
            "```mermaid\nflowchart LR\nA-->B\n```"
        ),
    )
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(
        ai_routes.token_service,
        "get_session_key",
        lambda token: "session-key",
    )

    response = ai_routes.get_ai_session(response=Response(), token="auth-token")
    rendered = response.messages[1].rendered_content
    rendered_thinking = response.messages[1].rendered_thinking

    assert response.messages[0].rendered_content == ""
    assert "<h1>Result</h1>" in rendered
    assert '<math xmlns="http://www.w3.org/1998/Math/MathML"' in rendered
    assert '<pre class="meta-mermaid-source">' in rendered
    assert '<code class="language-mermaid">' in rendered
    assert "<h2>Reasoning</h2>" in rendered_thinking
    assert '<math xmlns="http://www.w3.org/1998/Math/MathML"' in rendered_thinking


def test_ai_session_renders_note_uuid_as_navigable_content_preview(monkeypatch) -> None:
    note_id = "75193dae-9e05-4a4e-94bf-417ffde18957"

    class FakeNotes:
        def has_note(self, candidate_note_id: str) -> bool:
            return candidate_note_id == note_id

        def get_note(self, candidate_note_id: str):
                assert candidate_note_id == note_id
                return SimpleNamespace(
                    parent_id=None,
                    content="<p>Instructor + LiteLLM vs. Pydantic AI</p>",
                    tags="architecture",
                )

    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-key",
        user_content="Summarize it",
        provider="ollama",
        model="qwen3:8b",
    )
    store.append_delta(
        session_key="session-key",
        turn_id=turn_id,
        delta_kind="content",
        text=f"Source: [[{note_id}]]",
    )
    store.complete_turn(
        session_key="session-key",
        turn_id=turn_id,
        final_content=f"Source: [[{note_id}]]",
    )
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "note_store", FakeNotes())
    monkeypatch.setattr(
        ai_routes.token_service,
        "get_session_key",
        lambda token: "session-key",
    )

    response = ai_routes.get_ai_session(response=Response(), token="auth-token")
    rendered = response.messages[1].rendered_content

    assert "Instructor + LiteLLM vs. Pydantic AI" in rendered
    assert 'class="ai-chat-note-mention"' in rendered
    assert 'class="ai-chat-references"' in rendered
    assert f'data-ref-note-id="{note_id}"' in rendered
    assert 'class="note-reference-link"' in rendered


def test_ai_session_rendered_markdown_rejects_executable_links(monkeypatch) -> None:
    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-key",
        user_content="Give me a link",
        provider="ollama",
        model="qwen3:8b",
    )
    store.append_delta(
        session_key="session-key",
        turn_id=turn_id,
        delta_kind="content",
        text="[unsafe](javascript:alert(1)) <script>alert(2)</script>",
    )
    store.complete_turn(
        session_key="session-key",
        turn_id=turn_id,
        final_content="[unsafe](javascript:alert(1)) <script>alert(2)</script>",
    )
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(
        ai_routes.token_service,
        "get_session_key",
        lambda token: "session-key",
    )

    response = ai_routes.get_ai_session(response=Response(), token="auth-token")
    rendered = response.messages[1].rendered_content

    assert "javascript:" in rendered
    assert 'href="javascript:' not in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_copy_ai_response_writes_markdown_llm_note_clipboard(monkeypatch) -> None:
    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-key",
        user_content="Explain it",
        provider="ollama",
        model="qwen3:8b",
    )
    raw_markdown = "# Result\n\nInline math: $x^2$."
    note_content = (
        "<div># Result</div>"
        "<div></div>"
        "<div>Inline math: $x^2$.</div>"
    )
    store.append_delta(
        session_key="session-key",
        turn_id=turn_id,
        delta_kind="content",
        text=raw_markdown,
    )
    store.complete_turn(
        session_key="session-key",
        turn_id=turn_id,
        final_content=raw_markdown,
    )
    copied_payloads = []
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-key")
    monkeypatch.setattr(
        ai_routes,
        "set_clipboard",
        lambda client_id, records: copied_payloads.append((client_id, records)),
    )

    response = ai_routes.copy_ai_message(
        message_id=turn_id,
        payload=ai_routes.AiCopyMessageRequest(client_id="client-123"),
        token="auth-token",
    )

    assert response.message_id == turn_id
    assert response.plain_text == raw_markdown
    assert response.tags == "@markdown @llm"
    assert "<h1>Result</h1>" in response.html
    assert '<math xmlns="http://www.w3.org/1998/Math/MathML"' in response.html
    assert copied_payloads == [
        (
            "client-123",
            [
                {
                    "id": f"ai-chat:{turn_id}",
                    "parent_id": None,
                    "prev_id": None,
                    "next_id": None,
                    "is_collapsed": False,
                    "content": note_content,
                    "tags": "@markdown @llm",
                }
            ],
        )
    ]


def test_copy_ai_response_rejects_user_message(monkeypatch) -> None:
    store = AiChatSessionStore()
    store.start_turn(
        session_key="session-key",
        user_content="Do not copy me",
        provider="ollama",
        model="qwen3:8b",
    )
    user_message_id = store.snapshot(session_key="session-key")["messages"][0]["id"]
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-key")

    with pytest.raises(HTTPException) as exc_info:
        ai_routes.copy_ai_message(
            message_id=user_message_id,
            payload=ai_routes.AiCopyMessageRequest(client_id="client-123"),
            token="auth-token",
        )

    assert exc_info.value.status_code == 404


def test_copy_ai_response_rejects_streaming_message(monkeypatch) -> None:
    store = AiChatSessionStore()
    turn_id = store.start_turn(
        session_key="session-key",
        user_content="Wait for it",
        provider="ollama",
        model="qwen3:8b",
    )
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-key")

    with pytest.raises(HTTPException) as exc_info:
        ai_routes.copy_ai_message(
            message_id=turn_id,
            payload=ai_routes.AiCopyMessageRequest(client_id="client-123"),
            token="auth-token",
        )

    assert exc_info.value.status_code == 409


def test_clear_ai_session_removes_only_current_session(monkeypatch) -> None:
    store = AiChatSessionStore()
    traces = AgentTraceStore()
    store.start_turn(
        session_key="session-a",
        user_content="A",
        provider="ollama",
        model="qwen3:8b",
    )
    store.start_turn(
        session_key="session-b",
        user_content="B",
        provider="ollama",
        model="qwen3:8b",
    )
    traces.set_exact_details_enabled(session_key="session-a", enabled=True)
    traces.start_run(session_key="session-a", model="qwen3:8b", user_message="A")
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "agent_trace_store", traces)
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-a")

    http_response = Response()
    response = ai_routes.clear_ai_session(response=http_response, token="auth-token")

    assert response.message == "Chat cleared"
    assert http_response.headers["Cache-Control"] == "no-store"
    assert store.snapshot(session_key="session-a") == {"messages": []}
    assert len(store.snapshot(session_key="session-b")["messages"]) == 2
    assert traces.snapshot(session_key="session-a") == {
        "enabled": True,
        "has_trace": False,
        "run": {},
    }


def test_debug_trace_defaults_to_exact_details_and_can_hide_them_afterward(monkeypatch) -> None:
    traces = AgentTraceStore()
    monkeypatch.setattr(ai_routes, "agent_trace_store", traces)
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-a")

    run_id = traces.start_run(
        session_key="session-a",
        model="qwen3:8b",
        user_message="Why did this fail?",
    )
    traces.fail_run(
        session_key="session-a",
        run_id=run_id,
        error="Validation failed",
    )
    initial_http_response = Response()
    initial = ai_routes.get_ai_debug_snapshot(
        response=initial_http_response,
        token="auth-token",
    )
    hidden = ai_routes.put_ai_debug_details(
        payload=ai_routes.AiDebugDetailToggleRequest(enabled=False),
        response=Response(),
        token="auth-token",
    )

    assert initial.enabled is True
    assert initial.has_trace is True
    assert initial.run["run_id"] == run_id
    assert initial.run["status"] == "error"
    assert initial_http_response.headers["Cache-Control"] == "no-store"
    assert hidden.enabled is False
    assert hidden.has_trace is True
    assert hidden.run["run_id"] == run_id
    assert traces.snapshot(session_key="session-b")["enabled"] is True


def test_stream_chat_updates_server_history_and_emits_typed_events(monkeypatch) -> None:
    store = AiChatSessionStore()

    class FakeRuntime:
        async def stream(
            self,
            *,
            session_key,
            base_url,
            selected_model,
            thinking_level,
            canonical_messages,
            prompts,
            skills,
            retrieval_settings,
        ):
            assert session_key == "session-key"
            assert base_url == "http://127.0.0.1:11435"
            assert selected_model == "qwen3:8b"
            assert thinking_level == "low"
            assert canonical_messages == [{"role": "user", "content": "Hello"}]
            assert prompts.system_prompt == "Custom system prompt"
            assert prompts.final_response_prompt == DEFAULT_AGENT_PROMPTS.final_response_prompt
            assert prompts.tool_result_prompt == DEFAULT_AGENT_PROMPTS.tool_result_prompt
            assert skills == DEFAULT_AGENT_SKILLS
            assert retrieval_settings.max_note_characters == 4_000
            assert retrieval_settings.max_page_characters == 30_000
            assert retrieval_settings.max_notes_per_page == 3
            yield {
                "type": "action_status",
                "action": "planning",
                "status": "started",
                "label": "Planning next action",
                "approx_input_tokens": 1_300,
            }
            yield {"type": "thinking_delta", "text": "Think"}
            yield {
                "type": "content_delta",
                "text": "Hi",
                "reference_note_ids": [],
            }
            yield {"type": "done", "reference_note_ids": []}

    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "agent_runtime", FakeRuntime())
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-key")
    monkeypatch.setattr(
        ai_routes,
        "load_client_preferences",
        lambda *, token: {
            SYSTEM_PROMPT_PREFERENCE_KEY: "Custom system prompt",
            "pref.ai.retrieval.max_note_characters": "4000",
            "pref.ai.retrieval.max_page_characters": "30000",
            "pref.ai.retrieval.max_notes_per_page": "3",
        },
    )

    response = ai_routes.stream_ai_chat(
        payload=ai_routes.AiChatRequest(
            provider="ollama",
            model="qwen3:8b",
            thinking_level="low",
            message="Hello",
        ),
        token="auth-token",
    )

    assert response.headers["content-encoding"] == "identity"
    assert response.headers["x-accel-buffering"] == "no"

    async def read_events() -> list[dict[str, object]]:
        raw_chunks = [chunk async for chunk in response.body_iterator]
        return [json.loads(chunk) for chunk in raw_chunks]

    events = asyncio.run(read_events())
    snapshot = store.snapshot(session_key="session-key")

    _assert_positive_activity_token_counts(events)
    assert _without_activity_token_counts(events) == [
        {
            "type": "action_status",
            "action": "ollama_runtime",
            "status": "started",
            "label": "Starting MetaList-managed Ollama · 32,768-token context",
        },
        {
            "type": "action_status",
            "action": "ollama_runtime",
            "status": "completed",
            "label": "MetaList-managed Ollama ready · 32,768-token context",
        },
        {
            "type": "action_status",
            "action": "planning",
            "status": "started",
            "label": "Planning next action",
        },
        {
            "type": "thinking_delta",
            "text": "Think",
            "rendered_text": "<p>Think</p>",
        },
        {
            "type": "content_delta",
            "text": "Hi",
            "reference_note_ids": [],
            "rendered_text": "<p>Hi</p>",
        },
        {
            "type": "done",
            "reference_note_ids": [],
            "content": "Hi",
            "rendered_content": "<p>Hi</p>",
        },
    ]
    assert snapshot["messages"][1]["thinking"] == "Think"
    assert snapshot["messages"][1]["content"] == "Hi"
    assert snapshot["messages"][1]["status"] == "complete"
    assert _without_activity_token_counts(
        snapshot["messages"][1]["activities"]
    ) == [
        {
            "action": "ollama_runtime",
            "status": "started",
            "label": "Starting MetaList-managed Ollama · 32,768-token context",
        },
        {
            "action": "ollama_runtime",
            "status": "completed",
            "label": "MetaList-managed Ollama ready · 32,768-token context",
        },
        {
            "action": "planning",
            "status": "started",
            "label": "Planning next action",
        }
    ]


def test_stream_chat_records_client_cancellation_in_the_turn(monkeypatch) -> None:
    store = AiChatSessionStore()

    class FakeRuntime:
        async def stream(self, **kwargs):
            del kwargs
            yield {
                "type": "action_status",
                "action": "model_request",
                "status": "started",
                "label": "Ollama choosing next action · attempt 1 of 2",
                "approx_input_tokens": 1_400,
            }
            await asyncio.Event().wait()

    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "agent_runtime", FakeRuntime())
    monkeypatch.setattr(
        ai_routes.token_service,
        "get_session_key",
        lambda token: "session-key",
    )
    monkeypatch.setattr(
        ai_routes,
        "load_client_preferences",
        lambda *, token: {},
    )

    response = ai_routes.stream_ai_chat(
        payload=ai_routes.AiChatRequest(
            provider="ollama",
            model="qwen3:8b",
            thinking_level="low",
            message="Cancel this request",
        ),
        token="auth-token",
    )

    async def cancel_after_first_event() -> None:
        body_iterator = response.body_iterator
        await anext(body_iterator)
        pending_event = asyncio.create_task(anext(body_iterator))
        await asyncio.sleep(0)
        pending_event.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_event

    asyncio.run(cancel_after_first_event())
    assistant_message = store.snapshot(session_key="session-key")["messages"][1]

    assert assistant_message["status"] == "error"
    assert assistant_message["error"] == "Cancelled by user"
    assert assistant_message["activities"][-1]["approx_input_tokens"] > 0
    assert _without_activity_token_counts([assistant_message["activities"][-1]]) == [{
        "action": "cancel",
        "status": "completed",
        "label": "Cancelled by user",
    }]


def test_stream_chat_blocks_references_from_an_earlier_turn(monkeypatch) -> None:
    stale_note_id = "75193dae-9e05-4a4e-94bf-417ffde18957"

    class FakeNotes:
        def has_note(self, note_id: str) -> bool:
            return note_id == stale_note_id

        def get_note(self, note_id: str):
            assert note_id == stale_note_id
            return SimpleNamespace(
                parent_id=None,
                content="<p>Testosterone and sleep</p>",
                tags="health",
            )

    class FakeRuntime:
        async def stream(
            self,
            *,
            session_key,
            base_url,
            selected_model,
            thinking_level,
            canonical_messages,
            prompts,
            skills,
            retrieval_settings,
        ):
            del session_key, base_url, selected_model, thinking_level
            del prompts, skills, retrieval_settings
            assert canonical_messages == [
                {"role": "user", "content": "Summarize testosterone notes"},
                {"role": "assistant", "content": "Sleep affects testosterone."},
                {"role": "user", "content": "Describe Bayes' theorem briefly"},
            ]
            yield {
                "type": "content_delta",
                "text": f"Bayes updates a prior. [[{stale_note_id}]]",
                "reference_note_ids": [],
            }
            yield {"type": "done", "reference_note_ids": []}

    store = AiChatSessionStore()
    prior_turn_id = store.start_turn(
        session_key="session-key",
        user_content="Summarize testosterone notes",
        provider="ollama",
        model="qwen3:8b",
    )
    prior_content = f"Sleep affects testosterone. [[{stale_note_id}]]"
    store.append_delta(
        session_key="session-key",
        turn_id=prior_turn_id,
        delta_kind="content",
        text=prior_content,
    )
    store.complete_turn(
        session_key="session-key",
        turn_id=prior_turn_id,
        final_content=prior_content,
    )
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "agent_runtime", FakeRuntime())
    monkeypatch.setattr(ai_routes, "note_store", FakeNotes())
    monkeypatch.setattr(
        ai_routes.token_service,
        "get_session_key",
        lambda token: "session-key",
    )
    monkeypatch.setattr(ai_routes, "load_client_preferences", lambda *, token: {})

    response = ai_routes.stream_ai_chat(
        payload=ai_routes.AiChatRequest(
            provider="ollama",
            model="qwen3:8b",
            thinking_level="low",
            message="Describe Bayes' theorem briefly",
        ),
        token="auth-token",
    )

    async def read_events() -> list[dict[str, object]]:
        raw_chunks = [chunk async for chunk in response.body_iterator]
        return [json.loads(chunk) for chunk in raw_chunks]

    events = asyncio.run(read_events())
    content_event = events[2]
    assert stale_note_id not in content_event["rendered_text"]
    assert "Testosterone and sleep" not in content_event["rendered_text"]
    assert "ai-chat-references" not in content_event["rendered_text"]
    assert events[3] == {
        "type": "done",
        "reference_note_ids": [],
        "content": "Bayes updates a prior.",
        "rendered_content": "<p>Bayes updates a prior.</p>",
    }
    snapshot = store.snapshot(session_key="session-key")
    assert snapshot["messages"][-1]["content"] == "Bayes updates a prior."


def test_stream_chat_persists_and_emits_ollama_failure(monkeypatch) -> None:
    store = AiChatSessionStore()

    class FailingRuntime:
        async def stream(
            self,
            *,
            session_key,
            base_url,
            selected_model,
            thinking_level,
            canonical_messages,
            prompts,
            skills,
            retrieval_settings,
        ):
            del session_key, base_url, selected_model, thinking_level
            del canonical_messages, prompts, skills, retrieval_settings
            raise OllamaProviderError("Ollama generation failed")
            yield

    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "agent_runtime", FailingRuntime())
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-key")
    monkeypatch.setattr(ai_routes, "load_client_preferences", lambda *, token: {})

    response = ai_routes.stream_ai_chat(
        payload=ai_routes.AiChatRequest(
            provider="ollama",
            model="qwen3:8b",
            thinking_level="high",
            message="Hello",
        ),
        token="auth-token",
    )

    async def read_events() -> list[dict[str, object]]:
        raw_chunks = [chunk async for chunk in response.body_iterator]
        return [json.loads(chunk) for chunk in raw_chunks]

    events = asyncio.run(read_events())
    snapshot = store.snapshot(session_key="session-key")

    _assert_positive_activity_token_counts(events)
    assert _without_activity_token_counts(events) == [
        {
            "type": "action_status",
            "action": "ollama_runtime",
            "status": "started",
            "label": "Starting MetaList-managed Ollama · 32,768-token context",
        },
        {
            "type": "action_status",
            "action": "ollama_runtime",
            "status": "completed",
            "label": "MetaList-managed Ollama ready · 32,768-token context",
        },
        {"type": "error", "message": "Ollama generation failed"},
    ]
    assert snapshot["messages"][1]["status"] == "error"
    assert snapshot["messages"][1]["error"] == "Ollama generation failed"


def test_chat_request_rejects_disabled_gpt_oss_thinking() -> None:
    with pytest.raises(ValueError, match="does not support disabling thinking"):
        ai_routes.AiChatRequest(
            provider="ollama",
            model="gpt-oss:20b",
            thinking_level="off",
            message="Hello",
        )


def test_ai_requests_reject_obsolete_client_selected_ollama_url() -> None:
    with pytest.raises(ValidationError, match="base_url"):
        ai_routes.AiModelsRequest(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
        )


def test_model_discovery_maps_ollama_failure_to_bad_gateway(monkeypatch) -> None:
    class FailingProvider:
        async def list_models(self, *, base_url):
            raise OllamaProviderError("Could not connect to Ollama")

    monkeypatch.setattr(ai_routes, "ollama_provider", FailingProvider())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ai_routes.list_ai_models(
                payload=ai_routes.AiModelsRequest(
                    provider="ollama",
                ),
                token="auth-token",
            )
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Could not connect to Ollama"


def test_model_pull_route_streams_progress_from_ollama(monkeypatch) -> None:
    class FakeProvider:
        async def stream_pull(self, *, base_url, model):
            assert base_url == "http://127.0.0.1:11435"
            assert model == "gemma3:4b"
            yield {
                "type": "progress",
                "status": "pulling layer",
                "completed": 50,
                "total": 100,
            }
            yield {
                "type": "done",
                "status": "success",
                "completed": 100,
                "total": 100,
            }

    monkeypatch.setattr(ai_routes, "ollama_provider", FakeProvider())

    response = ai_routes.pull_ai_model(
        payload=ai_routes.AiModelPullRequest(
            provider="ollama",
            model="gemma3:4b",
        ),
        token="auth-token",
    )

    async def read_events() -> list[dict[str, object]]:
        raw_chunks = [chunk async for chunk in response.body_iterator]
        return [json.loads(chunk) for chunk in raw_chunks]

    assert asyncio.run(read_events()) == [
        {
            "type": "progress",
            "status": "pulling layer",
            "completed": 50,
            "total": 100,
        },
        {
            "type": "done",
            "status": "success",
            "completed": 100,
            "total": 100,
        },
    ]
