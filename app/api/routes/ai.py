"""Authenticated AI provider and session-chat endpoints."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.api.request_auth import require_request_auth_token
from app.api.transactions import transactional_route
from app.services.ai_chat import ai_chat_store
from app.services.markdown_rendering import render_markdown_to_html
from app.services.ollama_provider import OllamaProviderError
from app.services.ollama_provider import normalize_ollama_base_url
from app.services.ollama_provider import ollama_provider
from app.services.ollama_provider import validate_ollama_model
from app.services.tokens import token_service


router = APIRouter(prefix="/ai", tags=["ai"])


class AiModelsRequest(BaseModel):
    provider: Literal["ollama"]
    base_url: str

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_ollama_base_url(value)


class AiModelsResponse(BaseModel):
    models: list[str]


class AiChatRequest(BaseModel):
    provider: Literal["ollama"]
    base_url: str
    model: str
    message: str = Field(..., max_length=32_000)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_ollama_base_url(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return validate_ollama_model(value)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Chat message must not be blank")
        return value


class AiChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    rendered_content: str
    thinking: str
    rendered_thinking: str
    status: Literal["complete", "streaming", "error"]
    error: str
    provider: Literal["ollama"]
    model: str


class AiSessionResponse(BaseModel):
    messages: list[AiChatMessage]


class AiClearResponse(BaseModel):
    message: str


@router.post("/models", response_model=AiModelsResponse)
@transactional_route
async def list_ai_models(
    payload: AiModelsRequest,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiModelsResponse:
    del token
    try:
        models = await ollama_provider.list_models(base_url=payload.base_url)
    except OllamaProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AiModelsResponse(models=models)


@router.get("/session", response_model=AiSessionResponse)
def get_ai_session(
    response: Response,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    session_key = token_service.get_session_key(token)
    snapshot = ai_chat_store.snapshot(session_key=session_key)
    messages: list[AiChatMessage] = []
    for message in snapshot["messages"]:
        rendered_content = ""
        rendered_thinking = ""
        if message["role"] == "assistant" and message["content"] != "":
            rendered_content = render_markdown_to_html(message["content"])
        if message["role"] == "assistant" and message["thinking"] != "":
            rendered_thinking = render_markdown_to_html(message["thinking"])
        messages.append(
            AiChatMessage(
                id=message["id"],
                role=message["role"],
                content=message["content"],
                rendered_content=rendered_content,
                thinking=message["thinking"],
                rendered_thinking=rendered_thinking,
                status=message["status"],
                error=message["error"],
                provider=message["provider"],
                model=message["model"],
            )
        )
    return AiSessionResponse(messages=messages)


@router.delete("/session", response_model=AiClearResponse)
@transactional_route
def clear_ai_session(
    response: Response,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiClearResponse:
    response.headers["Cache-Control"] = "no-store"
    session_key = token_service.get_session_key(token)
    ai_chat_store.clear_session(session_key=session_key)
    return AiClearResponse(message="Chat cleared")


@router.post("/chat")
@transactional_route
def stream_ai_chat(
    payload: AiChatRequest,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> StreamingResponse:
    session_key = token_service.get_session_key(token)
    turn_id = ai_chat_store.start_turn(
        session_key=session_key,
        user_content=payload.message,
        provider=payload.provider,
        model=payload.model,
    )
    provider_messages = ai_chat_store.provider_messages(session_key=session_key)

    async def stream_events() -> AsyncIterator[str]:
        accumulated_thinking = ""
        accumulated_content = ""
        try:
            async for event in ollama_provider.stream_chat(
                base_url=payload.base_url,
                model=payload.model,
                messages=provider_messages,
            ):
                event_type = event["type"]
                outgoing_event = event
                if event_type == "thinking_delta":
                    ai_chat_store.append_delta(
                        session_key=session_key,
                        turn_id=turn_id,
                        delta_kind="thinking",
                        text=event["text"],
                    )
                    accumulated_thinking += event["text"]
                    outgoing_event = {
                        **event,
                        "rendered_text": render_markdown_to_html(accumulated_thinking),
                    }
                elif event_type == "content_delta":
                    ai_chat_store.append_delta(
                        session_key=session_key,
                        turn_id=turn_id,
                        delta_kind="content",
                        text=event["text"],
                    )
                    accumulated_content += event["text"]
                    outgoing_event = {
                        **event,
                        "rendered_text": render_markdown_to_html(accumulated_content),
                    }
                elif event_type == "done":
                    ai_chat_store.complete_turn(
                        session_key=session_key,
                        turn_id=turn_id,
                    )
                else:
                    raise RuntimeError(f"Unknown Ollama stream event type: {event_type}")
                yield f"{json.dumps(outgoing_event, separators=(',', ':'))}\n"
        # lint: allow-PY001 rationale="stream errors must be delivered after response headers are sent"
        except OllamaProviderError as exc:
            error_message = str(exc)
            ai_chat_store.fail_turn(
                session_key=session_key,
                turn_id=turn_id,
                error=error_message,
            )
            event = {"type": "error", "message": error_message}
            yield f"{json.dumps(event, separators=(',', ':'))}\n"
        except asyncio.CancelledError:
            ai_chat_store.fail_turn(
                session_key=session_key,
                turn_id=turn_id,
                error="Response interrupted",
            )
            raise

    return StreamingResponse(
        stream_events(),
        media_type="application/x-ndjson",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-store",
            "Content-Encoding": "identity",
        },
    )
