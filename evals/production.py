"""Assemble regression requests with the same builders used by MetaList."""

from dataclasses import replace
from types import MappingProxyType

from app.services.agent.actions import ContextualWebActionEnvelope
from app.services.agent.actions import RespondAction, ScopedRouteEnvelope
from app.services.agent.context import AgentContextBuilder
from app.services.agent.help_catalog import MetaListHelpResponse
from app.services.agent.investigation import InvestigationEvidencePayload, InvestigationState
from app.services.agent.prompt_settings import AgentPromptSet
from app.services.agent.prompts import load_prompt
from app.services.agent.retrieval_settings import AgentRetrievalSettings
from app.services.agent.scope import AgentScopeDescriptor, ScopedSearchSnapshot, SelectedNoteContext, SelectedTreeNote
from app.services.agent.skill_settings import AgentSkillSet, DEFAULT_AGENT_SKILLS
from app.services.agent.skills import load_skill
from app.services.agent.token_estimation import estimate_input_tokens
from app.services.agent.web_capabilities import build_web_url_capabilities
from app.services.agent.web_evidence import WebPageEvidence
from app.services.agent.web_settings import AgentWebSettings
from app.services.agent.web_settings import DEFAULT_AGENT_WEB_SETTINGS
from app.services.content_formatting import extract_agent_note_text
from evals.models import Message, PreparedStep, PreviousOutput, SelectedTreeFixture, SelectedHtmlTreeNoteFixture, UnavailableSelectionFixture


RESPONSE_MODELS = {
    schema.__name__: schema
    for schema in (
        ScopedRouteEnvelope,
        MetaListHelpResponse,
        ContextualWebActionEnvelope,
    )
}
_OUTPUT_MARKER = "__METALIST_REGRESSION_PREVIOUS_OUTPUT_"


def current_prompts() -> AgentPromptSet:
    return AgentPromptSet(system_prompt=load_prompt("system.md"),
        final_response_prompt=load_prompt("final-response.md"), tool_result_prompt=load_prompt("tool-result.md"))


def current_skills() -> AgentSkillSet:
    skills = []
    for skill in DEFAULT_AGENT_SKILLS.skills:
        if skill.trigger_action == "investigate_current_scope":
            filename = "scoped-investigation.md"
        elif skill.trigger_action == "web_browsing":
            filename = "web-browsing.md"
        else:
            assert skill.trigger_action.startswith("help_")
            filename = skill.trigger_action.replace("_", "-", 1) + ".md"
        skills.append(replace(skill, content=load_skill(filename)))
    return AgentSkillSet(skills=tuple(skills))


def fixture_snapshot(context) -> ScopedSearchSnapshot:
    """Only metadata counts are needed by the request builders; no live store."""
    scope = context.scope
    root_ids = tuple(f"fixture-root-{index}" for index in range(scope.matching_result_tree_count))
    reference_ids = []
    if scope.scope_kind == "reference":
        reference_ids = ["fixture-reference"]
    descriptor = AgentScopeDescriptor(scope_kind=scope.scope_kind, active_tab_id="fixture-tab",
        scope_tab_id="fixture-tab", search_query=scope.search_query, sort_mode=scope.sort_mode,
        reference_root_ids=reference_ids, label=scope.label)
    return ScopedSearchSnapshot(run_id="fixture-run", session_key="fixture-session", descriptor=descriptor,
        created_at="2026-01-01T00:00:00+00:00", ordered_root_ids=root_ids,
        ordered_note_ids=tuple(f"fixture-note-{index}" for index in range(scope.matching_note_count)),
        notes_by_id=MappingProxyType({}), tree_nodes_by_id=MappingProxyType({}),
        selected_note=selected_note_context(context.selected_note))


def selected_note_context(fixture) -> SelectedNoteContext:
    if isinstance(fixture, UnavailableSelectionFixture):
        return SelectedNoteContext("unavailable", "", (), fixture.reason)
    if fixture.status == "unavailable":
        return SelectedNoteContext("unavailable", "", (), "unspecified")
    if fixture.status == "none":
        return SelectedNoteContext("none", "", ())
    if isinstance(fixture, SelectedTreeFixture):
        notes = tuple(selected_tree_note(note) for note in fixture.tree_notes)
    else:
        # Existing scenarios describe a standalone leaf; production still builds its tree payload.
        notes = (SelectedTreeNote(fixture.note_id, "", fixture.content_text, fixture.tags),)
    return SelectedNoteContext("available", fixture.note_id, notes)


def selected_tree_note(note) -> SelectedTreeNote:
    if isinstance(note, SelectedHtmlTreeNoteFixture):
        def title_lookup(url):
            if url in note.cached_url_titles:
                return note.cached_url_titles[url]
            return None
        content, redacted = extract_agent_note_text(content_html=note.content_html, tags=note.tags,
            title_lookup=title_lookup)
        assert not redacted, "Selected tree fixture must contain permitted notes only"
        return SelectedTreeNote(note.note_id, note.parent_id, content, note.tags)
    return SelectedTreeNote(**note.model_dump())


def web_evidence_fixture(fixture) -> WebPageEvidence:
    return WebPageEvidence(**fixture.model_dump())


def build_messages(*, step, canonical_messages, prompts, skills):
    builder = AgentContextBuilder()
    context = step.context
    if context.stage == "help":
        messages = builder.build_help_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
            skills=skills,
            topics=context.topics,
        )
        help_request = messages[-1]
        messages = builder.append_web_access_context(
            messages=messages[:-1],
            settings=DEFAULT_AGENT_WEB_SETTINGS,
            available_urls=(),
        )
        messages.append(help_request)
        return messages, "MetaListHelpResponse"
    snapshot = fixture_snapshot(context)
    retained_web_evidence = ()
    if context.stage == "web_action":
        retained_web_evidence = tuple(
            web_evidence_fixture(fixture)
            for fixture in context.retained_web_evidence
        )
    if context.stage == "web_respond":
        retained_web_evidence = tuple(
            web_evidence_fixture(fixture)
            for fixture in context.web_evidence
        )
    capabilities = build_web_url_capabilities(
        canonical_messages=canonical_messages,
        selected_note=snapshot.selected_note,
        investigation_evidence=None,
        retained_web_urls=tuple(
            page.final_url for page in retained_web_evidence
        ),
    )
    if context.stage in {"web_action", "web_respond"}:
        settings = AgentWebSettings(mode=context.mode)
        messages = builder.build_initial_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        messages = builder.append_selected_note_context(
            messages=messages,
            snapshot=snapshot,
        )
        messages = builder.append_web_access_context(
            messages=messages,
            settings=settings,
            available_urls=capabilities.normalized_urls,
        )
        messages = builder.activate_skill(
            messages=messages,
            skill=skills.for_action("web_browsing"),
        )
        if retained_web_evidence:
            messages = builder.append_retained_web_evidence(
                messages=messages,
                evidence=retained_web_evidence,
                omitted_count=0,
            )
        if context.stage == "web_respond":
            return builder.append_final_request(
                messages=messages,
                action=RespondAction(kind="respond", basis=context.basis),
                prompts=prompts,
                current_user_request=canonical_messages[-1]["content"],
                reference_note_ids=snapshot.selected_note.reference_note_ids,
                reference_web_evidence=retained_web_evidence,
            ), ""
        for exchange in context.tool_exchanges:
            messages = builder.append_web_tool_result(
                messages=messages,
                action_payload=exchange.action_payload,
                action_name=exchange.action_name,
                result_payload=exchange.result_payload,
                prompts=prompts,
            )
        messages = builder.append_web_action_request(
            messages=messages,
            settings=settings,
        )
        response_model = "ContextualWebActionEnvelope"
        return messages, response_model
    if context.stage == "route":
        messages = builder.build_scoped_route_messages(canonical_messages=canonical_messages,
            prompts=prompts, snapshot=snapshot)
        route_request = messages[-1]
        messages = builder.append_web_access_context(
            messages=messages[:-1],
            settings=DEFAULT_AGENT_WEB_SETTINGS,
            available_urls=capabilities.normalized_urls,
        )
        messages.append(route_request)
        return messages, "ScopedRouteEnvelope"
    if context.stage == "respond":
        messages = builder.build_initial_messages(canonical_messages=canonical_messages, prompts=prompts)
        messages = builder.append_selected_note_context(messages=messages, snapshot=snapshot)
        messages = builder.append_web_access_context(
            messages=messages,
            settings=DEFAULT_AGENT_WEB_SETTINGS,
            available_urls=capabilities.normalized_urls,
        )
        return builder.append_final_request(messages=messages, action=RespondAction(kind="respond", basis=context.basis),
            prompts=prompts, current_user_request=canonical_messages[-1]["content"],
            reference_note_ids=snapshot.selected_note.reference_note_ids,
            reference_web_evidence=()), ""
    assert context.stage == "investigation"
    state = InvestigationState.start(snapshot=snapshot,
        settings=AgentRetrievalSettings(max_page_approximate_tokens=500_000))
    evidence = InvestigationEvidencePayload(evidence_note_ids=tuple(context.evidence_note_ids),
        result_tree_ids=tuple(context.result_tree_ids), result_trees=tuple(context.result_trees),
        returned_approximate_token_count=estimate_input_tokens(context.result_trees))
    messages, _references = builder.build_scoped_final_messages(canonical_messages=canonical_messages,
        prompts=prompts, state=state, evidence_payload=evidence, basis=context.basis)
    messages.insert(-1, builder.append_web_access_context(
        messages=[],
        settings=DEFAULT_AGENT_WEB_SETTINGS,
        available_urls=capabilities.normalized_urls,
    )[0])
    return messages, ""


def prepare_step(step, *, prompts, skills) -> PreparedStep:
    canonical = []
    substitutions = {}
    for message in step.conversation:
        if isinstance(message, PreviousOutput):
            marker = f"{_OUTPUT_MARKER}{message.from_step}__"
            substitutions[marker] = message
            canonical.append({"role": "assistant", "content": marker})
        else:
            if _OUTPUT_MARKER in message.content:
                raise ValueError("Conversation contains a reserved previous-output marker")
            canonical.append(message.model_dump())
    messages, response_model = build_messages(step=step, canonical_messages=canonical, prompts=prompts, skills=skills)
    prepared_messages = []
    for message in messages:
        if message["role"] == "assistant" and message["content"] in substitutions:
            prepared_messages.append(substitutions[message["content"]])
        else:
            prepared_messages.append(Message.model_validate(message))
    schema = {}
    kind = "text"
    if response_model:
        kind = "structured"
        schema = RESPONSE_MODELS[response_model].model_json_schema()
    return PreparedStep(kind=kind, messages=prepared_messages, response_model=response_model,
        response_schema=schema, max_output_tokens=step.max_output_tokens, expectation=step.expectation)
