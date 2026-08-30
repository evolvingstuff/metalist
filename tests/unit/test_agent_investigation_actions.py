from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.services.agent.actions import InvestigationStep
from app.services.agent.actions import InvestigationStepConstraints
from app.services.agent.actions import EvidenceSelection
from app.services.agent.actions import EvidenceSelectionConstraints
from app.services.agent.actions import EvidenceSelectionWithoutRationale
from app.services.agent.actions import ScopedRouteConstraints
from app.services.agent.actions import ScopedRouteEnvelope
from app.services.agent.actions import RankedNote
from app.services.agent.actions import WorkingSummary
from app.services.agent.actions import bind_investigation_step_constraints
from app.services.agent.actions import bind_evidence_selection_constraints
from app.services.agent.actions import bind_scoped_route_constraints
from app.services.agent.actions import request_explicitly_requires_saved_notes
from app.services.agent.actions import request_requires_complete_scope_coverage
from app.services.agent.actions import validate_working_summary_for_observed_sources


def _summary() -> WorkingSummary:
    return WorkingSummary(
        ranked_notes=[RankedNote(note_id="note-a", importance=90)],
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
            "evidence_sufficiency": "insufficient",
        }
    )

    step = InvestigationStep.model_validate(payload)

    assert step.facet_page == 2
    assert step.tag_expression == ""


def test_investigation_step_wire_schema_omits_ollama_incompatible_max_length() -> None:
    serialized_schema = json.dumps(InvestigationStep.model_json_schema())

    assert '"maxLength"' not in serialized_schema


def test_working_summary_contains_only_ranked_note_ids() -> None:
    properties = WorkingSummary.model_json_schema()["properties"]

    assert set(properties) == {"ranked_notes"}


def test_working_summary_schema_programmatically_bounds_rolling_output() -> None:
    properties = WorkingSummary.model_json_schema()["properties"]

    assert properties["ranked_notes"]["maxItems"] == 64


def test_investigation_wire_schema_places_action_before_working_summary() -> None:
    property_names = list(InvestigationStep.model_json_schema()["properties"])

    assert property_names[0] == "action_kind"
    assert property_names[-1] == "working_summary"


@pytest.mark.parametrize("importance", (0, 101))
def test_ranked_note_importance_is_bounded(importance: int) -> None:
    with pytest.raises(ValidationError):
        RankedNote(note_id="note-a", importance=importance)


def test_working_summary_sorts_by_importance_and_rejects_duplicate_ids() -> None:
    summary = WorkingSummary(
        ranked_notes=[
            RankedNote(note_id="note-low", importance=10),
            RankedNote(note_id="note-high", importance=95),
        ]
    )

    assert [ranked.note_id for ranked in summary.ranked_notes] == [
        "note-high",
        "note-low",
    ]
    with pytest.raises(ValidationError, match="must be unique"):
        WorkingSummary(
            ranked_notes=[
                RankedNote(note_id="note-a", importance=90),
                RankedNote(note_id="note-a", importance=80),
            ]
        )


def test_working_summary_selects_highest_scored_32_notes() -> None:
    summary = WorkingSummary(
        ranked_notes=[
            RankedNote(note_id=f"note-{index}", importance=index)
            for index in range(1, 65)
        ]
    )

    selected = summary.top_source_ids(maximum=32)

    assert len(selected) == 32
    assert selected[0] == "note-64"
    assert selected[-1] == "note-33"


def test_working_summary_merges_pages_and_retains_highest_scored_64_notes() -> None:
    first_page = WorkingSummary(
        ranked_notes=[
            RankedNote(note_id=f"first-{index}", importance=index)
            for index in range(1, 41)
        ]
    )
    second_page = WorkingSummary(
        ranked_notes=[
            RankedNote(note_id=f"second-{index}", importance=index + 40)
            for index in range(1, 41)
        ]
    )

    merged = first_page.merged_with(page_summary=second_page, maximum=64)

    assert len(merged.ranked_notes) == 64
    assert merged.ranked_notes[0].note_id == "second-40"
    assert merged.ranked_notes[-1].importance == 17
    assert "first-16" not in merged.referenced_source_ids()


def test_investigation_step_schema_explains_inactive_action_sentinels() -> None:
    properties = InvestigationStep.model_json_schema()["properties"]

    assert properties["facet_page"]["description"].endswith("emit 0 otherwise.")
    assert properties["source_ids"]["description"].endswith(
        "emit an empty array otherwise."
    )


def test_investigation_step_has_no_redundant_answer_source_ids() -> None:
    properties = InvestigationStep.model_json_schema()["properties"]

    assert properties["source_ids"]["maxItems"] == 12
    assert "answer_source_ids" not in properties


def test_investigation_step_still_validates_string_length_off_wire() -> None:
    payload = _payload()
    payload["reason"] = "x" * 513

    with pytest.raises(ValidationError, match="at most 512 characters"):
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
    summary = WorkingSummary(
        ranked_notes=[
            RankedNote(note_id=f"long-note-id-{index}-" + ("x" * 40), importance=50)
            for index in range(40)
        ]
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


def test_evidence_selection_without_rationale_rejects_reason_field() -> None:
    constraints = EvidenceSelectionConstraints(
        allowed_note_ids=frozenset({"note-a"}),
    )

    with bind_evidence_selection_constraints(constraints):
        selection = EvidenceSelectionWithoutRationale.model_validate(
            {"relevant_note_ids": []}
        )
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            EvidenceSelectionWithoutRationale.model_validate(
                {
                    "relevant_note_ids": [],
                    "reason": "This field is forbidden when diagnostics are hidden.",
                }
            )

    assert selection.model_dump() == {"relevant_note_ids": []}
