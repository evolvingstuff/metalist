import asyncio
import json

import pytest
from fastapi import HTTPException, Response

import app.api.routes.ai as ai_routes
from app.services.ai_chat import AiChatSessionStore
from app.services.ollama_provider import OllamaProviderError


def test_ai_session_snapshot_uses_authenticated_session_key(monkeypatch) -> None:
    store = AiChatSessionStore()
    store.start_turn(
        session_key="session-key",
        user_content="Hello",
        provider="ollama",
        model="qwen3:8b",
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
    store.complete_turn(session_key="session-key", turn_id=turn_id)
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
    store.complete_turn(session_key="session-key", turn_id=turn_id)
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


def test_clear_ai_session_removes_only_current_session(monkeypatch) -> None:
    store = AiChatSessionStore()
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
    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-a")

    http_response = Response()
    response = ai_routes.clear_ai_session(response=http_response, token="auth-token")

    assert response.message == "Chat cleared"
    assert http_response.headers["Cache-Control"] == "no-store"
    assert store.snapshot(session_key="session-a") == {"messages": []}
    assert len(store.snapshot(session_key="session-b")["messages"]) == 2


def test_stream_chat_updates_server_history_and_emits_typed_events(monkeypatch) -> None:
    store = AiChatSessionStore()

    class FakeProvider:
        async def stream_chat(self, *, base_url, model, thinking_level, messages):
            assert base_url == "http://127.0.0.1:11434"
            assert model == "qwen3:8b"
            assert thinking_level == "low"
            assert messages == [{"role": "user", "content": "Hello"}]
            yield {"type": "thinking_delta", "text": "Think"}
            yield {"type": "content_delta", "text": "Hi"}
            yield {"type": "done"}

    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "ollama_provider", FakeProvider())
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-key")

    response = ai_routes.stream_ai_chat(
        payload=ai_routes.AiChatRequest(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
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

    assert events == [
        {
            "type": "thinking_delta",
            "text": "Think",
            "rendered_text": "<p>Think</p>",
        },
        {
            "type": "content_delta",
            "text": "Hi",
            "rendered_text": "<p>Hi</p>",
        },
        {"type": "done"},
    ]
    assert snapshot["messages"][1]["thinking"] == "Think"
    assert snapshot["messages"][1]["content"] == "Hi"
    assert snapshot["messages"][1]["status"] == "complete"


def test_stream_chat_persists_and_emits_ollama_failure(monkeypatch) -> None:
    store = AiChatSessionStore()

    class FailingProvider:
        async def stream_chat(self, *, base_url, model, thinking_level, messages):
            del base_url, model, thinking_level, messages
            raise OllamaProviderError("Ollama generation failed")
            yield

    monkeypatch.setattr(ai_routes, "ai_chat_store", store)
    monkeypatch.setattr(ai_routes, "ollama_provider", FailingProvider())
    monkeypatch.setattr(ai_routes.token_service, "get_session_key", lambda token: "session-key")

    response = ai_routes.stream_ai_chat(
        payload=ai_routes.AiChatRequest(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
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

    assert events == [{"type": "error", "message": "Ollama generation failed"}]
    assert snapshot["messages"][1]["status"] == "error"
    assert snapshot["messages"][1]["error"] == "Ollama generation failed"


def test_chat_request_rejects_disabled_gpt_oss_thinking() -> None:
    with pytest.raises(ValueError, match="does not support disabling thinking"):
        ai_routes.AiChatRequest(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="gpt-oss:20b",
            thinking_level="off",
            message="Hello",
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
                    base_url="http://127.0.0.1:11434",
                ),
                token="auth-token",
            )
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Could not connect to Ollama"
