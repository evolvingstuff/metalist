from app.services.agent.actions import AgentRouteEnvelope
from app.services.agent.actions import ContextualWebActionEnvelope
from app.services.agent.actions import SearchQueryEnvelope
from app.services.agent.structured_inference import _response_finish_reason, _structured_max_output_tokens


def test_structured_output_limits_are_bounded_by_response_type() -> None:
    assert _structured_max_output_tokens(AgentRouteEnvelope) == 512
    assert _structured_max_output_tokens(SearchQueryEnvelope) == 1_024
    assert _structured_max_output_tokens(ContextualWebActionEnvelope) == 4_096


def test_structured_retry_can_identify_output_limit_truncation() -> None:
    response = {
        "choices": [
            {
                "message": {"role": "assistant", "content": '{"partial":'},
                "finish_reason": "length",
            }
        ]
    }

    assert _response_finish_reason(response) == "length"
