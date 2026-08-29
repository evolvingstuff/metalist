"""Authenticated AI provider and session-chat endpoints."""

from __future__ import annotations

import asyncio
import html
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.request_auth import require_request_auth_token
from app.api.transactions import transactional_route
from app.models.utils import note_data_to_html
from app.models.utils import render_note_data_read_only
from app.services.ai_chat import ai_chat_store
from app.services.ai_chat_rendering import find_note_citation_ids
from app.services.ai_chat_rendering import render_ai_chat_markdown_to_html
from app.services.ai_chat_rendering import sanitize_ai_chat_markdown_citations
from app.services.agent.context import AgentContextBuilder
from app.services.agent.model_policy import SingleModelPolicy
from app.services.agent.ollama_inference import OllamaInferenceAdapter
from app.services.agent.permissions import AgentPermissionPolicy
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.prompt_settings import resolve_agent_prompt_set
from app.services.agent.retrieval_settings import resolve_agent_retrieval_settings
from app.services.agent.runtime import AgentExecutionError
from app.services.agent.runtime import AgentRuntime
from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.skill_settings import resolve_agent_skill_set
from app.services.agent.token_estimation import estimate_input_tokens
from app.services.agent.tools import read_only_agent_tools
from app.services.agent.trace import agent_trace_store
from app.services.client_state_service import load_client_preferences
from app.services.markdown_rendering import render_markdown_to_html
from app.services.managed_ollama_runtime import ManagedOllamaRuntimeError
from app.services.managed_ollama_runtime import managed_ollama_runtime
from app.services.note_store import store as note_store
from app.services.ollama_provider import OllamaProviderError
from app.services.ollama_provider import ollama_provider
from app.services.ollama_provider import resolve_ollama_think_value
from app.services.ollama_provider import validate_ollama_model
from app.services.sync import set_clipboard
from app.services.tokens import token_service


router = APIRouter(prefix="/ai", tags=["ai"])

agent_context_builder = AgentContextBuilder()
agent_runtime = AgentRuntime(
    context_builder=agent_context_builder,
    inference=OllamaInferenceAdapter(provider=ollama_provider),
    model_policy=SingleModelPolicy(),
    permission_policy=AgentPermissionPolicy(),
    tool_registry=read_only_agent_tools,
    trace_store=agent_trace_store,
)


def _event_reference_note_ids(event: dict[str, object]) -> frozenset[str]:
    raw_note_ids = event["reference_note_ids"]
    if not isinstance(raw_note_ids, list):
        raise RuntimeError("Agent reference_note_ids event field must be a list")
    note_ids: set[str] = set()
    for note_id in raw_note_ids:
        if not isinstance(note_id, str) or note_id == "":
            raise RuntimeError("Agent reference note id must be non-empty")
        if note_id in note_ids:
            raise RuntimeError("Agent reference_note_ids event field has duplicates")
        note_ids.add(note_id)
    return frozenset(note_ids)


class AiModelsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama"]


class AiModelsResponse(BaseModel):
    models: list[str]


class AiSkillDefaultResponse(BaseModel):
    skill_id: str
    title: str
    description: str
    trigger_action: str
    preference_key: str
    content: str


class AiPromptDefaultsResponse(BaseModel):
    system_prompt: str
    final_response_prompt: str
    tool_result_prompt: str
    skills: list[AiSkillDefaultResponse]


class AiModelPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama"]
    model: str

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return validate_ollama_model(value)


class AiChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama"]
    model: str
    thinking_level: Literal["off", "low", "medium", "high"]
    message: str = Field(..., max_length=32_000)

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

    @model_validator(mode="after")
    def validate_thinking_level_for_model(self) -> Self:
        resolve_ollama_think_value(
            model=self.model,
            thinking_level=self.thinking_level,
        )
        return self


class AiChatActivity(BaseModel):
    sequence: int = Field(..., ge=1)
    action: str
    status: Literal["started", "completed"]
    label: str
    approx_input_tokens: int = Field(..., ge=1)


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
    activities: list[AiChatActivity]


class AiSessionResponse(BaseModel):
    messages: list[AiChatMessage]


class AiClearResponse(BaseModel):
    message: str


class AiDebugDetailToggleRequest(BaseModel):
    enabled: bool


class AiDebugSnapshotResponse(BaseModel):
    enabled: bool
    has_trace: bool
    run: dict[str, Any]


class AiCopyMessageRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, value: str) -> str:
        normalized = value.strip()
        if normalized == "":
            raise ValueError("Client id must not be blank")
        return normalized


class AiCopyMessageResponse(BaseModel):
    message_id: str
    html: str
    plain_text: str
    tags: str


def _markdown_to_note_content_html(markdown_text: str) -> str:
    if not isinstance(markdown_text, str) or markdown_text == "":
        raise ValueError("AI response Markdown must be a non-empty string")
    return "".join(
        f"<div>{html.escape(line)}</div>"
        for line in markdown_text.split("\n")
    )


@router.post("/models", response_model=AiModelsResponse)
@transactional_route
async def list_ai_models(
    payload: AiModelsRequest,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiModelsResponse:
    del token
    try:
        runtime_info = await asyncio.to_thread(managed_ollama_runtime.ensure_running)
        models = await ollama_provider.list_models(base_url=runtime_info.base_url)
    except (ManagedOllamaRuntimeError, OllamaProviderError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AiModelsResponse(models=models)


@router.get("/prompts/defaults", response_model=AiPromptDefaultsResponse)
def get_ai_prompt_defaults(
    response: Response,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiPromptDefaultsResponse:
    del token
    response.headers["Cache-Control"] = "no-store"
    return AiPromptDefaultsResponse(
        system_prompt=DEFAULT_AGENT_PROMPTS.system_prompt,
        final_response_prompt=DEFAULT_AGENT_PROMPTS.final_response_prompt,
        tool_result_prompt=DEFAULT_AGENT_PROMPTS.tool_result_prompt,
        skills=[
            AiSkillDefaultResponse(
                skill_id=skill.skill_id,
                title=skill.title,
                description=skill.description,
                trigger_action=skill.trigger_action,
                preference_key=skill.preference_key,
                content=skill.content,
            )
            for skill in DEFAULT_AGENT_SKILLS.skills
        ],
    )


@router.post("/models/pull")
@transactional_route
def pull_ai_model(
    payload: AiModelPullRequest,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> StreamingResponse:
    del token

    async def stream_events() -> AsyncIterator[str]:
        try:
            runtime_info = await asyncio.to_thread(managed_ollama_runtime.ensure_running)
            async for event in ollama_provider.stream_pull(
                base_url=runtime_info.base_url,
                model=payload.model,
            ):
                yield f"{json.dumps(event, separators=(',', ':'))}\n"
        # lint: allow-PY001 rationale="pull errors must be delivered after response headers are sent"
        except (ManagedOllamaRuntimeError, OllamaProviderError) as exc:
            error_event = {"type": "error", "message": str(exc)}
            yield f"{json.dumps(error_event, separators=(',', ':'))}\n"

    return StreamingResponse(
        stream_events(),
        media_type="application/x-ndjson",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-store",
            "Content-Encoding": "identity",
        },
    )


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
        activities = message["activities"]
        if not isinstance(activities, list):
            raise TypeError("AI chat message activities must be a list")
        rendered_content = ""
        rendered_thinking = ""
        if message["role"] == "assistant" and message["content"] != "":
            allowed_note_ids = find_note_citation_ids(
                message["content"],
                notes=note_store,
            )
            rendered_content = render_ai_chat_markdown_to_html(
                message["content"],
                notes=note_store,
                allowed_note_ids=allowed_note_ids,
            )
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
                activities=[
                    AiChatActivity(
                        sequence=index,
                        action=activity["action"],
                        status=activity["status"],
                        label=activity["label"],
                        approx_input_tokens=activity["approx_input_tokens"],
                    )
                    for index, activity in enumerate(activities, start=1)
                ],
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
    agent_trace_store.clear_trace(session_key=session_key)
    return AiClearResponse(message="Chat cleared")


@router.get("/debug", response_model=AiDebugSnapshotResponse)
def get_ai_debug_snapshot(
    response: Response,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiDebugSnapshotResponse:
    response.headers["Cache-Control"] = "no-store"
    session_key = token_service.get_session_key(token)
    return AiDebugSnapshotResponse.model_validate(
        agent_trace_store.snapshot(session_key=session_key)
    )


@router.put("/debug", response_model=AiDebugSnapshotResponse)
@transactional_route
def put_ai_debug_details(
    payload: AiDebugDetailToggleRequest,
    response: Response,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiDebugSnapshotResponse:
    response.headers["Cache-Control"] = "no-store"
    session_key = token_service.get_session_key(token)
    agent_trace_store.set_exact_details_enabled(
        session_key=session_key,
        enabled=payload.enabled,
    )
    return AiDebugSnapshotResponse.model_validate(
        agent_trace_store.snapshot(session_key=session_key)
    )


@router.post("/messages/{message_id}/copy", response_model=AiCopyMessageResponse)
@transactional_route
def copy_ai_message(
    message_id: str,
    payload: AiCopyMessageRequest,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> AiCopyMessageResponse:
    if message_id.strip() == "":
        raise HTTPException(status_code=404, detail="AI response not found")
    session_key = token_service.get_session_key(token)
    snapshot = ai_chat_store.snapshot(session_key=session_key)
    matching_messages = [
        message
        for message in snapshot["messages"]
        if message["id"] == message_id and message["role"] == "assistant"
    ]
    if len(matching_messages) == 0:
        raise HTTPException(status_code=404, detail="AI response not found")
    if len(matching_messages) != 1:
        raise RuntimeError("AI chat session contains duplicate message ids")

    message = matching_messages[0]
    if message["status"] != "complete":
        raise HTTPException(status_code=409, detail="AI response is not complete")
    content = message["content"]
    if content == "":
        raise HTTPException(status_code=409, detail="AI response is empty")

    tags = "@markdown @llm"
    note_content = _markdown_to_note_content_html(content)
    clipboard_record = {
        "id": f"ai-chat:{message_id}",
        "parent_id": None,
        "prev_id": None,
        "next_id": None,
        "is_collapsed": False,
        "content": note_content,
        "tags": tags,
    }
    set_clipboard(payload.client_id, [clipboard_record])

    rendered_tree = render_note_data_read_only(
        {"content": note_content, "tags": tags, "children": []},
    )
    return AiCopyMessageResponse(
        message_id=message_id,
        html=note_data_to_html(rendered_tree),
        plain_text=content,
        tags=tags,
    )


@router.post("/chat")
@transactional_route
def stream_ai_chat(
    payload: AiChatRequest,
    token: Annotated[str, Depends(require_request_auth_token)],
) -> StreamingResponse:
    session_key = token_service.get_session_key(token)
    preferences = load_client_preferences(token=token)
    prompts = resolve_agent_prompt_set(preferences=preferences)
    skills = resolve_agent_skill_set(preferences=preferences)
    retrieval_settings = resolve_agent_retrieval_settings(preferences=preferences)
    turn_id = ai_chat_store.start_turn(
        session_key=session_key,
        user_content=payload.message,
        provider=payload.provider,
        model=payload.model,
    )
    provider_messages = ai_chat_store.provider_messages(session_key=session_key)
    initial_messages = agent_context_builder.build_initial_messages(
        canonical_messages=provider_messages,
        prompts=prompts,
    )
    initial_approx_input_tokens = estimate_input_tokens(initial_messages)

    async def stream_events() -> AsyncIterator[str]:
        accumulated_thinking = ""
        accumulated_content = ""
        reference_note_ids = frozenset()
        has_reference_scope = False
        latest_approx_input_tokens = initial_approx_input_tokens
        try:
            runtime_started_event = {
                "type": "action_status",
                "action": "ollama_runtime",
                "status": "started",
                "label": "Starting MetaList-managed Ollama · 32,768-token context",
                "approx_input_tokens": latest_approx_input_tokens,
            }
            ai_chat_store.append_activity(
                session_key=session_key,
                turn_id=turn_id,
                action=runtime_started_event["action"],
                status=runtime_started_event["status"],
                label=runtime_started_event["label"],
                approx_input_tokens=runtime_started_event["approx_input_tokens"],
            )
            yield f"{json.dumps(runtime_started_event, separators=(',', ':'))}\n"
            runtime_info = await asyncio.to_thread(managed_ollama_runtime.ensure_running)
            runtime_ready_event = {
                "type": "action_status",
                "action": "ollama_runtime",
                "status": "completed",
                "label": (
                    "MetaList-managed Ollama ready · "
                    f"{runtime_info.context_tokens:,}-token context"
                ),
                "approx_input_tokens": latest_approx_input_tokens,
            }
            ai_chat_store.append_activity(
                session_key=session_key,
                turn_id=turn_id,
                action=runtime_ready_event["action"],
                status=runtime_ready_event["status"],
                label=runtime_ready_event["label"],
                approx_input_tokens=runtime_ready_event["approx_input_tokens"],
            )
            yield f"{json.dumps(runtime_ready_event, separators=(',', ':'))}\n"
            async for event in agent_runtime.stream(
                session_key=session_key,
                base_url=runtime_info.base_url,
                selected_model=payload.model,
                thinking_level=payload.thinking_level,
                canonical_messages=provider_messages,
                prompts=prompts,
                skills=skills,
                retrieval_settings=retrieval_settings,
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
                    event_reference_note_ids = _event_reference_note_ids(event)
                    if (
                        has_reference_scope
                        and event_reference_note_ids != reference_note_ids
                    ):
                        raise RuntimeError(
                            "Agent reference scope changed during final response"
                        )
                    reference_note_ids = event_reference_note_ids
                    has_reference_scope = True
                    ai_chat_store.append_delta(
                        session_key=session_key,
                        turn_id=turn_id,
                        delta_kind="content",
                        text=event["text"],
                    )
                    accumulated_content += event["text"]
                    outgoing_event = {
                        **event,
                        "rendered_text": render_ai_chat_markdown_to_html(
                            accumulated_content,
                            notes=note_store,
                            allowed_note_ids=reference_note_ids,
                        ),
                    }
                elif event_type == "action_status":
                    event_approx_input_tokens = event["approx_input_tokens"]
                    if (
                        not isinstance(event_approx_input_tokens, int)
                        or isinstance(event_approx_input_tokens, bool)
                        or event_approx_input_tokens < 1
                    ):
                        raise RuntimeError(
                            "Agent action status approximate input tokens are invalid"
                        )
                    latest_approx_input_tokens = event_approx_input_tokens
                    ai_chat_store.append_activity(
                        session_key=session_key,
                        turn_id=turn_id,
                        action=event["action"],
                        status=event["status"],
                        label=event["label"],
                        approx_input_tokens=event_approx_input_tokens,
                    )
                elif event_type == "done":
                    event_reference_note_ids = _event_reference_note_ids(event)
                    if not has_reference_scope:
                        raise RuntimeError(
                            "Agent final response completed without a reference scope"
                        )
                    if event_reference_note_ids != reference_note_ids:
                        raise RuntimeError(
                            "Agent completion reference scope does not match content"
                        )
                    final_content = sanitize_ai_chat_markdown_citations(
                        accumulated_content,
                        notes=note_store,
                        allowed_note_ids=reference_note_ids,
                    )
                    ai_chat_store.complete_turn(
                        session_key=session_key,
                        turn_id=turn_id,
                        final_content=final_content,
                    )
                    outgoing_event = {
                        **event,
                        "content": final_content,
                        "rendered_content": render_ai_chat_markdown_to_html(
                            final_content,
                            notes=note_store,
                            allowed_note_ids=reference_note_ids,
                        ),
                    }
                else:
                    raise RuntimeError(f"Unknown agent stream event type: {event_type}")
                yield f"{json.dumps(outgoing_event, separators=(',', ':'))}\n"
        # lint: allow-PY001 rationale="stream errors must be delivered after response headers are sent"
        except (AgentExecutionError, ManagedOllamaRuntimeError, OllamaProviderError) as exc:
            error_message = str(exc)
            ai_chat_store.fail_turn(
                session_key=session_key,
                turn_id=turn_id,
                error=error_message,
            )
            event = {"type": "error", "message": error_message}
            yield f"{json.dumps(event, separators=(',', ':'))}\n"
        except asyncio.CancelledError:
            ai_chat_store.append_activity(
                session_key=session_key,
                turn_id=turn_id,
                action="cancel",
                status="completed",
                label="Cancelled by user",
                approx_input_tokens=latest_approx_input_tokens,
            )
            ai_chat_store.fail_turn(
                session_key=session_key,
                turn_id=turn_id,
                error="Cancelled by user",
            )
            raise
        # lint: allow-PY001 rationale="mark the streamed turn failed before re-raising internal errors"
        except Exception:
            ai_chat_store.fail_turn(
                session_key=session_key,
                turn_id=turn_id,
                error="Internal agent error",
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
