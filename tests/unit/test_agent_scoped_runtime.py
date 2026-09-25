from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import MappingProxyType

import pytest

from app.services.agent.context import AgentContextBuilder
from app.services.agent.inference import InferenceAttempt
from app.services.agent.inference import InferenceContextWindow
from app.services.agent.inference import InferenceResponse
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.model_policy import SingleModelPolicy
from app.services.agent.permissions import AgentPermissionPolicy
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.runtime import AgentRuntime
from app.services.agent.scope import AgentScopeDescriptor
from app.services.agent.scope import FrozenScopedNote
from app.services.agent.scope import FrozenScopedTreeNode
from app.services.agent.scope import ScopedSearchSnapshot
from app.services.agent.scope import SelectedNoteContext, SelectedTreeNote
from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.web_settings import DEFAULT_AGENT_WEB_SETTINGS
from app.services.agent.web_settings import AgentWebSettings
from app.services.agent.web_evidence import web_evidence_store
from app.services.agent.web_fetch import WebPageFetchResult
from app.services.agent.trace import AgentTraceStore


def _descriptor() -> AgentScopeDescriptor:
    return AgentScopeDescriptor(
        scope_kind="search",
        active_tab_id="tab-1",
        scope_tab_id="tab-1",
        search_query="testosterone",
        sort_mode="normal",
        reference_root_ids=[],
        label="testosterone",
    )


def _note(
    note_id: str,
    root_note_id: str,
    parent_id: str,
    content: str,
    index: int,
) -> FrozenScopedNote:
    return FrozenScopedNote(
        note_id=note_id,
        parent_id=parent_id,
        root_note_id=root_note_id,
        content_text=content,
        explicit_tags_text="testosterone",
        explicit_tag_terms=("testosterone",),
        proposed_tags_text="",
        proposed_tag_terms=(),
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:00+00:00",
        order_index=index,
    )


def _snapshot(*, large_tail: bool) -> ScopedSearchSnapshot:
    tail = "TAIL"
    if large_tail:
        tail = "TAIL " * 10_000
    notes = {
        "root-a": _note("root-a", "root-a", "", "ROOT_ALPHA", 0),
        "child-a": _note("child-a", "root-a", "root-a", "CHILD_ALPHA", 1),
        "root-b": _note("root-b", "root-b", "", tail, 2),
    }
    nodes = {
        "root-a": FrozenScopedTreeNode(
            note_id="root-a",
            parent_id="",
            root_note_id="root-a",
            child_ids=("child-a",),
        ),
        "child-a": FrozenScopedTreeNode(
            note_id="child-a",
            parent_id="root-a",
            root_note_id="root-a",
            child_ids=(),
        ),
        "root-b": FrozenScopedTreeNode(
            note_id="root-b",
            parent_id="",
            root_note_id="root-b",
            child_ids=(),
        ),
    }
    return ScopedSearchSnapshot(
        run_id="scope-run",
        session_key="session-1",
        descriptor=_descriptor(),
        created_at="2026-08-29T00:00:00+00:00",
        ordered_root_ids=("root-a", "root-b"),
        ordered_note_ids=("root-a", "child-a", "root-b"),
        notes_by_id=MappingProxyType(notes),
        tree_nodes_by_id=MappingProxyType(nodes),
    )


class _FakeInference:
    provider_label = "OpenAI"

    def __init__(self, *, route_kind: str) -> None:
        self.route_kind = route_kind
        self.final_messages: list[dict[str, str]] = []
        self.route_messages: list[dict[str, str]] = []

    async def inspect_context_window(
        self,
        *,
        base_url: str,
        model: str,
    ) -> InferenceContextWindow:
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
    ) -> InferenceResponse:
        del thinking_level
        self.route_messages = messages
        payload = {
            "kind": self.route_kind,
            "help_topics": [],
            "reason": "Saved-note evidence is required."
            if self.route_kind == "investigate_current_scope"
            else "No saved-note evidence is required.",
        }
        content = json.dumps(payload)
        response_model.model_validate_json(content)
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
                    output_tokens_received=10,
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

    async def stream_text(self, **arguments):
        self.final_messages = arguments["messages"]
        arguments["on_request"]({
            "method": "POST",
            "url": f'{arguments["base_url"]}/api/chat',
            "body": {
                "model": arguments["model"],
                "messages": arguments["messages"],
            },
        })
        yield {"type": "content_delta", "text": "Answer [[child-a]]"}
        yield {"type": "done"}


class _UnusedTools:
    pass


def _runtime(inference: _FakeInference) -> AgentRuntime:
    return AgentRuntime(
        context_builder=AgentContextBuilder(),
        inference=inference,
        model_policy=SingleModelPolicy(),
        permission_policy=AgentPermissionPolicy(),
        tool_registry=_UnusedTools(),
        trace_store=AgentTraceStore(),
        provider_label="OpenAI",
    )


def _events(
    *,
    inference: _FakeInference,
    snapshot: ScopedSearchSnapshot,
    message: str,
    token_limit: int,
) -> list[dict[str, object]]:
    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in _runtime(inference).stream_scoped(
                tag_handler=None,
                session_key="session-1",
                base_url="https://api.openai.com/v1",
                selected_model="gpt-5.6-sol",
                thinking_level="off",
                canonical_messages=[{"role": "user", "content": message}],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=AgentRetrievalSettings(
                    max_page_approximate_tokens=token_limit,
                ),
                web_settings=DEFAULT_AGENT_WEB_SETTINGS,
                frozen_scope=snapshot,
            )
        ]

    return asyncio.run(collect())


def test_scoped_request_sends_one_full_nested_evidence_payload_directly() -> None:
    inference = _FakeInference(route_kind="investigate_current_scope")
    events = _events(
        inference=inference,
        snapshot=_snapshot(large_tail=False),
        message="please summarize my notes about testosterone",
        token_limit=24_000,
    )

    final_requests = [
        message
        for message in inference.final_messages
        if message["content"].startswith("FINAL_RESPONSE_REQUEST\n")
    ]
    assert len(final_requests) == 1
    final_payload = json.loads(inference.final_messages[-1]["content"].split("\n", 1)[1])
    assert len(final_payload["authoritative_result_trees"]) == 2
    assert final_payload["authoritative_result_trees"][0]["content_text"] == "ROOT_ALPHA"
    assert final_payload["authoritative_result_trees"][0]["children"][0][
        "content_text"
    ] == "CHILD_ALPHA"
    assert all("working_summary" not in message["content"] for message in inference.final_messages)
    assert any(event.get("type") == "done" for event in events)


def test_oversized_scope_omits_only_trailing_complete_roots() -> None:
    inference = _FakeInference(route_kind="investigate_current_scope")
    events = _events(
        inference=inference,
        snapshot=_snapshot(large_tail=True),
        message="please summarize my notes about testosterone",
        token_limit=500,
    )

    final_payload = json.loads(inference.final_messages[-1]["content"].split("\n", 1)[1])
    assert len(final_payload["authoritative_result_trees"]) == 1
    assert final_payload["authoritative_result_trees"][0]["note_id"] == "root-a"
    assert final_payload["evidence_coverage"]["omitted_result_tree_count"] == 1
    labels = [event.get("label", "") for event in events]
    assert "Only using 1 of 2 root notes for answer" in labels


def test_direct_response_does_not_send_note_content() -> None:
    inference = _FakeInference(route_kind="respond")
    _events(
        inference=inference,
        snapshot=_snapshot(large_tail=False),
        message="please explain Bayes theorem",
        token_limit=24_000,
    )

    serialized_messages = json.dumps(inference.final_messages)
    assert "ROOT_ALPHA" not in serialized_messages
    assert "CHILD_ALPHA" not in serialized_messages


@pytest.mark.parametrize("route", ["respond", "investigate_current_scope"])
def test_selected_note_reaches_routing_and_final_without_narrowing_scope(route) -> None:
    inference = _FakeInference(route_kind=route)
    snapshot = replace(_snapshot(large_tail=False), selected_note=SelectedNoteContext(
        "available", "child-a", (SelectedTreeNote("parent", "", "PARENT_CONTEXT", "parent-tag"),
            SelectedTreeNote("child-a", "parent", "CURRENT_SELECTED_CONTENT", "selected-tag"),
            SelectedTreeNote("abstract", "child-a", "ABSTRACT_CONTENT", "abstract-tag"),
            SelectedTreeNote("sibling", "parent", "SIBLING_CONTEXT", "sibling-tag"))))
    _events(inference=inference, snapshot=snapshot,
        message="Can you explain the relevant parts?", token_limit=24_000)
    for messages in (inference.route_messages, inference.final_messages):
        contexts = [json.loads(m["content"].split("\n", 1)[1]) for m in messages
                    if m["content"].startswith("SELECTED_NOTE_CONTEXT\n")]
        assert len(contexts) == 1
        assert [n["note_id"] for n in contexts[0]["selected_note"]["tree_notes"] if n["is_selected"]] == ["child-a"]
        assert all(text in json.dumps(contexts[0]) for text in ("PARENT_CONTEXT", "CURRENT_SELECTED_CONTENT", "ABSTRACT_CONTENT", "SIBLING_CONTEXT"))
        assert contexts[0]["selected_note"]["note_id"] == "child-a"
    if route == "respond":
        assert "ROOT_ALPHA" not in json.dumps(inference.final_messages)
    else:
        assert "ROOT_ALPHA" in json.dumps(inference.final_messages)
        assert "TAIL" in json.dumps(inference.final_messages)


def test_selected_note_over_budget_is_not_sent_to_provider() -> None:
    inference = _FakeInference(route_kind="respond")
    snapshot = replace(_snapshot(large_tail=False), selected_note=SelectedNoteContext(
        "available", "child-a", (SelectedTreeNote("parent", "", "PARENT", ""),
            SelectedTreeNote("child-a", "parent", "https://example.test/paper", ""),
            SelectedTreeNote("abstract", "child-a", "LARGE " * 1000, ""))))
    with pytest.raises(Exception, match="selected note tree exceeds"):
        _events(inference=inference, snapshot=snapshot, message="Explain", token_limit=500)
    assert inference.route_messages == []
    assert inference.final_messages == []


def test_model_can_respond_to_request_prohibiting_note_inspection() -> None:
    inference = _FakeInference(route_kind="respond")
    _events(
        inference=inference,
        snapshot=_snapshot(large_tail=False),
        message="Answer from our conversation; do not inspect current notes.",
        token_limit=24_000,
    )
    assert inference.final_messages
    assert "ROOT_ALPHA" not in json.dumps(inference.final_messages)


class _WebInference(_FakeInference):
    def __init__(
        self,
        *,
        web_actions: list[dict[str, object]],
        route_kind: str,
    ) -> None:
        super().__init__(route_kind=route_kind)
        self.web_actions = list(web_actions)

    async def infer_structured(self, **arguments) -> InferenceResponse:
        response_model = arguments["response_model"]
        if response_model.__name__ == "ScopedRouteEnvelope":
            return await super().infer_structured(**arguments)
        assert response_model.__name__ == "ContextualWebActionEnvelope"
        assert self.web_actions, "Web planner requested more fixture actions"
        content = json.dumps(self.web_actions.pop(0))
        response_model.model_validate_json(content)
        return InferenceResponse(
            content=content,
            thinking="",
            usage={},
            attempts=[InferenceAttempt(request={}, response={}, error="", duration_ms=1.0)],
        )

    async def stream_text(self, **arguments):
        self.final_messages = arguments["messages"]
        final_payload = json.loads(
            arguments["messages"][-1]["content"].split("\n", 1)[1]
        )
        web_catalog = final_payload["web_reference_catalog"]
        citation = ""
        if web_catalog:
            citation = " " + web_catalog[0]["citation_token"]
        yield {"type": "content_delta", "text": "Web answer" + citation}
        yield {"type": "done"}


def _web_events(*, inference, snapshot, mode):
    async def collect():
        return [
            event
            async for event in _runtime(inference).stream_scoped(
                tag_handler=None,
                session_key="session-1",
                base_url="https://api.openai.com/v1",
                selected_model="gpt-5.6-sol",
                thinking_level="off",
                canonical_messages=[{"role": "user", "content": "Read the linked page"}],
                prompts=DEFAULT_AGENT_PROMPTS,
                skills=DEFAULT_AGENT_SKILLS,
                retrieval_settings=AgentRetrievalSettings(
                    max_page_approximate_tokens=24_000,
                ),
                web_settings=AgentWebSettings(mode=mode),
                frozen_scope=snapshot,
            )
        ]
    return asyncio.run(collect())


def test_contextual_web_loop_opens_disclosed_url_and_cites_retained_page(monkeypatch) -> None:
    web_evidence_store.reset()
    snapshot = replace(
        _snapshot(large_tail=False),
        selected_note=SelectedNoteContext(
            "available",
            "child-a",
            (SelectedTreeNote(
                "child-a", "", "See https://example.com/article", "source"
            ),),
        ),
    )
    inference = _WebInference(route_kind="respond", web_actions=[
        {"kind": "open_web_pages", "urls": ["https://example.com/article"],
         "reason": "Open disclosed source"},
        {"kind": "respond", "urls": [], "reason": "Page is sufficient"},
    ])
    calls = []

    async def fake_fetch(urls):
        calls.append(list(urls))
        return (WebPageFetchResult(
            requested_url="https://example.com/article",
            final_url="https://example.com/article",
            status="ok",
            title="Article",
            content_text="Verified page content",
            fetched_at="2026-09-24T00:00:00+00:00",
            truncated=False,
            error_kind="",
        ),)

    monkeypatch.setattr("app.services.agent.runtime.fetch_web_pages", fake_fetch)
    events = _web_events(inference=inference, snapshot=snapshot, mode="contextual")

    assert calls == [["https://example.com/article"]]
    assert events[-1]["type"] == "done"
    assert len(events[-1]["reference_web_ids"]) == 1
    assert "web_reference_catalog" in inference.final_messages[-1]["content"]


def test_contextual_web_loop_blocks_undisclosed_url_without_network(monkeypatch) -> None:
    web_evidence_store.reset()
    inference = _WebInference(route_kind="respond", web_actions=[
        {"kind": "open_web_pages", "urls": ["https://private.example/hidden"],
         "reason": "Try URL"},
        {"kind": "respond", "urls": [], "reason": "Explain contextual limit"},
    ])

    async def forbidden_fetch(_urls):
        raise AssertionError("Undisclosed contextual URL reached the network")

    monkeypatch.setattr("app.services.agent.runtime.fetch_web_pages", forbidden_fetch)
    events = _web_events(
        inference=inference,
        snapshot=_snapshot(large_tail=False),
        mode="contextual",
    )

    assert events[-1]["reference_web_ids"] == []
    tool_messages = [
        message["content"] for message in inference.final_messages
        if message["content"].startswith("TOOL_RESULT open_web_pages")
    ]
    assert len(tool_messages) == 1
    assert "not_available_in_permitted_context" in tool_messages[0]


def test_full_web_loop_opens_agent_proposed_url_outside_context(monkeypatch) -> None:
    web_evidence_store.reset()
    inference = _WebInference(route_kind="respond", web_actions=[
        {"kind": "open_web_pages", "urls": ["https://example.com/quote"],
         "reason": "Open a direct public source"},
        {"kind": "respond", "urls": [], "reason": "Explain opened page"},
    ])
    calls = []

    async def fake_fetch(urls):
        calls.append(list(urls))
        return (WebPageFetchResult(
            requested_url="https://example.com/quote",
            final_url="https://example.com/quote",
            status="ok",
            title="Public quote",
            content_text="Current value: 42",
            fetched_at="2026-09-24T00:00:00+00:00",
            truncated=False,
            error_kind="",
        ),)

    monkeypatch.setattr("app.services.agent.runtime.fetch_web_pages", fake_fetch)

    events = _web_events(
        inference=inference,
        snapshot=_snapshot(large_tail=False),
        mode="full",
    )

    assert calls == [["https://example.com/quote"]]
    assert events[-1]["type"] == "done"
    assert len(events[-1]["reference_web_ids"]) == 1


def test_investigation_web_loop_preserves_full_note_evidence() -> None:
    web_evidence_store.reset()
    inference = _WebInference(
        route_kind="investigate_current_scope",
        web_actions=[
            {
                "kind": "respond",
                "urls": [],
                "reason": "The note evidence is sufficient",
            },
        ],
    )

    events = _web_events(
        inference=inference,
        snapshot=_snapshot(large_tail=False),
        mode="contextual",
    )

    assert events[-1]["type"] == "done"
    assert "INVESTIGATION_EVIDENCE_CONTEXT" in json.dumps(
        inference.final_messages
    )
    assert "ROOT_ALPHA" in json.dumps(inference.final_messages)
    assert "TAIL" in json.dumps(inference.final_messages)
