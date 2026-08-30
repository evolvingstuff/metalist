from __future__ import annotations

import asyncio
import json
from types import MappingProxyType

import pytest

import app.services.agent.runtime as runtime_module
from app.services.agent.context import AgentContextBuilder
from app.services.agent.inference import InferenceAttempt
from app.services.agent.inference import InferenceContextWindow
from app.services.agent.inference import InferenceResponse
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.investigation import InvestigationState
from app.services.agent.model_policy import SingleModelPolicy
from app.services.agent.permissions import AgentPermissionPolicy
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.retrieval_settings import DEFAULT_AGENT_RETRIEVAL_SETTINGS
from app.services.agent.runtime import AgentRuntime
from app.services.agent.scope import AgentScopeDescriptor
from app.services.agent.scope import FrozenScopedNote
from app.services.agent.scope import FrozenScopedTreeNode
from app.services.agent.scope import ScopedSearchSnapshot
from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.trace import AgentTraceStore
from app.services.agent.token_estimation import estimate_input_tokens
from app.services.agent.token_estimation import estimate_message_tokens
from app.services.ollama_provider import OllamaProviderError
from app.services.tag_ontology import TagOntology


def _descriptor() -> AgentScopeDescriptor:
    return AgentScopeDescriptor(
        scope_kind="all_notes",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="All notes",
    )


def _frozen_note(note_id: str, content: str, index: int) -> FrozenScopedNote:
    return FrozenScopedNote(
        note_id=note_id,
        parent_id="",
        root_note_id=note_id,
        content_text=content,
        explicit_tags_text="foo",
        explicit_tag_terms=("foo",),
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:00+00:00",
        order_index=index,
    )


def _root_tree_nodes(*note_ids: str) -> MappingProxyType:
    return MappingProxyType(
        {
            note_id: FrozenScopedTreeNode(
                note_id=note_id,
                parent_id="",
                root_note_id=note_id,
                child_ids=(),
            )
            for note_id in note_ids
        }
    )


class _FakeScopeFactory:
    def freeze(self, **arguments) -> ScopedSearchSnapshot:
        assert arguments["descriptor"] == _descriptor()
        assert arguments["authoritative_search_query"] == ""
        notes = {
            "note-a": _frozen_note("note-a", "RAW_ALPHA_UNIQUE", 0),
            "note-b": _frozen_note("note-b", "RAW_BETA_UNIQUE", 1),
        }
        return ScopedSearchSnapshot(
            run_id=arguments["run_id"],
            session_key=arguments["session_key"],
            descriptor=arguments["descriptor"],
            created_at="2026-08-29T00:00:00+00:00",
            ordered_root_ids=("note-a", "note-b"),
            ordered_note_ids=("note-a", "note-b"),
            notes_by_id=MappingProxyType(notes),
            tree_nodes_by_id=_root_tree_nodes("note-a", "note-b"),
        )


class _FakeInference:
    def __init__(self) -> None:
        self.structured_requests: list[list[dict[str, str]]] = []
        self.final_messages: list[dict[str, str]] = []
        self.outputs = [
            json.dumps(
                {
                    "kind": "investigate_current_scope",
                    "reason": "The request depends on saved-note evidence.",
                }
            ),
            json.dumps(
                {
                    "working_summary": {
                        "ranked_notes": [
                            {"note_id": "note-a", "importance": 88}
                        ]
                    },
                    "action_kind": "page_next",
                    "tag_expression": "",
                    "exact_text": "",
                    "facet_page": 0,
                    "backtrack_state_id": "",
                    "source_ids": [],
                    "reason": "The scope has another ordered page.",
                    "evidence_sufficiency": "insufficient",
                }
            ),
            json.dumps(
                {
                    "working_summary": {
                        "ranked_notes": [
                            {"note_id": "note-b", "importance": 92}
                        ]
                    },
                    "action_kind": "answer",
                    "tag_expression": "",
                    "exact_text": "",
                    "facet_page": 0,
                    "backtrack_state_id": "",
                    "source_ids": [],
                    "reason": "Both ordered pages now provide sufficient evidence.",
                    "evidence_sufficiency": "sufficient",
                }
            ),
        ]

    async def inspect_context_window(self, *, base_url: str, model: str):
        del base_url
        return InferenceContextWindow(
            model=model,
            maximum_tokens=32_768,
            loaded_tokens=32_768,
            required_tokens=32_768,
        )

    async def infer_structured(
        self,
        *,
        base_url,
        model,
        thinking_level,
        messages,
        response_model,
        on_progress,
    ):
        del thinking_level
        content = self.outputs.pop(0)
        response_model.model_validate_json(content)
        self.structured_requests.append(messages)
        wire_request = {
            "method": "POST",
            "url": f"{base_url}/v1/chat/completions",
            "body": {"model": model, "messages": messages},
        }
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
                    wire_request=wire_request,
                    output_tokens_received=0,
                )
            )
        return InferenceResponse(
            content=content,
            thinking="",
            usage={},
            attempts=[
                InferenceAttempt(
                    request=wire_request,
                    response={"content": content},
                    error="",
                    duration_ms=1.0,
                )
            ],
        )

    async def stream_text(
        self,
        *,
        base_url,
        model,
        thinking_level,
        messages,
        max_output_tokens,
        on_request,
    ):
        del thinking_level
        assert max_output_tokens == 1_024
        self.final_messages = messages
        on_request(
            {
                "method": "POST",
                "url": f"{base_url}/api/chat",
                "body": {"model": model, "messages": messages},
            }
        )
        yield {
            "type": "content_delta",
            "text": "Alpha and beta. [[note-a]] [[note-b]]",
        }
        yield {"type": "done"}


class _UnusedTools:
    pass


class _RetryFinalInference(_FakeInference):
    def __init__(self) -> None:
        super().__init__()
        self.outputs = [
            json.dumps(
                {
                    "kind": "respond",
                    "reason": "The request does not require saved-note evidence.",
                }
            )
        ]
        self.final_attempt_count = 0

    async def stream_text(self, **arguments):
        self.final_attempt_count += 1
        if self.final_attempt_count == 1:
            raise OllamaProviderError(
                "Ollama chat request failed with HTTP 400: transient rejection"
            )
        async for event in super().stream_text(**arguments):
            yield event


class _PartialFailureFinalInference(_RetryFinalInference):
    async def stream_text(self, **arguments):
        del arguments
        self.final_attempt_count += 1
        yield {"type": "content_delta", "text": "Partial"}
        raise OllamaProviderError("Ollama stream failed after output")


class _NarrowingInference(_FakeInference):
    def __init__(self) -> None:
        super().__init__()
        self.outputs = [
            json.dumps(
                {
                    "kind": "investigate_current_scope",
                    "reason": "The request depends on saved-note evidence.",
                }
            ),
            json.dumps(
                {"ordered_tags": ["keep", "discard-b", "discard-c"]}
            ),
        ]

    async def stream_text(self, **arguments):
        self.final_messages = arguments["messages"]
        arguments["on_request"](
            {
                "method": "POST",
                "url": f'{arguments["base_url"]}/api/chat',
                "body": {
                    "model": arguments["model"],
                    "messages": arguments["messages"],
                },
            }
        )
        yield {"type": "content_delta", "text": "Kept evidence. [[note-a]]"}
        yield {"type": "done"}


def _tagged_frozen_note(
    *,
    note_id: str,
    content: str,
    tag: str,
    index: int,
) -> FrozenScopedNote:
    return FrozenScopedNote(
        note_id=note_id,
        parent_id="",
        root_note_id=note_id,
        content_text=content,
        explicit_tags_text=tag,
        explicit_tag_terms=(tag,),
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:00+00:00",
        order_index=index,
    )


def test_oversized_scope_is_narrowed_by_cumulative_tags_before_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_SCOPED_EVIDENCE_OVERFLOW_MODE",
        runtime_module._LEGACY_MULTIPAGE_OVERFLOW_MODE,
    )
    inference = _NarrowingInference()
    notes = {
        "note-a": _tagged_frozen_note(
            note_id="note-a",
            content="KEEP_UNIQUE " + ("alpha " * 300),
            tag="keep",
            index=0,
        ),
        "note-b": _tagged_frozen_note(
            note_id="note-b",
            content="DROP_B_UNIQUE " + ("beta " * 300),
            tag="discard-b",
            index=1,
        ),
        "note-c": _tagged_frozen_note(
            note_id="note-c",
            content="DROP_C_UNIQUE " + ("gamma " * 300),
            tag="discard-c",
            index=2,
        ),
        "note-d": _tagged_frozen_note(
            note_id="note-d",
            content="DROP_D_UNIQUE " + ("delta " * 300),
            tag="discard-d",
            index=3,
        ),
    }
    frozen_scope = ScopedSearchSnapshot(
        run_id="scope-capture",
        session_key="session-1",
        descriptor=_descriptor(),
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=tuple(notes),
        ordered_note_ids=tuple(notes),
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=_root_tree_nodes(*notes),
    )
    traces = AgentTraceStore()
    case_variant_ontology = TagOntology(
        implication_out_edges={},
        implication_closure={},
        implied_by_closure={},
        scc_members_by_tag={
            "KEEP": frozenset({"KEEP", "retain"}),
            "keep": frozenset({"keep", "preserve"}),
        },
        matcher_rules=(),
    )
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=traces,
        provider_label="Ollama",
        ontology_provider=lambda: case_variant_ontology,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=2_000,
        max_page_characters=20_000,
        max_notes_per_page=50,
        max_page_approximate_tokens=5_000,
        max_ranked_tags_per_page=50,
        max_working_summary_characters=8_000,
        ideal_narrowed_scope_approximate_tokens=1_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen2.5:7b-instruct",
                thinking_level="off",
                canonical_messages=[
                    {"role": "user", "content": "Summarize my saved notes."}
                ],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    events = asyncio.run(collect())

    final_context = json.dumps(inference.final_messages)
    assert "KEEP_UNIQUE" in final_context
    assert "DROP_B_UNIQUE" not in final_context
    assert "DROP_C_UNIQUE" not in final_context
    assert "DROP_D_UNIQUE" not in final_context
    assert any(
        event["type"] == "action_status"
        and event["action"] == "context_narrowing"
        and event["status"] == "started"
        and event["label"].startswith("Automatic narrowing required")
        for event in events
    )
    completed_activities = [
        event
        for event in events
        if event["type"] == "action_status"
        and event["status"] == "completed"
    ]
    assert any(
        event["action"] == "context_narrowing_plan"
        and event["label"]
        == "AI proposed cumulative tags · keep → discard-b → discard-c"
        for event in completed_activities
    )
    assert any(
        event["action"] == "context_narrowing_test"
        and "Tested cumulative prefix 1 of 3 · keep" in event["label"]
        for event in completed_activities
    )
    assert any(
        event["action"] == "context_narrowing_test"
        and "Rejected zero-result prefix 2 of 3 · keep discard-b"
        in event["label"]
        for event in completed_activities
    )
    assert any(
        event["action"] == "context_narrowing"
        and "Narrowed scope · keep" in event["label"]
        for event in completed_activities
    )
    trace = traces.snapshot(session_key="session-1")
    trace_events = trace["run"]["events"]
    narrowing_event = next(
        event for event in trace_events if event["type"] == "CONTEXT_NARROWING"
    )
    assert narrowing_event["detail"]["selected_tags"] == ["keep"]
    assert narrowing_event["detail"]["did_narrow"] is True


def test_required_user_scope_tag_is_not_reapplied_as_narrowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_SCOPED_EVIDENCE_OVERFLOW_MODE",
        runtime_module._LEGACY_MULTIPAGE_OVERFLOW_MODE,
    )
    inference = _FakeInference()
    inference.outputs = [
        json.dumps(
            {
                "kind": "investigate_current_scope",
                "reason": "The request depends on saved-note evidence.",
            }
        )
    ]
    descriptor = AgentScopeDescriptor(
        scope_kind="search",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="ML3 -journal",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="ML3 -journal",
    )
    notes = {
        f"note-{index}": _tagged_frozen_note(
            note_id=f"note-{index}",
            content=f"REQUIRED_SCOPE_{index} " + ("evidence " * 300),
            tag="ML3",
            index=index,
        )
        for index in range(4)
    }
    frozen_scope = ScopedSearchSnapshot(
        run_id="scope-capture",
        session_key="session-1",
        descriptor=descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=tuple(notes),
        ordered_note_ids=tuple(notes),
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=_root_tree_nodes(*notes),
    )
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
        ontology_provider=TagOntology.empty,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=2_000,
        max_page_characters=20_000,
        max_notes_per_page=50,
        max_page_approximate_tokens=5_000,
        max_ranked_tags_per_page=50,
        max_working_summary_characters=8_000,
        ideal_narrowed_scope_approximate_tokens=1_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen2.5:7b-instruct",
                thinking_level="off",
                canonical_messages=[
                    {"role": "user", "content": "Summarize my saved notes."}
                ],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    events = asyncio.run(collect())

    assert len(inference.structured_requests) == 1
    final_context = json.dumps(inference.final_messages)
    for index in range(4):
        assert f"REQUIRED_SCOPE_{index}" in final_context
    assert not any(
        event["type"] == "action_status"
        and event["action"] in {
            "context_narrowing_plan",
            "context_narrowing_test",
        }
        for event in events
    )
    assert any(
        event["type"] == "action_status"
        and event["action"] == "context_narrowing"
        and "No additional tag constraints available" in event["label"]
        for event in events
    )


def test_scoped_runtime_replaces_old_raw_pages_and_rehydrates_final_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime_module,
        "_SCOPED_EVIDENCE_OVERFLOW_MODE",
        runtime_module._LEGACY_MULTIPAGE_OVERFLOW_MODE,
    )
    inference = _FakeInference()
    scope_factory = _FakeScopeFactory()
    frozen_scope = scope_factory.freeze(
        descriptor=_descriptor(),
        authoritative_search_query="",
        authoritative_sort_mode="normal",
        authoritative_date_filter={},
        run_id="scope-capture",
        session_key="session-1",
    )
    frozen_scope = ScopedSearchSnapshot(
        run_id=frozen_scope.run_id,
        session_key=frozen_scope.session_key,
        descriptor=frozen_scope.descriptor,
        created_at=frozen_scope.created_at,
        ordered_root_ids=frozen_scope.ordered_root_ids,
        ordered_note_ids=frozen_scope.ordered_note_ids,
        notes_by_id=MappingProxyType(
            {
                "note-a": _frozen_note(
                    "note-a", "RAW_ALPHA_UNIQUE " + ("! " * 300), 0
                ),
                "note-b": _frozen_note(
                    "note-b", "RAW_BETA_UNIQUE " + ("? " * 300), 1
                ),
            }
        ),
        tree_nodes_by_id=frozen_scope.tree_nodes_by_id,
    )
    traces = AgentTraceStore()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=traces,
        provider_label="Ollama",
        ontology_provider=TagOntology.empty,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=1,
        max_page_approximate_tokens=500,
        max_ranked_tags_per_page=10,
        max_working_summary_characters=8_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen3:8b",
                thinking_level="off",
                canonical_messages=[
                    {"role": "user", "content": "Synthesize my visible notes"}
                ],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    events = asyncio.run(collect())

    first_step = json.dumps(inference.structured_requests[1])
    second_step = json.dumps(inference.structured_requests[2])
    final_request = json.dumps(inference.final_messages)
    first_runtime_message = inference.structured_requests[1][-1]["content"]
    first_runtime_payload = json.loads(first_runtime_message.split("\n", 1)[1])
    assert "result_trees" in first_runtime_payload["note_page"]
    assert "notes" not in first_runtime_payload["note_page"]
    assert first_runtime_payload["note_page"]["result_trees"][0]["note_id"] == "note-a"
    assert "children" not in first_runtime_payload["note_page"]["result_trees"][0]
    assert "RAW_ALPHA_UNIQUE" in first_step
    assert "RAW_ALPHA_UNIQUE" not in second_step
    assert "RAW_BETA_UNIQUE" in second_step
    assert '"importance":88' not in second_step
    assert '"ranked_notes"' not in second_step
    assert "RAW_ALPHA_UNIQUE" in final_request
    assert "RAW_BETA_UNIQUE" in final_request
    assert events[-1] == {
        "type": "done",
        "reference_note_ids": ["note-b", "note-a"],
    }
    trace_events = traces.snapshot(session_key="session-1")["run"]["events"]
    evidence_events = [
        event for event in trace_events if event["type"] == "EVIDENCE_PAYLOAD"
    ]
    assert len(evidence_events) == 2
    assert evidence_events[0]["detail"]["note_page"]["result_trees"][0][
        "content_text"
    ].startswith("RAW_ALPHA_UNIQUE")
    assert evidence_events[1]["detail"]["note_page"]["result_trees"][0][
        "content_text"
    ].startswith("RAW_BETA_UNIQUE")


def test_scoped_runtime_retains_only_leading_root_trees_that_fit_one_page() -> None:
    inference = _NarrowingInference()
    note_ids = ("note-a", "note-b", "note-c", "note-d")
    frozen_scope = ScopedSearchSnapshot(
        run_id="scope-capture",
        session_key="session-1",
        descriptor=_descriptor(),
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=note_ids,
        ordered_note_ids=note_ids,
        notes_by_id=MappingProxyType(
            {
                note_id: _frozen_note(
                    note_id,
                    f"UNIQUE_{note_id.upper()} " + ("x" * 500),
                    index,
                )
                for index, note_id in enumerate(note_ids)
            }
        ),
        tree_nodes_by_id=_root_tree_nodes(*note_ids),
    )
    traces = AgentTraceStore()
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=traces,
        provider_label="Ollama",
        ontology_provider=TagOntology.empty,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=1,
        max_page_approximate_tokens=500,
        max_ranked_tags_per_page=10,
        max_working_summary_characters=8_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen3:8b",
                thinking_level="off",
                canonical_messages=[
                    {"role": "user", "content": "Synthesize my visible notes"}
                ],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    events = asyncio.run(collect())

    final_request = json.dumps(inference.final_messages)
    final_payload = json.loads(inference.final_messages[-1]["content"].split("\n", 1)[1])
    coverage = final_payload["evidence_coverage"]
    included_root_count = coverage["included_result_tree_count"]
    assert 1 < included_root_count < len(note_ids)
    assert coverage["omitted_result_tree_count"] == len(note_ids) - included_root_count
    assert coverage["included_note_count"] == included_root_count
    assert coverage["omitted_note_count"] == len(note_ids) - included_root_count
    for note_id in note_ids[:included_root_count]:
        assert f"UNIQUE_{note_id.upper()}" in final_request
    for note_id in note_ids[included_root_count:]:
        assert f"UNIQUE_{note_id.upper()}" not in final_request
    assert "leading root-tree prefix retained" in final_request
    assert "do not claim exhaustive scope coverage" in final_request
    assert f"includes {included_root_count} notes" in (
        final_payload["instruction_for_evidence"]
    )
    assert f"omits {len(note_ids) - included_root_count} notes" in (
        final_payload["instruction_for_evidence"]
    )
    assert len(inference.structured_requests) == 1
    assert any(
        event["type"] == "action_status"
        and event["action"] == "evidence_root_prefix"
        and "Retained token-bounded root prefix" in event["label"]
        and f"{included_root_count} of {len(note_ids)} result trees" in event["label"]
        for event in events
    )
    evidence_page_event = next(
        event
        for event in events
        if event["type"] == "action_status"
        and event["action"] == "investigation_page"
    )
    assert "evidence tokens" not in evidence_page_event["label"]
    assert "content chars" not in evidence_page_event["label"]
    assert evidence_page_event["approx_input_tokens"] == estimate_input_tokens(
        final_payload["authoritative_result_trees"]
    )
    assert not any(
        event["type"] == "action_status"
        and event["action"].startswith("context_narrowing")
        for event in events
    )
    trace_events = traces.snapshot(session_key="session-1")["run"]["events"]
    retention_event = next(
        event
        for event in trace_events
        if event["type"] == "EVIDENCE_ROOT_PREFIX_RETAINED"
    )
    assert retention_event["detail"]["retained_root_ids"] == list(
        note_ids[:included_root_count]
    )
    assert retention_event["detail"]["dropped_root_ids"] == list(
        note_ids[included_root_count:]
    )


def test_short_23_note_single_page_final_stays_under_8000_estimated_tokens() -> None:
    note_ids: list[str] = []
    root_ids: list[str] = []
    notes: dict[str, FrozenScopedNote] = {}
    tree_nodes: dict[str, FrozenScopedTreeNode] = {}
    for root_index in range(12):
        root_id = f"10000000-0000-4000-8000-{root_index:012d}"
        root_ids.append(root_id)
        note_ids.append(root_id)
        root_tags = ("testosterone", f"topic-{root_index}")
        notes[root_id] = FrozenScopedNote(
            note_id=root_id,
            parent_id="",
            root_note_id=root_id,
            content_text=f"Short testosterone note {root_index}.",
            explicit_tags_text=" ".join(root_tags),
            explicit_tag_terms=root_tags,
            created_at="2026-08-29T00:00:00+00:00",
            updated_at="2026-08-29T00:00:00+00:00",
            order_index=len(note_ids) - 1,
        )
        child_ids: tuple[str, ...] = ()
        if root_index < 11:
            child_id = f"20000000-0000-4000-8000-{root_index:012d}"
            child_ids = (child_id,)
            note_ids.append(child_id)
            child_tags = (f"detail-{root_index}",)
            notes[child_id] = FrozenScopedNote(
                note_id=child_id,
                parent_id=root_id,
                root_note_id=root_id,
                content_text=f"Brief supporting detail {root_index}.",
                explicit_tags_text=" ".join(child_tags),
                explicit_tag_terms=child_tags,
                created_at="2026-08-29T00:00:00+00:00",
                updated_at="2026-08-29T00:00:00+00:00",
                order_index=len(note_ids) - 1,
            )
            tree_nodes[child_id] = FrozenScopedTreeNode(
                note_id=child_id,
                parent_id=root_id,
                root_note_id=root_id,
                child_ids=(),
            )
        tree_nodes[root_id] = FrozenScopedTreeNode(
            note_id=root_id,
            parent_id="",
            root_note_id=root_id,
            child_ids=child_ids,
        )
    descriptor = AgentScopeDescriptor(
        scope_kind="search",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="testosterone",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="testosterone",
    )
    snapshot = ScopedSearchSnapshot(
        run_id="short-evidence-run",
        session_key="session-1",
        descriptor=descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=tuple(root_ids),
        ordered_note_ids=tuple(note_ids),
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=MappingProxyType(tree_nodes),
    )
    state = InvestigationState.start(
        snapshot=snapshot,
        settings=DEFAULT_AGENT_RETRIEVAL_SETTINGS,
    )
    note_page = state.current_note_page()
    messages, reference_note_ids = (
        AgentContextBuilder().build_single_page_scoped_final_messages(
            canonical_messages=[
                {
                    "role": "user",
                    "content": (
                        "please summarize all of my notes involving testosterone"
                    ),
                }
            ],
            prompts=DEFAULT_AGENT_PROMPTS,
            state=state,
            note_page=note_page,
            basis="the complete one-page frozen evidence scope",
        )
    )

    assert note_page.returned_character_count < 1_000
    assert note_page.total_pages == 1
    assert len(note_page.result_tree_ids) == 12
    assert reference_note_ids == tuple(note_ids)
    final_payload = json.loads(messages[-1]["content"].split("\n", 1)[1])
    assert "current user's exact request defines relevance" in (
        final_payload["instruction_for_evidence"]
    )
    assert "reference_catalog" not in final_payload
    assert "verified_authoritative_result_trees" not in final_payload
    assert final_payload["authoritative_result_trees"] == list(
        note_page.result_trees
    )
    serialized_final_payload = json.dumps(final_payload, sort_keys=True)
    for note_id in note_ids:
        assert serialized_final_payload.count(note_id) == 1
        assert f"[[{note_id}]]" not in serialized_final_payload
    assert estimate_message_tokens(messages) <= 8_000


def test_scoped_runtime_respond_route_never_counts_frozen_note_tokens(
    monkeypatch,
) -> None:
    def reject_root_token_count(*args, **kwargs) -> int:
        raise AssertionError("respond route must not count frozen note tokens")

    monkeypatch.setattr(
        InvestigationState,
        "_full_root_page_token_cost",
        reject_root_token_count,
    )
    inference = _FakeInference()
    inference.outputs = [
        json.dumps(
            {
                "kind": "respond",
                "reason": "The request does not require saved-note evidence.",
            }
        )
    ]
    descriptor = AgentScopeDescriptor(
        scope_kind="search",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="testosterone",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="testosterone",
    )
    frozen_scope = ScopedSearchSnapshot(
        run_id="scope-capture",
        session_key="session-1",
        descriptor=descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=("note-a",),
        ordered_note_ids=("note-a",),
        notes_by_id=MappingProxyType(
            {"note-a": _frozen_note("note-a", "PRIVATE_TESTOSTERONE_NOTE", 0)}
        ),
        tree_nodes_by_id=_root_tree_nodes("note-a"),
    )
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
        ontology_provider=TagOntology.empty,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=50,
        max_ranked_tags_per_page=10,
        max_working_summary_characters=8_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen2.5:7b-instruct",
                thinking_level="off",
                canonical_messages=[{"role": "user", "content": "hey are you there?"}],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    events = asyncio.run(collect())

    route_context = json.dumps(inference.structured_requests[0])
    final_context = json.dumps(inference.final_messages)
    assert "ROUTE_SELECTION_REQUEST" in route_context
    assert 'testosterone' in route_context
    assert 'evidence_page_count' not in route_context
    route_request = json.loads(
        inference.structured_requests[0][-1]["content"].split("\n", 1)[1]
    )
    assert route_request["current_user_request"] == "hey are you there?"
    assert route_request["explicit_saved_notes_request"] is False
    assert "PRIVATE_TESTOSTERONE_NOTE" not in route_context
    assert "PRIVATE_TESTOSTERONE_NOTE" not in final_context
    assert 'testosterone' not in final_context
    assert events[-1] == {"type": "done", "reference_note_ids": []}


def test_exact_saved_notes_request_routes_into_raw_single_page_evidence() -> None:
    inference = _FakeInference()
    inference.outputs = [
        json.dumps(
            {
                "kind": "investigate_current_scope",
                "reason": "The user explicitly asked to summarize their notes.",
            }
        )
    ]
    descriptor = AgentScopeDescriptor(
        scope_kind="search",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="testosterone",
        sort_mode="normal",
        date_filter_active=False,
        date_filter_metric="",
        date_filter_start="",
        date_filter_end="",
        reference_root_ids=[],
        label="testosterone",
    )
    frozen_scope = ScopedSearchSnapshot(
        run_id="scope-capture",
        session_key="session-1",
        descriptor=descriptor,
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=("note-a", "note-b"),
        ordered_note_ids=("note-a", "note-b"),
        notes_by_id=MappingProxyType(
            {
                "note-a": _frozen_note(
                    "note-a",
                    "PRIVATE_EXERCISE_AND_MUSCLE_NOTE",
                    0,
                ),
                "note-b": _frozen_note(
                    "note-b",
                    "PRIVATE_UNRELATED_ONIONS_NOTE",
                    1,
                ),
            }
        ),
        tree_nodes_by_id=_root_tree_nodes("note-a", "note-b"),
    )
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
        ontology_provider=TagOntology.empty,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=50,
        max_ranked_tags_per_page=10,
        max_working_summary_characters=8_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen2.5:7b-instruct",
                thinking_level="off",
                canonical_messages=[
                    {
                        "role": "user",
                        "content": (
                            "what do my notes say specifically having to do with "
                            "exercise / muscles?"
                        ),
                    }
                ],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    events = asyncio.run(collect())

    route_context = json.dumps(inference.structured_requests[0])
    final_context = json.dumps(inference.final_messages)
    assert "ROUTE_SELECTION_REQUEST" in route_context
    assert "testosterone" in route_context
    route_request = json.loads(
        inference.structured_requests[0][-1]["content"].split("\n", 1)[1]
    )
    assert route_request["explicit_saved_notes_request"] is True
    assert "PRIVATE_EXERCISE_AND_MUSCLE_NOTE" not in route_context
    assert "PRIVATE_EXERCISE_AND_MUSCLE_NOTE" in final_context
    assert "PRIVATE_UNRELATED_ONIONS_NOTE" in final_context
    assert "authoritative_result_trees" in final_context
    assert "verified_authoritative_result_trees" not in final_context
    final_payload = json.loads(
        inference.final_messages[-1]["content"].split("\n", 1)[1]
    )
    assert "reference_catalog" not in final_payload
    assert len(inference.structured_requests) == 1
    assert not any(
        event["type"] == "action_status"
        and event["action"] == "evidence_selection"
        for event in events
    )
    assert events[-1] == {
        "type": "done",
        "reference_note_ids": ["note-a", "note-b"],
    }


def test_scoped_runtime_retries_final_response_only_before_output() -> None:
    inference = _RetryFinalInference()
    scope_factory = _FakeScopeFactory()
    frozen_scope = scope_factory.freeze(
        descriptor=_descriptor(),
        authoritative_search_query="",
        authoritative_sort_mode="normal",
        authoritative_date_filter={},
        run_id="scope-capture",
        session_key="session-1",
    )
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
        ontology_provider=TagOntology.empty,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=50,
        max_ranked_tags_per_page=10,
        max_working_summary_characters=8_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen2.5:7b-instruct",
                thinking_level="off",
                canonical_messages=[{"role": "user", "content": "hey are you there?"}],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    events = asyncio.run(collect())

    retry_events = [
        event
        for event in events
        if event["type"] == "action_status"
        and event["action"] == "respond"
        and "retrying" in event["label"]
    ]
    assert inference.final_attempt_count == 2
    assert retry_events == [
        {
            "type": "action_status",
            "action": "respond",
            "status": "started",
            "label": (
                "Ollama rejected the response before output · retrying attempt 2 of 2"
            ),
                    "approx_input_tokens": retry_events[0]["approx_input_tokens"],
                    "output_tokens_received": 0,
                    "duration_ms": 0.0,
                }
    ]
    assert events[-1] == {"type": "done", "reference_note_ids": []}


def test_scoped_runtime_does_not_retry_after_partial_final_output() -> None:
    inference = _PartialFailureFinalInference()
    scope_factory = _FakeScopeFactory()
    frozen_scope = scope_factory.freeze(
        descriptor=_descriptor(),
        authoritative_search_query="",
        authoritative_sort_mode="normal",
        authoritative_date_filter={},
        run_id="scope-capture",
        session_key="session-1",
    )
    runtime = AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=AgentTraceStore(),
        provider_label="Ollama",
        ontology_provider=TagOntology.empty,
    )
    settings = AgentRetrievalSettings(
        max_note_characters=500,
        max_page_characters=5_000,
        max_notes_per_page=50,
        max_ranked_tags_per_page=10,
        max_working_summary_characters=8_000,
    )

    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in runtime.stream_scoped(
                session_key="session-1",
                base_url="http://127.0.0.1:11435",
                selected_model="qwen2.5:7b-instruct",
                thinking_level="off",
                canonical_messages=[{"role": "user", "content": "hey are you there?"}],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=settings,
                frozen_scope=frozen_scope,
            )
        ]

    with pytest.raises(
        OllamaProviderError,
        match="Ollama stream failed after output",
    ):
        asyncio.run(collect())
    assert inference.final_attempt_count == 1
