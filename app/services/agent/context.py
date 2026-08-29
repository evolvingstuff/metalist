"""Build exact model contexts without polluting canonical conversation history."""

from __future__ import annotations

import json

from app.services.agent.actions import AgentAction
from app.services.agent.actions import RespondAction
from app.services.agent.actions import WorkingSummary
from app.services.agent.actions import request_requires_complete_scope_coverage
from app.services.agent.investigation import InvestigationNotePage
from app.services.agent.investigation import InvestigationState
from app.services.agent.investigation import TagFacetPage
from app.services.agent.prompt_settings import AgentPromptSet
from app.services.agent.scope import ScopedSearchSnapshot
from app.services.agent.skill_settings import AgentSkill
from app.services.agent.tools import ToolExecutionResult


def _exact_citation_token(note_id: str) -> str:
    if not isinstance(note_id, str) or note_id == "":
        raise ValueError("Citation note id must be non-empty")
    return f"[[{note_id}]]"


def _reference_catalog(note_ids: tuple[str, ...]) -> list[dict[str, str]]:
    if not isinstance(note_ids, tuple):
        raise TypeError("Reference note ids must be a tuple")
    return [
        {
            "note_id": note_id,
            "citation_token": _exact_citation_token(note_id),
        }
        for note_id in note_ids
    ]


def _attach_exact_citation_tokens(
    *,
    result_tree: dict[str, object],
    allowed_note_ids: frozenset[str],
) -> dict[str, object]:
    note_id = result_tree["note_id"]
    if not isinstance(note_id, str) or note_id == "":
        raise RuntimeError("Evidence tree note_id must be non-empty")
    annotated = dict(result_tree)
    if "is_evidence" in result_tree and result_tree["is_evidence"] is False:
        if note_id in allowed_note_ids:
            raise RuntimeError("Structural evidence node unexpectedly appears in catalog")
    else:
        if note_id not in allowed_note_ids:
            raise RuntimeError("Content-bearing evidence node is absent from catalog")
        annotated["citation_token"] = _exact_citation_token(note_id)
    if "children" not in result_tree:
        return annotated
    raw_children = result_tree["children"]
    if not isinstance(raw_children, list):
        raise RuntimeError("Evidence tree children must be a list")
    if raw_children:
        annotated_children: list[dict[str, object]] = []
        for child in raw_children:
            if not isinstance(child, dict):
                raise RuntimeError("Evidence tree child must be an object")
            annotated_children.append(
                _attach_exact_citation_tokens(
                    result_tree=child,
                    allowed_note_ids=allowed_note_ids,
                )
            )
        annotated["children"] = annotated_children
    return annotated


def serialize_investigation_note_page(
    note_page: InvestigationNotePage,
) -> dict[str, object]:
    if not isinstance(note_page, InvestigationNotePage):
        raise TypeError("note_page must be InvestigationNotePage")
    return {
        "state_id": note_page.state_id,
        "page": note_page.page,
        "total_pages": note_page.total_pages,
        "matching_note_count": note_page.matching_note_count,
        "matching_result_tree_count": note_page.matching_result_tree_count,
        "evidence_note_ids": list(note_page.evidence_note_ids),
        "result_trees": list(note_page.result_trees),
        "returned_approximate_token_count": (
            note_page.returned_approximate_token_count
        ),
    }


class AgentContextBuilder:
    def build_initial_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
    ) -> list[dict[str, str]]:
        self._validate_canonical_messages(canonical_messages)
        return [
            {"role": "system", "content": prompts.system_prompt},
            *[dict(message) for message in canonical_messages],
        ]

    def activate_skill(
        self,
        *,
        messages: list[dict[str, str]],
        skill: AgentSkill,
    ) -> list[dict[str, str]]:
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError("Skill activation requires an existing agent context")
        if messages[0].get("role") != "system":
            raise ValueError("Skill activation requires the base system prompt first")
        skill_message = (
            f"ACTIVE_SKILL {skill.skill_id}\n"
            f"Trigger action: {skill.trigger_action}\n\n"
            f"{skill.content}"
        )
        return [
            dict(messages[0]),
            {"role": "system", "content": skill_message},
            *[dict(message) for message in messages[1:]],
        ]

    def build_scoped_route_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
        snapshot: ScopedSearchSnapshot,
        evidence_page_count: int,
    ) -> list[dict[str, str]]:
        """Expose active-view context for routing without exposing note evidence."""
        if not isinstance(snapshot, ScopedSearchSnapshot):
            raise TypeError("snapshot must be ScopedSearchSnapshot")
        if (
            not isinstance(evidence_page_count, int)
            or isinstance(evidence_page_count, bool)
            or evidence_page_count < 1
        ):
            raise ValueError("evidence_page_count must be a positive integer")
        base = self.build_initial_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        descriptor = snapshot.descriptor
        route_scope = {
            "instruction": (
                "This is the frozen user-driven MetaList view active at Send time. "
                "Use it as routing context. It contains no note content."
            ),
            "scope_kind": descriptor.scope_kind,
            "label": descriptor.label,
            "search_query": descriptor.search_query,
            "sort_mode": descriptor.sort_mode,
            "date_filter": descriptor.normalized_date_filter(),
            "matching_note_count": snapshot.note_count,
            "matching_result_tree_count": snapshot.result_tree_count,
            "evidence_page_count": evidence_page_count,
        }
        return [
            dict(base[0]),
            {
                "role": "system",
                "content": "ACTIVE_METALIST_SCOPE\n"
                + json.dumps(route_scope, sort_keys=True, separators=(",", ":")),
            },
            *[dict(message) for message in base[1:]],
        ]

    def append_action(
        self,
        *,
        messages: list[dict[str, str]],
        action: AgentAction,
    ) -> list[dict[str, str]]:
        action_json = json.dumps(action.model_dump(), sort_keys=True, separators=(",", ":"))
        return [*messages, {"role": "assistant", "content": action_json}]

    def append_tool_result(
        self,
        *,
        messages: list[dict[str, str]],
        result: ToolExecutionResult,
        prompts: AgentPromptSet,
    ) -> list[dict[str, str]]:
        payload_json = json.dumps(result.payload, sort_keys=True, separators=(",", ":"))
        content = prompts.render_tool_result(
            action_name=result.action_name,
            payload_json=payload_json,
        )
        return [*messages, {"role": "user", "content": content}]

    def append_final_request(
        self,
        *,
        messages: list[dict[str, str]],
        action: RespondAction,
        prompts: AgentPromptSet,
    ) -> list[dict[str, str]]:
        with_action = self.append_action(messages=messages, action=action)
        content = prompts.render_final_response_request(basis=action.basis)
        return [*with_action, {"role": "user", "content": content}]

    def build_scoped_investigation_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
        skill: AgentSkill,
        state: InvestigationState,
        note_page: InvestigationNotePage,
        facet_page: TagFacetPage,
        working_summary: WorkingSummary,
        reopened_sources: tuple[dict[str, object], ...],
    ) -> list[dict[str, str]]:
        """Rebuild one bounded step context; previous raw pages never enter it."""
        base = self.build_initial_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        with_skill = self.activate_skill(messages=base, skill=skill)
        snapshot = state.snapshot
        requires_complete_scope_coverage = request_requires_complete_scope_coverage(
            canonical_messages[-1]["content"]
        )
        available_actions = [
            "refine_tags",
            "refine_exact_text",
            "reopen_sources",
        ]
        if note_page.page < note_page.total_pages:
            available_actions.insert(0, "page_next")
        if not (
            requires_complete_scope_coverage
            and note_page.page < note_page.total_pages
        ):
            available_actions.append("answer")
        if facet_page.total_pages > 1:
            available_actions.append("inspect_tag_facets")
        if len(state.disclosed_state_ids) > 1:
            available_actions.append("backtrack")
        runtime_payload = {
            "instruction": (
                "Replace working_summary and choose exactly one next action using "
                "the required InvestigationStep schema. Current note content is "
                "answerable evidence, not an ID-only preview."
            ),
            "frozen_scope": {
                "kind": snapshot.descriptor.scope_kind,
                "label": snapshot.descriptor.label,
                "search_query": snapshot.descriptor.search_query,
                "note_count": snapshot.note_count,
                "result_tree_count": snapshot.result_tree_count,
                "evidence_page_count": note_page.total_pages,
            },
            "current_state": {
                "state_id": state.current_state_id,
                "disclosed_state_ids": list(state.disclosed_state_ids),
                "observed_source_ids": sorted(state.observed_source_ids),
                "disclosed_tags": sorted(state.disclosed_tags),
            },
            "available_actions": available_actions,
            "coverage_requirement": (
                "complete" if requires_complete_scope_coverage else "question-dependent"
            ),
            "working_summary": working_summary.model_dump(mode="json"),
            "tag_facets": {
                "page": facet_page.page,
                "total_pages": facet_page.total_pages,
                "total_facets": facet_page.total_facets,
                "facets": [
                    {
                        "tag": facet.tag,
                        "matching_notes": facet.note_count,
                        "matching_result_trees": facet.result_tree_count,
                    }
                    for facet in facet_page.facets
                ],
            },
            "note_page": serialize_investigation_note_page(note_page),
            "reopened_sources": list(reopened_sources),
        }
        return [
            *with_skill,
            {
                "role": "user",
                "content": "SCOPED_INVESTIGATION_STATE\n"
                + json.dumps(runtime_payload, sort_keys=True, separators=(",", ":")),
            },
        ]

    def build_scoped_final_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
        state: InvestigationState,
        working_summary: WorkingSummary,
        verified_sources: tuple[dict[str, object], ...],
        reference_note_ids: tuple[str, ...],
        basis: str,
    ) -> list[dict[str, str]]:
        if not isinstance(reference_note_ids, tuple):
            raise TypeError("reference_note_ids must be a tuple")
        allowed_note_ids = frozenset(reference_note_ids)
        cited_sources: list[dict[str, object]] = []
        for source in verified_sources:
            note_id = source["note_id"]
            if not isinstance(note_id, str) or note_id == "":
                raise RuntimeError("Verified source note_id must be non-empty")
            if note_id not in allowed_note_ids:
                raise RuntimeError("Verified source is absent from reference catalog")
            cited_sources.append(
                {
                    **source,
                    "citation_token": _exact_citation_token(note_id),
                }
            )
        base = self.build_initial_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        final_payload = {
            "instruction": prompts.render_final_response_request(basis=basis),
            "frozen_scope": {
                "kind": state.snapshot.descriptor.scope_kind,
                "label": state.snapshot.descriptor.label,
                "note_count": state.snapshot.note_count,
                "result_tree_count": state.snapshot.result_tree_count,
            },
            "working_summary": working_summary.model_dump(mode="json"),
            "reference_catalog": _reference_catalog(reference_note_ids),
            "verified_authoritative_sources": cited_sources,
        }
        return [
            *base,
            {
                "role": "user",
                "content": "FINAL_RESPONSE_REQUEST\n"
                + json.dumps(final_payload, sort_keys=True, separators=(",", ":")),
            },
        ]

    def build_single_page_scoped_final_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
        state: InvestigationState,
        note_page: InvestigationNotePage,
        basis: str,
    ) -> tuple[list[dict[str, str]], tuple[str, ...]]:
        """Send one complete frozen evidence page directly to final generation."""
        if not isinstance(note_page, InvestigationNotePage):
            raise TypeError("note_page must be InvestigationNotePage")
        if note_page.total_pages != 1 or note_page.page != 1:
            raise ValueError("Single-page final context requires the complete first page")
        if not isinstance(basis, str) or basis.strip() == "":
            raise ValueError("Single-page final basis must be non-empty")
        reference_note_ids = note_page.evidence_note_ids
        allowed_note_ids = frozenset(reference_note_ids)
        cited_result_trees = [
            {
                "root_note_id": root_note_id,
                "result_tree": _attach_exact_citation_tokens(
                    result_tree=result_tree,
                    allowed_note_ids=allowed_note_ids,
                ),
            }
            for root_note_id, result_tree in zip(
                note_page.result_tree_ids,
                note_page.result_trees,
                strict=True,
            )
        ]
        base = self.build_initial_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        final_payload = {
            "instruction": prompts.render_final_response_request(basis=basis),
            "frozen_scope": {
                "kind": state.snapshot.descriptor.scope_kind,
                "label": state.snapshot.descriptor.label,
                "search_query": state.snapshot.descriptor.search_query,
                "note_count": state.snapshot.note_count,
                "result_tree_count": state.snapshot.result_tree_count,
                "evidence_page_count": 1,
            },
            "instruction_for_evidence": (
                "This is the complete frozen evidence scope, already grouped into "
                "ordered root-note trees. The current user's exact request defines "
                "relevance; this page is candidate evidence, not a checklist. Omit "
                "nodes that do not directly answer the request even if they share the "
                "scope topic. Copy citation_token from the same evidence object whose "
                "content_text supports the claim. Do not infer a citation from tree "
                "position or merely cite the enclosing root."
            ),
            "reference_catalog": _reference_catalog(reference_note_ids),
            "verified_authoritative_result_trees": cited_result_trees,
        }
        return (
            [
                *base,
                {
                    "role": "user",
                    "content": "FINAL_RESPONSE_REQUEST\n"
                    + json.dumps(final_payload, sort_keys=True, separators=(",", ":")),
                },
            ],
            reference_note_ids,
        )

    def build_single_page_evidence_selection_messages(
        self,
        *,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
        skill: AgentSkill,
        state: InvestigationState,
        note_page: InvestigationNotePage,
    ) -> list[dict[str, str]]:
        """Ask for a small exact-ID relevance decision before prose generation."""
        if not isinstance(note_page, InvestigationNotePage):
            raise TypeError("note_page must be InvestigationNotePage")
        if note_page.page != 1 or note_page.total_pages != 1:
            raise ValueError("Evidence selection requires one complete evidence page")
        base = self.build_initial_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        with_skill = self.activate_skill(messages=base, skill=skill)
        payload = {
            "instruction": "Apply the active skill and return EvidenceSelection.",
            "current_user_request": canonical_messages[-1]["content"],
            "frozen_scope": {
                "kind": state.snapshot.descriptor.scope_kind,
                "label": state.snapshot.descriptor.label,
                "search_query": state.snapshot.descriptor.search_query,
                "note_count": state.snapshot.note_count,
                "result_tree_count": state.snapshot.result_tree_count,
                "evidence_page_count": 1,
            },
            "candidate_evidence_page": serialize_investigation_note_page(note_page),
        }
        return [
            *with_skill,
            {
                "role": "user",
                "content": "EVIDENCE_SELECTION_REQUEST\n"
                + json.dumps(payload, sort_keys=True, separators=(",", ":")),
            },
        ]

    @staticmethod
    def _validate_canonical_messages(messages: list[dict[str, str]]) -> None:
        if not isinstance(messages, list) or len(messages) == 0:
            raise ValueError("Canonical agent messages must be a non-empty list")
        for message in messages:
            if not isinstance(message, dict) or set(message) != {"role", "content"}:
                raise ValueError("Canonical agent message must contain role and content")
            if message["role"] not in {"user", "assistant"}:
                raise ValueError("Canonical agent message has unsupported role")
            if not isinstance(message["content"], str) or message["content"] == "":
                raise ValueError("Canonical agent message content must be non-empty")
        if messages[-1]["role"] != "user":
            raise ValueError("Canonical agent context must end with the current user message")
