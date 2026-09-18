import pytest

from pydantic import ValidationError

from app.services.agent.actions import ScopedRouteEnvelope


@pytest.mark.parametrize("kind", ["respond", "investigate_current_scope", "tag_proposals"])
def test_route_schema_accepts_each_supported_model_choice(kind: str) -> None:
    route = ScopedRouteEnvelope.model_validate({"kind": kind, "reason": "Model decision.", "help_topics": []})
    assert route.kind == kind


@pytest.mark.parametrize("payload", [
    {"kind": "delete_notes", "reason": "Unsupported action."},
    {"kind": "respond"},
    {"kind": "respond", "reason": " "},
    {"kind": "respond", "reason": "Answer.", "extra": True},
])
def test_route_schema_still_rejects_malformed_actions(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ScopedRouteEnvelope.model_validate(payload)
