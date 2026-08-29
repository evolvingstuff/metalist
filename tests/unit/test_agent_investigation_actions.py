from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.services.agent.actions import InvestigationStep
from app.services.agent.actions import InvestigationStepConstraints
from app.services.agent.actions import EvidenceSelection
from app.services.agent.actions import EvidenceSelectionConstraints
from app.services.agent.actions import ScopedRouteConstraints
from app.services.agent.actions import ScopedRouteEnvelope
from app.services.agent.actions import WorkingEvidence
from app.services.agent.actions import WorkingSummary
from app.services.agent.actions import bind_investigation_step_constraints
from app.services.agent.actions import bind_evidence_selection_constraints
from app.services.agent.actions import bind_scoped_route_constraints
from app.services.agent.actions import request_explicitly_requires_saved_notes
from app.services.agent.actions import request_requires_complete_scope_coverage
from app.services.agent.actions import validate_working_summary_for_observed_sources


def _summary() -> WorkingSummary:
    return WorkingSummary(
        answer_relevant_facts=[
            WorkingEvidence(claim="The note says lorem ipsum.", source_ids=["note-a"])
        ],
        possible_conclusions=[],
        contradictions_or_uncertainties=[],
        unresolved_questions=[],
        useful_search_terms_or_tags=["foo"],
    )


def test_exact_saved_notes_request_cannot_validate_as_respond() -> None:
    user_message = "please summarize my notes about testosterone"
    requires_saved_notes = request_explicitly_requires_saved_notes(user_message)

    assert requires_saved_notes is True
    constraints = ScopedRouteConstraints(
        explicit_saved_notes_request=requires_saved_notes,
    )
    with bind_scoped_route_constraints(constraints):
        with pytest.raises(
            ValidationError,
            match="explicitly requests evidence from saved notes",
        ):
            ScopedRouteEnvelope.model_validate(
                {
                    "kind": "respond",
                    "reason": (
                        "The request does not require specific evidence from the "
                        "user's saved notes."
                    ),
                }
            )


@pytest.mark.parametrize(
    "user_message",
    (
        "please describe Bayes' theorem briefly",
        "please answer without using my notes",
    ),
)
def test_non_note_evidence_requests_do_not_force_investigation(
    user_message: str,
) -> None:
    assert request_explicitly_requires_saved_notes(user_message) is False


def _payload() -> dict[str, object]:
    return {
        "working_summary": _summary().model_dump(),
        "action_kind": "answer",
        "tag_expression": "",
        "exact_text": "",
        "facet_page": 0,
        "backtrack_state_id": "",
        "source_ids": [],
        "answer_source_ids": ["note-a"],
        "reason": "The observed source directly answers the question.",
        "evidence_sufficiency": "sufficient",
    }


def test_investigation_step_requires_every_flat_action_field() -> None:
    payload = _payload()
    del payload["exact_text"]

    with pytest.raises(ValidationError):
        InvestigationStep.model_validate(payload)


def test_investigation_step_normalizes_model_noise_in_inactive_action_fields() -> None:
    payload = _payload()
    payload.update(
        {
            "action_kind": "inspect_tag_facets",
            "tag_expression": "irrelevant-model-noise",
            "facet_page": 2,
            "answer_source_ids": ["irrelevant-source"],
            "evidence_sufficiency": "insufficient",
        }
    )

    step = InvestigationStep.model_validate(payload)

    assert step.facet_page == 2
    assert step.tag_expression == ""
    assert step.answer_source_ids == []


def test_investigation_step_wire_schema_omits_ollama_incompatible_max_length() -> None:
    serialized_schema = json.dumps(InvestigationStep.model_json_schema())

    assert '"maxLength"' not in serialized_schema


def test_working_summary_schema_derives_references_from_structured_evidence() -> None:
    properties = WorkingSummary.model_json_schema()["properties"]

    assert "source_references" not in properties


def test_working_summary_schema_programmatically_bounds_rolling_output() -> None:
    properties = WorkingSummary.model_json_schema()["properties"]

    assert properties["answer_relevant_facts"]["maxItems"] == 4
    assert properties["possible_conclusions"]["maxItems"] == 2
    assert properties["contradictions_or_uncertainties"]["maxItems"] == 2
    assert properties["unresolved_questions"]["maxItems"] == 4
    assert properties["useful_search_terms_or_tags"]["maxItems"] == 6


def test_investigation_wire_schema_places_action_before_working_summary() -> None:
    property_names = list(InvestigationStep.model_json_schema()["properties"])

    assert property_names[0] == "action_kind"
    assert property_names[-1] == "working_summary"


def test_working_evidence_accepts_at_most_four_direct_sources() -> None:
    with pytest.raises(ValidationError, match="at most 4 items"):
        WorkingEvidence(
            claim="A broad claim must not carry an indiscriminate source dump.",
            source_ids=[f"note-{index}" for index in range(5)],
        )


def test_investigation_step_schema_explains_inactive_action_sentinels() -> None:
    properties = InvestigationStep.model_json_schema()["properties"]

    assert properties["facet_page"]["description"].endswith("emit 0 otherwise.")
    assert properties["source_ids"]["description"].endswith(
        "emit an empty array otherwise."
    )


def test_investigation_step_still_validates_string_length_off_wire() -> None:
    payload = _payload()
    payload["reason"] = "x" * 2_001

    with pytest.raises(ValidationError, match="at most 2000 characters"):
        InvestigationStep.model_validate(payload)


def test_investigation_step_clears_inactive_argument_for_selected_action() -> None:
    payload = _payload()
    payload["tag_expression"] = "foo"

    step = InvestigationStep.model_validate(payload)

    assert step.action_kind == "answer"
    assert step.tag_expression == ""


def test_investigation_step_answer_requires_sufficient_evidence() -> None:
    payload = _payload()
    payload["evidence_sufficiency"] = "insufficient"

    with pytest.raises(ValidationError, match="answer requires sufficient evidence"):
        InvestigationStep.model_validate(payload)


def test_working_summary_rejects_unobserved_source_provenance() -> None:
    with pytest.raises(ValueError, match="unobserved source"):
        validate_working_summary_for_observed_sources(
            summary=_summary(),
            observed_source_ids=frozenset({"note-b"}),
            maximum_characters=8_000,
        )


def test_working_summary_enforces_total_serialized_budget() -> None:
    summary = _summary().model_copy(
        update={"unresolved_questions": ["x" * 2_000]}
    )
    serialized_size = len(json.dumps(summary.model_dump(), separators=(",", ":")))
    assert serialized_size > 1_000

    with pytest.raises(ValueError, match="character budget"):
        validate_working_summary_for_observed_sources(
            summary=summary,
            observed_source_ids=frozenset({"note-a"}),
            maximum_characters=1_000,
        )


def test_investigation_step_dynamic_constraints_reject_invalid_runtime_choice() -> None:
    constraints = InvestigationStepConstraints(
        has_next_note_page=False,
        requires_complete_scope_coverage=False,
        current_facet_page=1,
        total_facet_pages=1,
        disclosed_tags=frozenset({"foo"}),
        disclosed_state_ids=frozenset({"scope-0"}),
        observed_source_ids=frozenset({"note-a"}),
    )
    payload = _payload()
    payload.update({
        "action_kind": "page_next",
        "answer_source_ids": [],
        "evidence_sufficiency": "insufficient",
    })

    with bind_investigation_step_constraints(constraints):
        with pytest.raises(ValidationError, match="no next note page"):
            InvestigationStep.model_validate(payload)


def test_investigation_step_dynamic_constraints_accept_disclosed_tag_refinement() -> None:
    constraints = InvestigationStepConstraints(
        has_next_note_page=True,
        requires_complete_scope_coverage=False,
        current_facet_page=1,
        total_facet_pages=2,
        disclosed_tags=frozenset({"foo", "bar"}),
        disclosed_state_ids=frozenset({"scope-0"}),
        observed_source_ids=frozenset({"note-a"}),
    )
    payload = _payload()
    payload.update({
        "action_kind": "refine_tags",
        "tag_expression": "foo -bar",
        "answer_source_ids": [],
        "evidence_sufficiency": "insufficient",
    })

    with bind_investigation_step_constraints(constraints):
        step = InvestigationStep.model_validate(payload)

    assert step.tag_expression == "foo -bar"


def test_investigation_step_dynamic_constraints_reject_current_facet_page() -> None:
    constraints = InvestigationStepConstraints(
        has_next_note_page=True,
        requires_complete_scope_coverage=False,
        current_facet_page=1,
        total_facet_pages=2,
        disclosed_tags=frozenset({"foo"}),
        disclosed_state_ids=frozenset({"scope-0"}),
        observed_source_ids=frozenset({"note-a"}),
    )
    payload = _payload()
    payload.update(
        {
            "action_kind": "inspect_tag_facets",
            "facet_page": 1,
            "answer_source_ids": [],
            "evidence_sufficiency": "insufficient",
        }
    )

    with bind_investigation_step_constraints(constraints):
        with pytest.raises(ValidationError, match="already current"):
            InvestigationStep.model_validate(payload)


def test_complete_scope_request_cannot_answer_before_last_evidence_page() -> None:
    constraints = InvestigationStepConstraints(
        has_next_note_page=True,
        requires_complete_scope_coverage=True,
        current_facet_page=1,
        total_facet_pages=1,
        disclosed_tags=frozenset({"foo"}),
        disclosed_state_ids=frozenset({"scope-0"}),
        observed_source_ids=frozenset({"note-a"}),
    )

    with bind_investigation_step_constraints(constraints):
        with pytest.raises(ValidationError, match="evidence page remains"):
            InvestigationStep.model_validate(_payload())


@pytest.mark.parametrize(
    "user_message",
    (
        "please summarize all of my notes involving testosterone",
        "review everything in this scope",
        "give me an exhaustive synthesis",
    ),
)
def test_complete_scope_coverage_detection(user_message: str) -> None:
    assert request_requires_complete_scope_coverage(user_message) is True


def test_narrow_question_does_not_require_complete_scope_coverage() -> None:
    assert (
        request_requires_complete_scope_coverage(
            "According to my notes, when does Project Aurora launch?"
        )
        is False
    )


def test_evidence_selection_rejects_ids_outside_current_page() -> None:
    constraints = EvidenceSelectionConstraints(
        allowed_note_ids=frozenset({"note-a", "note-b"}),
    )

    with bind_evidence_selection_constraints(constraints):
        with pytest.raises(ValidationError, match="current page"):
            EvidenceSelection.model_validate(
                {
                    "relevant_note_ids": ["invented-note"],
                    "reason": "The invented note appears relevant.",
                }
            )


def test_evidence_selection_accepts_empty_selection() -> None:
    constraints = EvidenceSelectionConstraints(
        allowed_note_ids=frozenset({"note-a"}),
    )

    with bind_evidence_selection_constraints(constraints):
        selection = EvidenceSelection.model_validate(
            {
                "relevant_note_ids": [],
                "reason": "No candidate directly answers the current question.",
            }
        )

    assert selection.relevant_note_ids == []
