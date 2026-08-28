import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.agent.actions import agent_action_adapter
from app.services.agent.actions import agent_action_response_schema
from app.services.agent.actions import parse_agent_action_json
from app.services.agent.context import AgentContextBuilder
from app.services.agent.inference import InferenceAttempt
from app.services.agent.inference import InferenceResponse
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.inference import StructuredInferenceError
from app.services.agent.model_policy import SingleModelPolicy
from app.services.agent.permissions import AgentPermissionPolicy
from app.services.agent.runtime import AgentRuntime
from app.services.agent.tools import ToolExecutionResult
from app.services.agent.tools import ToolPermission
from app.services.agent.tools import ReadOnlyAgentToolRegistry
from app.services.agent.tools import ToolSpec
from app.services.agent.trace import AgentTraceStore


class FakeInferenceAdapter:
    def __init__(self, *, structured_contents: list[str]) -> None:
        self._structured_contents = list(structured_contents)
        self.structured_requests: list[dict[str, object]] = []
        self.final_requests: list[dict[str, object]] = []

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
        on_request,
    ):
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

    def execute(self, action) -> ToolExecutionResult:
        self.executed_actions.append(action)
        if action.kind == "search_notes":
            return ToolExecutionResult(
                action_name="search_notes",
                status_label="Searching notes",
                payload={
                    "query": action.query,
                    "matched_count": 1,
                    "returned_count": 1,
                    "notes": [
                        {
                            "note_id": "note-sqlite",
                            "content_preview": "Decision: keep SQLite.",
                            "tags": "architecture",
                        }
                    ],
                },
            )
        if action.kind == "read_notes":
            return ToolExecutionResult(
                action_name="read_notes",
                status_label="Reading 1 note",
                payload={
                    "notes": [
                        {
                            "note_id": "note-sqlite",
                            "content_text": "Decision: keep SQLite for local-first storage.",
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
            )
        ]

    return asyncio.run(collect())


def test_agent_action_schema_exposes_only_read_only_actions_and_respond() -> None:
    assert agent_action_adapter.validate_python(
        {
            "kind": "search_notes",
            "query": '"SQLite"',
            "rationale": "Find the relevant decision note.",
        }
    ).kind == "search_notes"
    assert agent_action_adapter.validate_python(
        {
            "kind": "read_notes",
            "note_ids": ["note-sqlite"],
            "rationale": "Read the matching note.",
        }
    ).kind == "read_notes"
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
                "rationale": "This invalid model output must be retried.",
            }
        )


def test_ollama_action_response_schema_is_a_flat_required_object() -> None:
    schema = agent_action_response_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "kind",
        "search_query",
        "note_ids",
        "reason",
    }
    assert set(schema["properties"]["kind"]["enum"]) == {
        "search_notes",
        "read_notes",
        "respond",
    }
    assert "$defs" not in schema
    assert "oneOf" not in schema
    assert "discriminator" not in schema

    action = parse_agent_action_json(
        json.dumps(
            {
                "kind": "respond",
                "search_query": "",
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


def test_ollama_action_ignores_required_placeholder_fields_for_inactive_action() -> None:
    action = parse_agent_action_json(
        json.dumps(
            {
                "kind": "read_notes",
                "search_query": "Pydantic AI",
                "note_ids": ["note-pydantic", "note-instructor"],
                "reason": "Read the relevant search results.",
            }
        )
    )

    assert action.model_dump() == {
        "kind": "read_notes",
        "note_ids": ["note-pydantic", "note-instructor"],
        "rationale": "Read the relevant search results.",
    }

    search_action = parse_agent_action_json(
        json.dumps(
            {
                "kind": "search_notes",
                "search_query": "Pydantic AI",
                "note_ids": ["inactive-note-id"],
                "reason": "Find relevant notes.",
            }
        )
    )
    assert search_action.model_dump() == {
        "kind": "search_notes",
        "query": "Pydantic AI",
        "rationale": "Find relevant notes.",
    }

    respond_action = parse_agent_action_json(
        json.dumps(
            {
                "kind": "respond",
                "search_query": "inactive query",
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
        "Ollama could not produce a valid agent action after 2 attempts. "
        "Open Agent Debug for exact request and response details."
    )
    assert error.attempts == attempts


def test_runtime_executes_read_only_loop_streams_status_and_traces_exact_context() -> None:
    inference = FakeInferenceAdapter(
        structured_contents=[
            json.dumps(
                {
                    "kind": "search_notes",
                    "search_query": '"storage"',
                    "note_ids": [],
                    "reason": "Locate the user's storage decision.",
                }
            ),
            json.dumps(
                {
                    "kind": "read_notes",
                    "search_query": "",
                    "note_ids": ["note-sqlite"],
                    "reason": "Read the matching note before answering.",
                }
            ),
            json.dumps(
                {
                    "kind": "respond",
                    "search_query": "",
                    "note_ids": [],
                    "reason": "The retrieved note says to keep SQLite.",
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
    )

    events = _collect_runtime_events(runtime)

    started_labels = [
        event["label"]
        for event in events
        if event["type"] == "action_status" and event["status"] == "started"
    ]
    assert started_labels == [
        "Preparing action selection",
        "Waiting for Ollama · attempt 1 of 2",
        "Ollama responded · validating attempt 1 of 2",
        "Searching notes",
        "Preparing action selection",
        "Waiting for Ollama · attempt 1 of 2",
        "Ollama responded · validating attempt 1 of 2",
        "Reading 1 note",
        "Preparing action selection",
        "Waiting for Ollama · attempt 1 of 2",
        "Ollama responded · validating attempt 1 of 2",
        "Writing response",
    ]
    assert events[-4:] == [
        {"type": "thinking_delta", "text": "Final reasoning"},
        {"type": "content_delta", "text": "The answer uses your SQLite note."},
        {
            "type": "action_status",
            "action": "respond",
            "status": "completed",
            "label": "Response complete",
        },
        {"type": "done"},
    ]
    assert [action.kind for action in tools.executed_actions] == [
        "search_notes",
        "read_notes",
    ]
    selected_action_events = [
        event
        for event in events
        if event["type"] == "action_status"
        and event["status"] == "completed"
        and event["label"].startswith("Selected action")
    ]
    assert selected_action_events == [
        {
            "type": "action_status",
            "action": "search_notes",
            "status": "completed",
            "label": 'Selected action · Search notes · "storage"',
        },
        {
            "type": "action_status",
            "action": "read_notes",
            "status": "completed",
            "label": "Selected action · Read 1 note",
        },
        {
            "type": "action_status",
            "action": "respond",
            "status": "completed",
            "label": "Selected action · Respond to user",
        },
    ]

    second_model_context = inference.structured_requests[1]["messages"]
    assert isinstance(second_model_context, list)
    assert second_model_context[0]["role"] == "system"
    assert "Skills may be appended" in second_model_context[0]["content"]
    assert any(
        message["role"] == "user" and "TOOL_RESULT search_notes" in message["content"]
        for message in second_model_context
    )
    final_context = inference.final_requests[0]["messages"]
    assert isinstance(final_context, list)
    assert any("Decision: keep SQLite" in message["content"] for message in final_context)

    snapshot = traces.snapshot(session_key="session-a")
    assert snapshot["enabled"] is False
    assert snapshot["has_trace"] is True
    run = snapshot["run"]
    assert run["status"] == "complete"
    event_types = [event["type"] for event in run["events"]]
    assert "OLLAMA_REQUEST" in event_types
    assert "MODEL_RESPONSE" in event_types
    assert "POLICY_DECISION" in event_types
    assert "TOOL_CALL" in event_types
    assert "TOOL_RESULT" in event_types
    assert event_types[-1] == "FINAL_RESPONSE"
    wire_requests = [
        event for event in run["events"] if event["type"] == "OLLAMA_REQUEST"
    ]
    assert len(wire_requests) == 4
    assert wire_requests[0]["label"] == (
        "Ollama wire request: action-selection · attempt 1 of 2"
    )
    assert wire_requests[0]["detail"]["body"]["messages"][0]["role"] == "system"
    assert wire_requests[0]["detail"]["body"]["messages"][1] == {
        "role": "user",
        "content": "What did I decide about storage?",
    }
    assert wire_requests[-1]["label"] == (
        "Ollama wire request: final-response · attempt 1 of 1"
    )
    assert wire_requests[-1]["detail"]["body"]["messages"] == final_context
    assert "SYSTEM_PROMPT" not in event_types


def test_runtime_records_instructor_validation_retry_attempts() -> None:
    content = json.dumps(
        {
            "kind": "respond",
            "search_query": "",
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
    )

    events = _collect_runtime_events(runtime)

    assert len(inference.structured_requests) == 1
    assert events[-1] == {"type": "done"}
    retry_events = [
        event
        for event in events
        if event["type"] == "action_status" and event["action"] == "retry"
    ]
    assert retry_events == [
        {
            "type": "action_status",
            "action": "retry",
            "status": "started",
            "label": "Structured output invalid (ValidationError) · Instructor will retry",
        }
    ]
    wire_requests = [
        event
        for event in traces.snapshot(session_key="session-a")["run"]["events"]
        if event["type"] == "OLLAMA_REQUEST"
    ]
    assert [event["detail"]["attempt"] for event in wire_requests] == [1, 2, 1]
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
    )
    transient_context = [
        *first_run_context,
        {"role": "user", "content": "TOOL_RESULT search_notes\n{}"},
        {"role": "user", "content": "SKILL_CONTENT future-research-skill"},
    ]

    next_run_context = builder.build_initial_messages(
        canonical_messages=canonical_messages,
    )

    assert len(transient_context) == len(next_run_context) + 2
    assert next_run_context[1:] == canonical_messages
    assert "ACTION_SCHEMA" not in next_run_context[0]["content"]
    assert all("TOOL_RESULT" not in message["content"] for message in next_run_context)
    assert all("SKILL_CONTENT" not in message["content"] for message in next_run_context)


def test_trace_store_always_keeps_latest_run_and_exact_details_default_off() -> None:
    traces = AgentTraceStore()

    assert traces.snapshot(session_key="session-a") == {
        "enabled": False,
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
    assert snapshot["enabled"] is False
    assert traces.snapshot(session_key="session-b")["enabled"] is False

    traces.set_exact_details_enabled(session_key="session-a", enabled=True)
    assert traces.snapshot(session_key="session-a")["enabled"] is True
    assert traces.snapshot(session_key="session-a")["run"]["run_id"] == second_run_id
    traces.set_exact_details_enabled(session_key="session-a", enabled=False)
    assert traces.snapshot(session_key="session-a")["enabled"] is False
    assert traces.snapshot(session_key="session-a")["run"]["run_id"] == second_run_id


def test_read_only_tools_search_memory_and_bound_returned_note_content() -> None:
    class FakeNotes:
        def __init__(self) -> None:
            self.records = {
                "note-a": SimpleNamespace(
                    id="note-a",
                    parent_id=None,
                    content="<div>SQLite decision</div>",
                    tags="architecture",
                ),
                "note-b": SimpleNamespace(
                    id="note-b",
                    parent_id="note-a",
                    content=f"<p>{'x' * 13_000}</p>",
                    tags="benchmark",
                ),
            }

        def list_note_ids(self) -> list[str]:
            return ["note-a", "note-b"]

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
            "rationale": "Find the decision.",
        }
    )
    read_action = agent_action_adapter.validate_python(
        {
            "kind": "read_notes",
            "note_ids": ["note-b", "missing-note"],
            "rationale": "Read the benchmark and report a missing id explicitly.",
        }
    )

    search_result = registry.execute(search_action)
    read_result = registry.execute(read_action)

    assert registry.spec_for(search_action).mutates is False
    assert search_result.payload["notes"] == [
        {
            "note_id": "note-a",
            "parent_id": "",
            "content_preview": "SQLite decision",
            "tags": "architecture",
        }
    ]
    read_notes = read_result.payload["notes"]
    assert isinstance(read_notes, list)
    assert len(read_notes[0]["content_text"]) == 12_000
    assert read_notes[0]["content_is_truncated"] is True
    assert read_result.payload["missing_note_ids"] == ["missing-note"]
