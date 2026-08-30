import asyncio
import json
from datetime import datetime
from datetime import timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.agent.actions import AgentRouteEnvelope
from app.services.agent.actions import ReadNotesByIdAction
from app.services.agent.actions import RespondAction
from app.services.agent.actions import SearchQueryEnvelope
from app.services.agent.actions import SearchNotesIntent
from app.services.agent.actions import agent_action_adapter
from app.services.agent.actions import agent_route_response_schema
from app.services.agent.actions import parse_agent_route_json
from app.services.agent.actions import parse_search_query_json
from app.services.agent.context import AgentContextBuilder
from app.services.agent.inference import InferenceAttempt
from app.services.agent.inference import InferenceContextWindow
from app.services.agent.inference import InferenceResponse
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.inference import StructuredInferenceError
from app.services.agent.model_policy import InferencePurpose
from app.services.agent.model_policy import SingleModelPolicy
from app.services.agent.permissions import AgentPermissionPolicy
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.retrieval_settings import DEFAULT_AGENT_RETRIEVAL_SETTINGS
from app.services.agent.runtime import AgentRuntime
from app.services.agent.runtime import _final_response_max_output_tokens
from app.services.agent.runtime import AgentExecutionError
from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.skill_settings import AgentSkill
from app.services.agent.skill_settings import AgentSkillSet
from app.services.agent.tools import ToolExecutionResult
from app.services.agent.tools import ToolPermission
from app.services.agent.tools import ReadOnlyAgentToolRegistry
from app.services.agent.tools import ToolSpec
from app.services.agent.trace import AgentTraceStore


TEST_TIMESTAMP = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
LEGACY_SEARCH_SKILLS = AgentSkillSet(
    skills=(
        AgentSkill(
            skill_id="search_notes",
            title="Search notes",
            description="Legacy runtime test skill",
            trigger_action="search_notes",
            preference_key="test.legacy.search",
            content="Produce a structured MetaList search query such as foo OR bar baz.",
        ),
    )
)


def _assert_positive_activity_token_counts(events: list[dict[str, object]]) -> None:
    activities = [event for event in events if event["type"] == "action_status"]
    assert activities
    assert all(
        isinstance(event["approx_input_tokens"], int)
        and not isinstance(event["approx_input_tokens"], bool)
        and event["approx_input_tokens"] > 0
        for event in activities
    )
    assert all(
        isinstance(event["duration_ms"], (int, float))
        and not isinstance(event["duration_ms"], bool)
        and event["duration_ms"] >= 0
        for event in activities
    )


def _without_activity_token_counts(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            key: value
            for key, value in event.items()
            if key not in {
                "approx_input_tokens",
                "output_tokens_received",
                "duration_ms",
            }
        }
        for event in events
    ]


@pytest.mark.parametrize(
    ("action", "completed_search_count", "expected_label"),
    [
        (
            SearchNotesIntent(
                kind="search_notes",
                rationale="The answer depends on the user's notes.",
            ),
            0,
            "Selected action · Search notes · The answer depends on the user's notes.",
        ),
        (
            SearchNotesIntent(
                kind="search_notes",
                rationale=(
                    "The first tag-only query may have missed notes that mention the "
                    "topic only in their text."
                ),
            ),
            1,
            (
                "Selected action · Search again · The first tag-only query may have "
                "missed notes that mention the topic only in their text."
            ),
        ),
        (
            ReadNotesByIdAction(
                kind="read_notes_by_id",
                note_ids=["note-a", "note-b"],
                rationale="The user explicitly named these notes.",
            ),
            0,
            (
                "Selected action · Read 2 notes by ID · "
                "The user explicitly named these notes."
            ),
        ),
        (
            RespondAction(
                kind="respond",
                basis="The request can be answered without note retrieval.",
            ),
            0,
            (
                "Selected action · Respond to user · "
                "The request can be answered without note retrieval."
            ),
        ),
    ],
)
def test_selected_action_status_exposes_every_action_reason(
    action: SearchNotesIntent | ReadNotesByIdAction | RespondAction,
    completed_search_count: int,
    expected_label: str,
) -> None:
    event = AgentRuntime._selected_action_status_event(
        action,
        completed_search_count=completed_search_count,
        approx_input_tokens=1_234,
    )

    assert event == {
        "type": "action_status",
        "action": action.kind,
        "status": "completed",
        "label": expected_label,
            "approx_input_tokens": 1_234,
            "output_tokens_received": 0,
            "duration_ms": 0.0,
        }


def test_structured_output_progress_reports_tokens_on_the_active_model_panel() -> None:
    progress = StructuredInferenceProgress(
        phase="output_progress",
        attempt=1,
        max_attempts=2,
        failure_kind="",
        error_type="",
        error_message="",
        duration_ms=50.0,
        wire_request={
            "method": "POST",
            "url": "http://127.0.0.1:11434/v1/chat/completions",
            "body": {"messages": [{"role": "user", "content": "Summarize"}]},
        },
        output_tokens_received=24,
    )

    event = AgentRuntime._progress_status_event(
        progress,
        purpose=InferencePurpose.INVESTIGATION_STEP,
        provider_label="Ollama",
    )

    assert event["action"] == "model_request"
    assert event["status"] == "started"
    assert event["output_tokens_received"] == 24
    assert event["label"] == "Ollama updating evidence and choosing next step"


def _children_in_record_order(
    records: dict[str, SimpleNamespace],
    parent_id: str | None,
) -> list[str]:
    return [
        note_id
        for note_id, record in records.items()
        if record.parent_id == parent_id
    ]


class FakeInferenceAdapter:
    def __init__(self, *, structured_contents: list[str]) -> None:
        self._structured_contents = list(structured_contents)
        self.structured_requests: list[dict[str, object]] = []
        self.final_requests: list[dict[str, object]] = []

    async def inspect_context_window(
        self,
        *,
        base_url: str,
        model: str,
    ) -> InferenceContextWindow:
        assert base_url == "http://127.0.0.1:11434"
        assert model == "qwen3:8b"
        return InferenceContextWindow(
            model=model,
            maximum_tokens=32768,
            loaded_tokens=32768,
            required_tokens=32768,
        )

    async def infer_structured(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
        response_model: type,
        on_progress,
    ) -> InferenceResponse:
        assert self._structured_contents, "unexpected structured inference request"
        content = self._structured_contents.pop(0)
        self.structured_requests.append(
            {
                "base_url": base_url,
                "model": model,
                "thinking_level": thinking_level,
                "messages": messages,
                "response_model": response_model,
            }
        )
        for phase in ("attempt_started", "response_received", "attempt_succeeded"):
            on_progress(
                StructuredInferenceProgress(
                    phase=phase,
                    attempt=1,
                    max_attempts=2,
                    failure_kind="",
                    error_type="",
                    error_message="",
                    duration_ms=1.0,
                    wire_request={
                        "method": "POST",
                        "url": f"{base_url}/v1/chat/completions",
                        "body": {
                            "model": model,
                            "messages": messages,
                            "stream": False,
                        },
                    },
                    output_tokens_received=0,
                )
            )
        return InferenceResponse(
            content=content,
            thinking="private model reasoning",
            usage={"prompt_eval_count": 11, "eval_count": 3},
            attempts=[
                InferenceAttempt(
                    request={
                        "model": model,
                        "messages": messages,
                        "response_model": response_model.__name__,
                    },
                    response={"message": {"content": content}},
                    error="",
                    duration_ms=1.0,
                )
            ],
        )

    async def stream_text(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
        on_request,
    ):
        assert max_output_tokens == 1_024
        self.final_requests.append(
            {
                "base_url": base_url,
                "model": model,
                "thinking_level": thinking_level,
                "messages": messages,
            }
        )
        on_request(
            {
                "method": "POST",
                "url": f"{base_url}/api/chat",
                "body": {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "think": thinking_level,
                },
            }
        )
        yield {"type": "thinking_delta", "text": "Final reasoning"}
        yield {"type": "content_delta", "text": "The answer uses your SQLite note."}
        yield {"type": "done"}


class FakeToolRegistry:
    def __init__(self) -> None:
        self.executed_actions: list[object] = []

    def spec_for(self, action) -> ToolSpec:
        return ToolSpec(
            name=action.kind,
            description=f"Execute {action.kind}",
            mutates=False,
            permission=ToolPermission.READ,
        )

    def execute(self, action, *, settings) -> ToolExecutionResult:
        assert settings == DEFAULT_AGENT_RETRIEVAL_SETTINGS
        self.executed_actions.append(action)
        if action.kind == "search_notes":
            return ToolExecutionResult(
                action_name="search_notes",
                status_label="Searching notes",
                payload={
                    "query": action.query,
                    "page": action.page,
                    "page_size": settings.max_notes_per_page,
                    "total_pages": 1,
                    "has_previous_page": False,
                    "previous_page": 0,
                    "has_next_page": False,
                    "next_page": 0,
                    "page_is_out_of_range": False,
                    "matched_count": 1,
                    "matched_note_count": 1,
                    "returned_count": 1,
                    "returned_note_count": 1,
                    "returned_character_count": 34,
                    "has_truncated_content": False,
                    "max_note_characters": settings.max_note_characters,
                    "max_page_characters": settings.max_page_characters,
                    "notes": [
                        {
                            "note_id": "note-sqlite",
                            "parent_id": "",
                            "root_note_id": "note-sqlite",
                            "content_text": "Decision: keep SQLite for storage.",
                            "content_character_count": 34,
                            "returned_character_count": 34,
                            "content_is_truncated": False,
                            "content_is_redacted": False,
                            "tags": "architecture",
                            "created_at": TEST_TIMESTAMP.isoformat(),
                            "updated_at": TEST_TIMESTAMP.isoformat(),
                        }
                    ],
                },
            )
        if action.kind == "read_notes_by_id":
            return ToolExecutionResult(
                action_name="read_notes_by_id",
                status_label="Reading 1 note by ID",
                payload={
                    "notes": [
                        {
                            "note_id": "note-sqlite",
                            "content_text": "Decision: keep SQLite for local-first storage.",
                            "content_is_redacted": False,
                            "tags": "architecture",
                        }
                    ],
                    "missing_note_ids": [],
                },
            )
        raise AssertionError(f"unexpected fake tool action: {action.kind}")


def _collect_runtime_events(runtime: AgentRuntime) -> list[dict[str, object]]:
    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream(
                session_key="session-a",
                base_url="http://127.0.0.1:11434",
                selected_model="qwen3:8b",
                thinking_level="low",
                canonical_messages=[
                    {"role": "user", "content": "What did I decide about storage?"}
                ],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=LEGACY_SEARCH_SKILLS,
                retrieval_settings=DEFAULT_AGENT_RETRIEVAL_SETTINGS,
            )
        ]

    return asyncio.run(collect())


def test_runtime_rejects_an_undersized_loaded_context_before_inference() -> None:
    class LowContextInference(FakeInferenceAdapter):
        async def inspect_context_window(
            self,
            *,
            base_url: str,
            model: str,
        ) -> InferenceContextWindow:
            assert base_url == "http://127.0.0.1:11434"
            assert model == "qwen3:8b"
            return InferenceContextWindow(
                model=model,
                maximum_tokens=32768,
                loaded_tokens=4096,
                required_tokens=32768,
            )

    inference = LowContextInference(structured_contents=[])
    traces = AgentTraceStore()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=FakeToolRegistry(),
        trace_store=traces,
        provider_label="Ollama",
    )

    async def collect_until_failure() -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        with pytest.raises(
            AgentExecutionError,
            match=(
                "loaded with 4,096 context tokens; MetaList requires 32,768 for "
                "this model"
            ),
        ):
            async for event in runtime.stream(
                session_key="session-a",
                base_url="http://127.0.0.1:11434",
                selected_model="qwen3:8b",
                thinking_level="low",
                canonical_messages=[{"role": "user", "content": "Search my notes"}],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=DEFAULT_AGENT_RETRIEVAL_SETTINGS,
            ):
                events.append(event)
        return events

    events = asyncio.run(collect_until_failure())

    _assert_positive_activity_token_counts(events)
    assert _without_activity_token_counts(events) == [
        {
            "type": "action_status",
            "action": "model_context",
            "status": "started",
            "label": "Loading Ollama model and checking context",
        },
        {
            "type": "action_status",
            "action": "model_context",
            "status": "completed",
            "label": (
                "Ollama context too small · 4,096 loaded · 32,768 required"
            ),
        },
    ]
    assert inference.structured_requests == []
    trace = traces.snapshot(session_key="session-a")["run"]
    context_events = [
        event for event in trace["events"] if event["type"] == "MODEL_CONTEXT"
    ]
    assert context_events[0]["detail"] == {
        "model": "qwen3:8b",
        "maximum_tokens": 32768,
        "loaded_tokens": 4096,
        "required_tokens": 32768,
        "is_sufficient": False,
    }


def test_agent_action_schema_exposes_only_read_only_actions_and_respond() -> None:
    assert agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": '"SQLite"',
            "page": 1,
            "rationale": "Find the relevant decision note.",
        }
    ).kind == "search_notes"
    assert agent_action_adapter.validate_python(
        {
            "kind": "read_notes_by_id",
            "note_ids": ["note-sqlite"],
            "rationale": "Read the matching note.",
        }
    ).kind == "read_notes_by_id"
    assert agent_action_adapter.validate_python(
        {
            "kind": "respond",
            "basis": "Answer from the retrieved storage decision.",
        }
    ).kind == "respond"

    with pytest.raises(ValidationError):
        agent_action_adapter.validate_python(
            {
                "kind": "patch_note",
                "note_id": "note-sqlite",
                "content": "mutated",
            }
        )

    with pytest.raises(ValidationError, match="Unclosed quote"):
        agent_action_adapter.validate_python(
            {
                "kind": "search_notes",
                "query": '"unterminated',
                "page": 1,
                "rationale": "This invalid model output must be retried.",
            }
        )


def test_ollama_route_response_schema_is_a_flat_required_object() -> None:
    schema = agent_route_response_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "kind",
        "note_ids",
        "reason",
    }
    action_kinds = schema["properties"]["kind"]["enum"]
    assert set(action_kinds) == {
        "search_notes",
        "read_notes_by_id",
        "respond",
    }
    assert action_kinds[0] == "respond"
    assert "content-bearing matching notes in notes[].content_text" in (
        schema["properties"]["kind"]["description"]
    )
    assert "examples" not in schema
    assert "$defs" not in schema
    assert "oneOf" not in schema
    assert "discriminator" not in schema

    action = parse_agent_route_json(
        json.dumps(
            {
                "kind": "respond",
                "note_ids": [],
                "reason": "Reply to the greeting.",
            }
        )
    )
    assert action.kind == "respond"
    assert action.model_dump() == {
        "kind": "respond",
        "basis": "Reply to the greeting.",
    }


@pytest.mark.parametrize(
    "search_query",
    [
        '-"Pydantic AI"',
        "-private",
        'Pydantic OR -"Pydantic AI"',
    ],
)
def test_agent_search_action_rejects_exclusion_only_clauses(
    search_query: str,
) -> None:
    with pytest.raises(ValidationError, match="positive term"):
        parse_search_query_json(
            json.dumps(
                {
                    "search_query": search_query,
                    "page": 1,
                    "reason": "Find notes about the requested topic.",
                }
            )
        )


def test_agent_search_action_allows_positive_terms_with_exclusions() -> None:
    action = parse_search_query_json(
        json.dumps(
            {
                "search_query": '"Pydantic AI" -deprecated',
                "page": 1,
                "reason": "Find current notes about the requested topic.",
            }
        )
    )

    assert action.model_dump() == {
        "kind": "search_notes",
        "query": '"Pydantic AI" -deprecated',
        "page": 1,
        "rationale": "Find current notes about the requested topic.",
    }


def test_search_query_wire_schema_avoids_ollama_multi_string_length_grammar_bug() -> None:
    schema = SearchQueryEnvelope.model_json_schema()

    assert schema["type"] == "object"
    assert set(schema["required"]) == {"search_query", "page", "reason"}
    assert "minLength" not in schema["properties"]["search_query"]
    assert "maxLength" not in schema["properties"]["search_query"]
    assert "minLength" not in schema["properties"]["reason"]
    assert "maxLength" not in schema["properties"]["reason"]
    assert "earlier conversation topics" in (
        schema["properties"]["search_query"]["description"].casefold()
    )
    assert 'foo or "foo"' in (
        schema["properties"]["search_query"]["description"].casefold()
    )
    with pytest.raises(ValidationError, match="must not exceed 1000"):
        SearchQueryEnvelope(search_query="x" * 1_001, page=1, reason="Too broad")
    with pytest.raises(ValidationError, match="must not exceed 2000"):
        SearchQueryEnvelope(search_query="foo", page=1, reason="x" * 2_001)


def test_ollama_route_ignores_note_ids_for_actions_that_do_not_read_by_id() -> None:
    action = parse_agent_route_json(
        json.dumps(
            {
                "kind": "read_notes_by_id",
                "note_ids": ["note-pydantic", "note-instructor"],
                "reason": "Read the relevant search results.",
            }
        )
    )

    assert action.model_dump() == {
        "kind": "read_notes_by_id",
        "note_ids": ["note-pydantic", "note-instructor"],
        "rationale": "Read the relevant search results.",
    }

    search_action = parse_agent_route_json(
        json.dumps(
            {
                "kind": "search_notes",
                "note_ids": ["inactive-note-id"],
                "reason": "Find relevant notes.",
            }
        )
    )
    assert search_action.model_dump() == {
        "kind": "search_notes",
        "rationale": "Find relevant notes.",
    }

    respond_action = parse_agent_route_json(
        json.dumps(
            {
                "kind": "respond",
                "note_ids": ["inactive-note-id"],
                "reason": "Answer using the retrieved note content.",
            }
        )
    )
    assert respond_action.model_dump() == {
        "kind": "respond",
        "basis": "Answer using the retrieved note content.",
    }


def test_structured_inference_error_is_concise_and_keeps_attempts() -> None:
    attempts = [
        InferenceAttempt(
            request={"messages": [{"role": "user", "content": "Find Pydantic AI"}]},
            response={"content": "invalid"},
            error="ValidationError: search_query missing",
            duration_ms=1.0,
        ),
        InferenceAttempt(
            request={"messages": [{"role": "user", "content": "retry"}]},
            response={"content": "still invalid"},
            error="ValidationError: inactive field populated",
            duration_ms=1.0,
        ),
    ]

    error = StructuredInferenceError(attempts=attempts)

    assert str(error) == (
        "The model could not produce a valid structured response after 2 attempts. "
        "Open Agent Debug for exact request and response details."
    )
    assert error.attempts == attempts


def test_runtime_executes_read_only_loop_streams_status_and_traces_exact_context() -> None:
    inference = FakeInferenceAdapter(
        structured_contents=[
            json.dumps(
                {
                    "kind": "search_notes",
                    "note_ids": [],
                    "reason": "Locate the user's storage decision.",
                }
            ),
            json.dumps(
                {
                    "search_query": '"storage"',
                    "page": 1,
                    "reason": "Search for the requested storage decision.",
                }
            ),
            json.dumps(
                {
                    "kind": "respond",
                    "note_ids": [],
                    "reason": "The complete matching note says to keep SQLite.",
                }
            ),
        ]
    )
    tools = FakeToolRegistry()
    traces = AgentTraceStore()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=tools,
        trace_store=traces,
        provider_label="Ollama",
    )

    events = _collect_runtime_events(runtime)
    _assert_positive_activity_token_counts(events)

    started_labels = [
        event["label"]
        for event in events
        if event["type"] == "action_status" and event["status"] == "started"
    ]
    assert started_labels[0] == "Loading Ollama model and checking context"
    assert started_labels[1] == "Preparing action selection"
    assert started_labels[2] == "Ollama choosing next action"
    assert started_labels[3] == "Ollama returned next-action choice · validating"
    assert started_labels[4] == "Ollama preparing MetaList search query"
    assert started_labels[5] == "Ollama returned search-query proposal · validating"
    assert len(started_labels) == 12
    assert started_labels[6] == 'Searching notes · page 1 · "storage"'
    assert started_labels[7] == "Preparing action selection"
    assert started_labels[8] == "Ollama choosing next action"
    assert started_labels[9] == "Ollama returned next-action choice · validating"
    assert started_labels[10] == "Writing response"
    assert _without_activity_token_counts(events[-5:]) == [
            {"type": "thinking_delta", "text": "Final reasoning"},
            {
                "type": "action_status",
                "action": "respond",
                "status": "started",
                "label": "Writing response",
            },
            {
            "type": "content_delta",
            "text": "The answer uses your SQLite note.",
            "reference_note_ids": ["note-sqlite"],
        },
        {
            "type": "action_status",
            "action": "respond",
            "status": "completed",
            "label": "Response complete",
        },
        {"type": "done", "reference_note_ids": ["note-sqlite"]},
    ]
    assert [action.kind for action in tools.executed_actions] == ["search_notes"]
    search_tool_events = [
        event
        for event in events
        if event["type"] == "action_status"
        and event["action"] == "search_notes"
        and not event["label"].startswith("Selected action")
    ]
    assert _without_activity_token_counts(search_tool_events) == [
        {
            "type": "action_status",
            "action": "search_notes",
            "status": "started",
            "label": 'Searching notes · page 1 · "storage"',
        },
        {
            "type": "action_status",
            "action": "search_notes",
            "status": "completed",
            "label": (
                "Search complete · 1 of 1 result tree · 1 of 1 matching note · "
                'page 1 of 1 · "storage"'
            ),
        },
    ]
    selected_action_events = [
        event
        for event in events
        if event["type"] == "action_status"
        and event["status"] == "completed"
        and event["label"].startswith("Selected action")
    ]
    assert _without_activity_token_counts(selected_action_events) == [
        {
            "type": "action_status",
            "action": "search_notes",
            "status": "completed",
            "label": (
                "Selected action · Search notes · "
                "Locate the user's storage decision."
            ),
        },
        {
            "type": "action_status",
            "action": "respond",
            "status": "completed",
            "label": (
                "Selected action · Respond to user · "
                "The complete matching note says to keep SQLite."
            ),
        },
    ]

    assert inference.structured_requests[0]["response_model"] is AgentRouteEnvelope
    assert inference.structured_requests[1]["response_model"] is SearchQueryEnvelope
    assert inference.structured_requests[2]["response_model"] is AgentRouteEnvelope
    search_query_context = inference.structured_requests[1]["messages"]
    assert isinstance(search_query_context, list)
    assert search_query_context[0]["role"] == "system"
    assert search_query_context[1]["role"] == "system"
    assert search_query_context[1]["content"].startswith(
        "ACTIVE_SKILL search_notes\n"
    )
    assert "foo OR bar baz" in search_query_context[1]["content"]
    second_route_context = inference.structured_requests[2]["messages"]
    assert isinstance(second_route_context, list)
    assert all(
        "ACTIVE_SKILL" not in message["content"] for message in second_route_context
    )
    assert any(
        message["role"] == "user" and "TOOL_RESULT search_notes" in message["content"]
        for message in second_route_context
    )
    final_context = inference.final_requests[0]["messages"]
    assert isinstance(final_context, list)
    assert any("Decision: keep SQLite" in message["content"] for message in final_context)

    snapshot = traces.snapshot(session_key="session-a")
    assert snapshot["enabled"] is True
    assert snapshot["has_trace"] is True
    run = snapshot["run"]
    assert run["status"] == "complete"
    event_types = [event["type"] for event in run["events"]]
    assert "OLLAMA_REQUEST" in event_types
    assert "MODEL_RESPONSE" in event_types
    assert "POLICY_DECISION" in event_types
    assert "TOOL_CALL" in event_types
    assert "TOOL_RESULT" in event_types
    assert "SKILL" in event_types
    assert "ACTION_ARGUMENTS" in event_types
    assert event_types[-1] == "FINAL_RESPONSE"
    wire_requests = [
        event for event in run["events"] if event["type"] == "OLLAMA_REQUEST"
    ]
    assert len(wire_requests) == 4
    assert wire_requests[0]["label"] == "Ollama wire request: action-selection"
    assert wire_requests[0]["detail"]["body"]["messages"][0]["role"] == "system"
    assert wire_requests[0]["detail"]["body"]["messages"][1] == {
        "role": "user",
        "content": "What did I decide about storage?",
    }
    assert wire_requests[1]["label"] == "Ollama wire request: search-query"
    assert wire_requests[-1]["label"] == "Ollama wire request: final-response"
    assert wire_requests[-1]["detail"]["body"]["messages"] == final_context
    assert "SYSTEM_PROMPT" not in event_types


def test_runtime_skips_a_semantically_duplicate_completed_search() -> None:
    inference = FakeInferenceAdapter(
        structured_contents=[
            json.dumps(
                {
                    "kind": "search_notes",
                    "note_ids": [],
                    "reason": "Search the user's notes for the topic.",
                }
            ),
            json.dumps(
                {
                    "search_query": 'foo OR "foo"',
                    "page": 1,
                    "reason": "Cover both the tag and note text.",
                }
            ),
            json.dumps(
                {
                    "kind": "search_notes",
                    "note_ids": [],
                    "reason": 'foo OR "foo"',
                }
            ),
            json.dumps(
                {
                    "search_query": '  "FOO"   OR   FOO  ',
                    "page": 1,
                    "reason": "Repeat the same search.",
                }
            ),
        ]
    )
    tools = FakeToolRegistry()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=tools,
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
    )

    events = _collect_runtime_events(runtime)
    _assert_positive_activity_token_counts(events)

    assert [action.kind for action in tools.executed_actions] == ["search_notes"]
    assert len(inference.structured_requests) == 3
    assert sum(
        event["type"] == "action_status"
        and event["label"] == "Activated skill · Search notes"
        for event in events
    ) == 1
    assert any(
        event["type"] == "action_status"
        and event["action"] == "search_notes"
        and event["label"].startswith("Skipped repeat-search selection")
        for event in events
    )
    assert not any(
        event["type"] == "action_status"
        and event["label"].startswith("Selected action · Search again")
        for event in events
    )
    assert events[-1] == {
        "type": "done",
        "reference_note_ids": ["note-sqlite"],
    }


def test_runtime_allows_a_revised_second_search() -> None:
    inference = FakeInferenceAdapter(
        structured_contents=[
            json.dumps(
                {
                    "kind": "search_notes",
                    "note_ids": [],
                    "reason": "Start with the user's requested tag.",
                }
            ),
            json.dumps(
                {
                    "search_query": "foo",
                    "page": 1,
                    "reason": "Search the tag first.",
                }
            ),
            json.dumps(
                {
                    "kind": "search_notes",
                    "note_ids": [],
                    "reason": "The first search may miss text-only mentions.",
                }
            ),
            json.dumps(
                {
                    "search_query": '"foo"',
                    "page": 1,
                    "reason": "Search exact note text for the missing evidence.",
                }
            ),
            json.dumps(
                {
                    "kind": "respond",
                    "note_ids": [],
                    "reason": "Both distinct searches are now complete.",
                }
            ),
        ]
    )
    tools = FakeToolRegistry()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=tools,
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
    )

    events = _collect_runtime_events(runtime)

    assert [
        action.query
        for action in tools.executed_actions
        if action.kind == "search_notes"
    ] == ["foo", '"foo"']
    assert any(
        event["type"] == "action_status"
        and event["label"] == (
            "Selected action · Search again · "
            "The first search may miss text-only mentions."
        )
        for event in events
    )


def test_runtime_skips_duplicate_query_after_a_distinct_repeat_search_reason() -> None:
    inference = FakeInferenceAdapter(
        structured_contents=[
            json.dumps(
                {
                    "kind": "search_notes",
                    "note_ids": [],
                    "reason": "Search the user's notes for the topic.",
                }
            ),
            json.dumps(
                {
                    "search_query": 'foo OR "foo"',
                    "page": 1,
                    "reason": "Cover both tag and text matches.",
                }
            ),
            json.dumps(
                {
                    "kind": "search_notes",
                    "note_ids": [],
                    "reason": "Look for a missing exact-text variation.",
                }
            ),
            json.dumps(
                {
                    "search_query": '"FOO" OR FOO',
                    "page": 1,
                    "reason": "This accidentally repeats the completed query.",
                }
            ),
        ]
    )
    tools = FakeToolRegistry()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=tools,
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
    )

    events = _collect_runtime_events(runtime)

    assert [action.kind for action in tools.executed_actions] == ["search_notes"]
    assert len(inference.structured_requests) == 4
    assert any(
        event["type"] == "action_status"
        and event["label"].startswith("Skipped duplicate search")
        for event in events
    )


def test_runtime_records_instructor_validation_retry_attempts() -> None:
    content = json.dumps(
        {
            "kind": "respond",
            "note_ids": [],
            "reason": "No retrieval is necessary for this greeting.",
        }
    )
    inference = FakeInferenceAdapter(structured_contents=[content])
    original_infer_structured = inference.infer_structured

    async def infer_with_retry_attempts(**kwargs):
        on_progress = kwargs.pop("on_progress")
        response = await original_infer_structured(
            **kwargs,
            on_progress=lambda progress: None,
        )
        progress_specs = [
            ("attempt_started", 1, "", ""),
            ("response_received", 1, "", ""),
            ("retrying", 1, "Structured output invalid", "ValidationError"),
            ("attempt_started", 2, "", ""),
            ("response_received", 2, "", ""),
            ("attempt_succeeded", 2, "", ""),
        ]
        for phase, attempt, failure_kind, error_type in progress_specs:
            error_message = ""
            if phase == "retrying":
                error_message = "missing required fields"
            on_progress(
                StructuredInferenceProgress(
                    phase=phase,
                    attempt=attempt,
                    max_attempts=2,
                    failure_kind=failure_kind,
                    error_type=error_type,
                    error_message=error_message,
                    duration_ms=1.0,
                    wire_request={
                        "method": "POST",
                        "url": "http://127.0.0.1:11434/v1/chat/completions",
                        "body": {
                            "model": kwargs["model"],
                            "messages": kwargs["messages"],
                            "attempt": attempt,
                        },
                    },
                    output_tokens_received=0,
                )
            )
        return InferenceResponse(
            content=response.content,
            thinking=response.thinking,
            usage=response.usage,
            attempts=[
                InferenceAttempt(
                    request={"messages": kwargs["messages"], "attempt": 1},
                    response={"message": {"content": "invalid"}},
                    error="ValidationError: missing required fields",
                    duration_ms=1.0,
                ),
                InferenceAttempt(
                    request={"messages": [*kwargs["messages"], {"role": "user", "content": "retry"}], "attempt": 2},
                    response={"message": {"content": content}},
                    error="",
                    duration_ms=2.0,
                ),
            ],
        )

    inference.infer_structured = infer_with_retry_attempts
    traces = AgentTraceStore()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=FakeToolRegistry(),
        trace_store=traces,
        provider_label="Ollama",
    )

    events = _collect_runtime_events(runtime)
    _assert_positive_activity_token_counts(events)

    assert len(inference.structured_requests) == 1
    assert events[-1] == {
        "type": "done",
        "reference_note_ids": [],
    }
    retry_events = [
        event
        for event in events
        if event["type"] == "action_status" and event["action"] == "retry"
    ]
    assert _without_activity_token_counts(retry_events) == [
        {
            "type": "action_status",
            "action": "retry",
            "status": "started",
            "label": "Structured output invalid (ValidationError) · Instructor will retry",
        }
    ]
    attempt_events = [
        event
        for event in events
        if event["type"] == "action_status"
        and event["action"] in {"model_request", "validation"}
    ]
    assert [event["label"] for event in attempt_events] == [
        "Ollama choosing next action",
        "Ollama returned next-action choice · validating",
        "Instructor retrying · Ollama choosing next action · attempt 2 of 2",
        "Ollama returned next-action choice · validating attempt 2 of 2",
        "Structured action validated · attempt 2 of 2",
    ]
    wire_requests = [
        event
        for event in traces.snapshot(session_key="session-a")["run"]["events"]
        if event["type"] == "OLLAMA_REQUEST"
    ]
    assert [event["detail"]["attempt"] for event in wire_requests] == [1, 2, 1]
    assert [event["label"] for event in wire_requests] == [
        "Ollama wire request: action-selection",
        "Ollama wire request: action-selection · attempt 2 of 2",
        "Ollama wire request: final-response",
    ]
    response_events = [
        event
        for event in traces.snapshot(session_key="session-a")["run"]["events"]
        if event["type"] == "MODEL_RESPONSE"
    ]
    assert response_events[0]["detail"]["validation"] == "invalid"
    assert response_events[1]["detail"]["validation"] == "valid"
    assert response_events[0]["detail"]["errors"] == [
        "ValidationError: missing required fields"
    ]
    status_events = [
        event
        for event in traces.snapshot(session_key="session-a")["run"]["events"]
        if event["type"] == "MODEL_STATUS"
    ]
    assert [event["detail"]["phase"] for event in status_events] == [
        "attempt_started",
        "response_received",
        "retrying",
        "attempt_started",
        "response_received",
        "attempt_succeeded",
    ]


def test_context_builder_does_not_carry_transient_tool_or_future_skill_events() -> None:
    builder = AgentContextBuilder()
    canonical_messages = [
        {"role": "user", "content": "First request"},
        {"role": "assistant", "content": "Durable final answer"},
        {"role": "user", "content": "Next request"},
    ]
    first_run_context = builder.build_initial_messages(
        canonical_messages=canonical_messages,
        prompts=DEFAULT_AGENT_PROMPTS,
    )
    transient_context = [
        *first_run_context,
        {"role": "user", "content": "TOOL_RESULT search_notes\n{}"},
        {"role": "user", "content": "SKILL_CONTENT future-research-skill"},
    ]

    next_run_context = builder.build_initial_messages(
        canonical_messages=canonical_messages,
        prompts=DEFAULT_AGENT_PROMPTS,
    )

    assert len(transient_context) == len(next_run_context) + 2
    assert next_run_context[1:] == canonical_messages
    assert "ACTION_SCHEMA" not in next_run_context[0]["content"]
    assert all(
        "TOOL_RESULT" not in message["content"] for message in next_run_context[1:]
    )
    assert all(
        "SKILL_CONTENT" not in message["content"] for message in next_run_context[1:]
    )


def test_context_builder_uses_packaged_prompt_resources() -> None:
    builder = AgentContextBuilder()
    initial_messages = builder.build_initial_messages(
        canonical_messages=[{"role": "user", "content": "Hello"}],
        prompts=DEFAULT_AGENT_PROMPTS,
    )

    assert initial_messages[0] == {
        "role": "system",
        "content": DEFAULT_AGENT_PROMPTS.system_prompt,
    }
    assert DEFAULT_AGENT_PROMPTS.render_tool_result(
        action_name="search_notes",
        payload_json='{"notes":[]}',
    ) == 'TOOL_RESULT search_notes\n{"notes":[]}'
    final_request = DEFAULT_AGENT_PROMPTS.render_final_response_request(
        basis="No retrieval was needed.",
    )
    assert final_request.startswith(
        "FINAL_RESPONSE_REQUEST\nStructured basis: No retrieval was needed.\n"
    )
    assert "citations are mandatory" in final_request
    assert "Every note-derived\nparagraph or list item" in final_request
    assert "[[UUID]]" in final_request
    assert "same evidence object" in final_request

    final_messages = builder.append_final_request(
        messages=initial_messages,
        action=RespondAction(
            kind="respond",
            basis="The latest message corrects the preceding answer.",
        ),
        prompts=DEFAULT_AGENT_PROMPTS,
        current_user_request="nitric oxide is not food",
    )
    final_payload = json.loads(final_messages[-1]["content"].split("\n", 1)[1])
    assert final_payload["current_user_request"] == "nitric oxide is not food"
    assert final_payload["reference_catalog"] == []
    assert final_payload["response_mode"] == "direct_without_note_evidence"
    assert "acknowledge the correction directly" in final_payload["instruction"]


def test_trace_store_always_keeps_latest_run_and_exact_details_default_on() -> None:
    traces = AgentTraceStore()

    assert traces.snapshot(session_key="session-a") == {
        "enabled": True,
        "has_trace": False,
        "run": {},
    }

    first_run_id = traces.start_run(
        session_key="session-a",
        model="qwen3:8b",
        user_message="first",
    )
    traces.append_event(
        session_key="session-a",
        run_id=first_run_id,
        event_type="TOOL_CALL",
        label="First tool",
        detail={"tool": "search_notes"},
        duration_ms=0.0,
    )
    second_run_id = traces.start_run(
        session_key="session-a",
        model="qwen3:8b",
        user_message="second",
    )

    snapshot = traces.snapshot(session_key="session-a")
    assert snapshot["run"]["run_id"] == second_run_id
    assert snapshot["run"]["run_id"] != first_run_id
    assert snapshot["run"]["events"] == []
    assert snapshot["enabled"] is True
    assert traces.snapshot(session_key="session-b")["enabled"] is True

    traces.set_exact_details_enabled(session_key="session-a", enabled=False)
    assert traces.snapshot(session_key="session-a")["enabled"] is False
    assert traces.snapshot(session_key="session-a")["run"]["run_id"] == second_run_id
    traces.set_exact_details_enabled(session_key="session-a", enabled=True)
    assert traces.snapshot(session_key="session-a")["enabled"] is True
    assert traces.snapshot(session_key="session-a")["run"]["run_id"] == second_run_id


def test_read_only_tools_apply_limits_and_include_note_metadata() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                "note-a": SimpleNamespace(
                    id="note-a",
                    parent_id=None,
                    content="<div>SQLite decision</div>",
                    tags="architecture",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "note-b": SimpleNamespace(
                    id="note-b",
                    parent_id="note-a",
                    content=f"<p>{'x' * 13_000}</p>",
                    tags="benchmark",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
            }

        def list_note_ids(self) -> list[str]:
            return ["note-a", "note-b"]

        def get_children(self, parent_id: str | None) -> list[str]:
            return _children_in_record_order(self.records, parent_id)

        def get_note(self, note_id: str):
            return self.records[note_id]

        def has_note(self, note_id: str) -> bool:
            return note_id in self.records

    class FakeSearches:
        def query_note_ids(self, query: str) -> set[str]:
            assert query == '"SQLite"'
            return {"note-a"}

    registry = ReadOnlyAgentToolRegistry(notes=FakeNotes(), searches=FakeSearches())
    search_action = agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": '"SQLite"',
            "page": 1,
            "rationale": "Find the decision.",
        }
    )
    read_action = agent_action_adapter.validate_python(
        {
            "kind": "read_notes_by_id",
            "note_ids": ["note-b", "missing-note"],
            "rationale": "Read the benchmark and report a missing id explicitly.",
        }
    )

    settings = AgentRetrievalSettings(
        max_note_characters=1_000,
        max_page_characters=20_000,
        max_notes_per_page=2,
    )
    search_result = registry.execute(search_action, settings=settings)
    read_result = registry.execute(read_action, settings=settings)

    assert registry.spec_for(search_action).mutates is False
    assert search_result.payload["query"] == '"SQLite"'
    assert search_result.payload["page"] == 1
    assert search_result.payload["page_size"] == 2
    assert search_result.payload["total_pages"] == 1
    assert search_result.payload["matched_count"] == 1
    assert search_result.payload["matched_note_count"] == 1
    assert search_result.payload["returned_count"] == 1
    assert search_result.payload["returned_note_count"] == 1
    assert search_result.payload["content_contract"] == {
        "notes_are_content_bearing": True,
        "note_content_field": "notes[].content_text",
        "follow_up_read_required": False,
        "instruction": (
            "Read and synthesize notes[].content_text now. note_id is only for "
            "citation and navigation, not a handle that requires another read."
        ),
    }
    search_notes = search_result.payload["notes"]
    assert isinstance(search_notes, list)
    assert search_notes == [
        {
            "note_id": "note-a",
            "parent_id": "",
            "root_note_id": "note-a",
            "content_text": "SQLite decision",
            "content_character_count": 15,
            "returned_character_count": 15,
            "content_is_truncated": False,
            "content_is_redacted": False,
            "tags": "architecture",
            "created_at": TEST_TIMESTAMP.isoformat(),
            "updated_at": TEST_TIMESTAMP.isoformat(),
        }
    ]
    read_notes = read_result.payload["notes"]
    assert isinstance(read_notes, list)
    assert len(read_notes[0]["content_text"]) == 1_000
    assert read_notes[0]["content_character_count"] == 13_000
    assert read_notes[0]["content_is_truncated"] is True
    assert read_notes[0]["created_at"] == TEST_TIMESTAMP.isoformat()
    assert read_notes[0]["updated_at"] == TEST_TIMESTAMP.isoformat()
    assert read_result.payload["missing_note_ids"] == ["missing-note"]


def test_read_only_search_groups_matching_parent_and_child_as_one_result() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                "root": SimpleNamespace(
                    id="root",
                    parent_id=None,
                    content="<h1>Incorporate AI</h1>",
                    tags="Pydantic AI",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "child": SimpleNamespace(
                    id="child",
                    parent_id="root",
                    content="<p>Instructor + LiteLLM vs. Pydantic AI</p>",
                    tags="Pydantic AI",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
            }

        def list_note_ids(self) -> list[str]:
            return ["root", "child"]

        def get_children(self, parent_id: str | None) -> list[str]:
            return _children_in_record_order(self.records, parent_id)

        def get_note(self, note_id: str):
            return self.records[note_id]

        def has_note(self, note_id: str) -> bool:
            return note_id in self.records

    class FakeSearches:
        def query_note_ids(self, query: str) -> set[str]:
            assert query == "Pydantic AI"
            return {"root", "child"}

    registry = ReadOnlyAgentToolRegistry(notes=FakeNotes(), searches=FakeSearches())
    action = agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": "Pydantic AI",
            "page": 1,
            "rationale": "Find the relevant result tree.",
        }
    )

    result = registry.execute(action, settings=DEFAULT_AGENT_RETRIEVAL_SETTINGS)

    assert result.payload["matched_count"] == 1
    assert result.payload["matched_note_count"] == 2
    assert result.payload["returned_count"] == 1
    assert result.payload["returned_note_count"] == 2
    notes = result.payload["notes"]
    assert isinstance(notes, list)
    assert [note["note_id"] for note in notes] == ["root", "child"]
    assert {note["root_note_id"] for note in notes} == {"root"}
    assert notes[1]["content_text"] == "Instructor + LiteLLM vs. Pydantic AI"


def test_read_only_search_pages_in_user_ranked_root_and_tree_order() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                "lower-root": SimpleNamespace(
                    id="lower-root",
                    parent_id=None,
                    content="<h1>Lower root</h1>",
                    tags="",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "lower-match": SimpleNamespace(
                    id="lower-match",
                    parent_id="lower-root",
                    content="<p>Lower matching note</p>",
                    tags="foo",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "top-root": SimpleNamespace(
                    id="top-root",
                    parent_id=None,
                    content="<h1>User-ranked top root</h1>",
                    tags="",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "top-match": SimpleNamespace(
                    id="top-match",
                    parent_id="top-root",
                    content="<p>Top matching note</p>",
                    tags="foo",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "top-match-two": SimpleNamespace(
                    id="top-match-two",
                    parent_id="top-root",
                    content="<p>Second top matching note</p>",
                    tags="foo",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
            }
            self.children = {
                None: ["top-root", "lower-root"],
                "top-root": ["top-match", "top-match-two"],
                "top-match": [],
                "top-match-two": [],
                "lower-root": ["lower-match"],
                "lower-match": [],
            }

        def list_note_ids(self) -> list[str]:
            return list(self.records)

        def get_children(self, parent_id: str | None) -> list[str]:
            return list(self.children[parent_id])

        def get_note(self, note_id: str):
            return self.records[note_id]

        def has_note(self, note_id: str) -> bool:
            return note_id in self.records

    class FakeSearches:
        def query_note_ids(self, query: str) -> set[str]:
            assert query == "foo"
            return {"lower-match", "top-match", "top-match-two"}

    registry = ReadOnlyAgentToolRegistry(notes=FakeNotes(), searches=FakeSearches())
    action = agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": "foo",
            "page": 1,
            "rationale": "Read the user's highest-ranked matching result first.",
        }
    )

    result = registry.execute(
        action,
        settings=AgentRetrievalSettings(
            max_note_characters=1_000,
            max_page_characters=20_000,
            max_notes_per_page=1,
        ),
    )

    notes = result.payload["notes"]
    assert isinstance(notes, list)
    assert [note["note_id"] for note in notes] == ["top-match", "top-match-two"]
    assert result.payload["returned_count"] == 1
    assert result.payload["returned_note_count"] == 2
    assert result.payload["total_pages"] == 2


def test_read_only_search_pages_large_result_sets() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                f"note-{index}": SimpleNamespace(
                    id=f"note-{index}",
                    parent_id=None,
                    content=f"<p>Complete note {index}</p>",
                    tags="foo",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                )
                for index in range(21)
            }

        def list_note_ids(self) -> list[str]:
            return list(self.records)

        def get_children(self, parent_id: str | None) -> list[str]:
            return _children_in_record_order(self.records, parent_id)

        def get_note(self, note_id: str):
            return self.records[note_id]

        def has_note(self, note_id: str) -> bool:
            return note_id in self.records

    class FakeSearches:
        def query_note_ids(self, query: str) -> set[str]:
            assert query == "foo"
            return {f"note-{index}" for index in range(21)}

    registry = ReadOnlyAgentToolRegistry(notes=FakeNotes(), searches=FakeSearches())
    action = agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": "foo",
            "page": 2,
            "rationale": "Find all notes tagged foo.",
        }
    )

    settings = AgentRetrievalSettings(
        max_note_characters=1_000,
        max_page_characters=20_000,
        max_notes_per_page=4,
    )
    result = registry.execute(action, settings=settings)

    assert result.payload["matched_count"] == 21
    assert result.payload["matched_note_count"] == 21
    assert result.payload["page"] == 2
    assert result.payload["page_size"] == 4
    assert result.payload["total_pages"] == 6
    assert result.payload["has_previous_page"] is True
    assert result.payload["previous_page"] == 1
    assert result.payload["has_next_page"] is True
    assert result.payload["next_page"] == 3
    notes = result.payload["notes"]
    assert isinstance(notes, list)
    assert [note["note_id"] for note in notes] == [
        "note-4",
        "note-5",
        "note-6",
        "note-7",
    ]


def test_read_only_search_caps_total_page_content_without_dropping_results() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                f"note-{index}": SimpleNamespace(
                    id=f"note-{index}",
                    parent_id=None,
                    content=f"<p>{'x' * 4_000}</p>",
                    tags="foo",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                )
                for index in range(3)
            }

        def list_note_ids(self) -> list[str]:
            return list(self.records)

        def get_children(self, parent_id: str | None) -> list[str]:
            return _children_in_record_order(self.records, parent_id)

        def get_note(self, note_id: str):
            return self.records[note_id]

        def has_note(self, note_id: str) -> bool:
            return note_id in self.records

    class FakeSearches:
        def query_note_ids(self, query: str) -> set[str]:
            assert query == "foo"
            return {"note-0", "note-1", "note-2"}

    registry = ReadOnlyAgentToolRegistry(notes=FakeNotes(), searches=FakeSearches())
    action = agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": "foo",
            "page": 1,
            "rationale": "Read the bounded result page.",
        }
    )

    result = registry.execute(
        action,
        settings=AgentRetrievalSettings(
            max_note_characters=4_000,
            max_page_characters=5_000,
            max_notes_per_page=50,
        ),
    )

    notes = result.payload["notes"]
    assert isinstance(notes, list)
    assert len(notes) == 3
    assert sum(len(note["content_text"]) for note in notes) == 5_000
    assert all(note["content_text"] != "" for note in notes)
    assert result.payload["returned_character_count"] == 5_000
    assert result.payload["max_page_characters"] == 5_000
    assert result.payload["has_truncated_content"] is True


def test_search_excludes_content_from_nonmatching_search_redacted_notes() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                "root": SimpleNamespace(
                    id="root",
                    parent_id=None,
                    content="<h1>Unmatched visible result root</h1>",
                    tags="",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "match": SimpleNamespace(
                    id="match",
                    parent_id="root",
                    content="<p>Relevant foo content</p>",
                    tags="foo",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
                "redacted-child": SimpleNamespace(
                    id="redacted-child",
                    parent_id="root",
                    content="<p>GRAY BAR CONTENT MUST NOT LEAVE METALIST</p>",
                    tags="bar",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                ),
            }

        def list_note_ids(self) -> list[str]:
            return ["root", "match", "redacted-child"]

        def get_children(self, parent_id: str | None) -> list[str]:
            return _children_in_record_order(self.records, parent_id)

        def get_note(self, note_id: str):
            return self.records[note_id]

        def has_note(self, note_id: str) -> bool:
            return note_id in self.records

    class FakeSearches:
        def query_note_ids(self, query: str) -> set[str]:
            assert query == "foo"
            return {"match"}

    registry = ReadOnlyAgentToolRegistry(notes=FakeNotes(), searches=FakeSearches())
    action = agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": "foo",
            "page": 1,
            "rationale": "Find matching foo notes.",
        }
    )

    result = registry.execute(action, settings=DEFAULT_AGENT_RETRIEVAL_SETTINGS)
    serialized_payload = json.dumps(result.payload)

    assert [note["note_id"] for note in result.payload["notes"]] == ["match"]
    assert "Relevant foo content" in serialized_payload
    assert "Unmatched visible result root" not in serialized_payload
    assert "GRAY BAR CONTENT MUST NOT LEAVE METALIST" not in serialized_payload


def test_agent_tools_redact_password_note_content() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                "password-note": SimpleNamespace(
                    id="password-note",
                    parent_id=None,
                    content="<p>correct horse battery staple</p>",
                    tags="@password credentials",
                    created_at=TEST_TIMESTAMP,
                    updated_at=TEST_TIMESTAMP,
                )
            }

        def list_note_ids(self) -> list[str]:
            return ["password-note"]

        def get_children(self, parent_id: str | None) -> list[str]:
            return _children_in_record_order(self.records, parent_id)

        def get_note(self, note_id: str):
            return self.records[note_id]

        def has_note(self, note_id: str) -> bool:
            return note_id in self.records

    class FakeSearches:
        def query_note_ids(self, query: str) -> set[str]:
            assert query == "credentials"
            return {"password-note"}

    registry = ReadOnlyAgentToolRegistry(notes=FakeNotes(), searches=FakeSearches())
    search_action = agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": "credentials",
            "page": 1,
            "rationale": "Find the credential note without exposing its value.",
        }
    )
    read_action = agent_action_adapter.validate_python(
        {
            "kind": "read_notes_by_id",
            "note_ids": ["password-note"],
            "rationale": "Read the known credential note safely.",
        }
    )

    search_result = registry.execute(
        search_action,
        settings=DEFAULT_AGENT_RETRIEVAL_SETTINGS,
    )
    read_result = registry.execute(
        read_action,
        settings=DEFAULT_AGENT_RETRIEVAL_SETTINGS,
    )

    for result in (search_result, read_result):
        serialized_payload = json.dumps(result.payload)
        assert "correct horse battery staple" not in serialized_payload
        assert result.payload["notes"][0]["content_text"] == "[REDACTED: @password]"
        assert result.payload["notes"][0]["content_is_redacted"] is True


def test_final_response_output_limit_is_provider_specific() -> None:
    assert _final_response_max_output_tokens(provider_label="Ollama") == 1_024
    assert _final_response_max_output_tokens(provider_label="OpenAI") == 8_192
    with pytest.raises(ValueError, match="Unsupported inference provider"):
        _final_response_max_output_tokens(provider_label="Unknown")
