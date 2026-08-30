import pytest

from app.services.agent.actions import ScopedRouteConstraints
from app.services.agent.actions import ScopedRouteEnvelope
from app.services.agent.actions import bind_scoped_route_constraints
from app.services.agent.actions import request_explicitly_requires_saved_notes


@pytest.mark.parametrize(
    "message",
    [
        "please summarize my notes about testosterone",
        "search my saved notes for foo",
        "review all of our notes about this",
    ],
)
def test_saved_note_requests_are_detected(message: str) -> None:
    assert request_explicitly_requires_saved_notes(message) is True


def test_explicit_saved_note_request_requires_scoped_investigation() -> None:
    constraints = ScopedRouteConstraints(explicit_saved_notes_request=True)
    with bind_scoped_route_constraints(constraints):
        with pytest.raises(ValueError, match="investigate_current_scope"):
            ScopedRouteEnvelope.model_validate({
                "kind": "respond",
                "reason": "Answer directly.",
            })
        route = ScopedRouteEnvelope.model_validate({
            "kind": "investigate_current_scope",
            "reason": "The request requires saved-note evidence.",
        })
    assert route.kind == "investigate_current_scope"


def test_saved_note_exclusion_allows_direct_response() -> None:
    message = "answer without using my saved notes"
    assert request_explicitly_requires_saved_notes(message) is False
