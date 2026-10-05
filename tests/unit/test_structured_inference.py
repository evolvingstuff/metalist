import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.services.agent.actions import ScopedRouteEnvelope
from app.services.agent.structured_inference import _InstructorTraceCapture
from app.services.agent.actions import AgentRouteEnvelope
from app.services.agent.actions import ContextualWebActionEnvelope
from app.services.agent.actions import SearchQueryEnvelope
from app.services.agent.structured_inference import _response_finish_reason, _structured_max_output_tokens


def test_structured_output_limits_are_bounded_by_response_type() -> None:
    assert _structured_max_output_tokens(AgentRouteEnvelope) == 8_192
    assert _structured_max_output_tokens(SearchQueryEnvelope) == 8_192
    assert _structured_max_output_tokens(ContextualWebActionEnvelope) == 8_192


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


def test_a_rejected_attempt_keeps_the_broken_rules_for_the_error_message() -> None:
    capture = _InstructorTraceCapture(on_progress=lambda progress: None)
    capture.record_request(messages=[], max_completion_tokens=8_192)
    asyncio.run(capture.record_wire_request(httpx.Request(
        "POST", "https://api.openai.com/v1/chat/completions", json={"model": "gpt-5.6-terra"},
    )))
    with pytest.raises(ValidationError) as rejected:
        ScopedRouteEnvelope.model_validate(
            {"kind": "metalist_help", "help_topics": ["release_notes"], "reason": "Product question"}
        )
    capture.record_parse_error(rejected.value)

    attempt = capture.freeze()[0]

    assert attempt.validation_errors == (
        {
            "field": "help_topics.0",
            "kind": "literal_error",
            "problem": rejected.value.errors()[0]["msg"],
            "value": "release_notes",
        },
    )


def test_routing_has_room_for_thinking_before_its_short_answer() -> None:
    # Reasoning tokens count against the output limit: at Medium or High
    # thinking, 512 tokens could be spent entirely on thinking.
    assert _structured_max_output_tokens(ScopedRouteEnvelope) >= 8_192
    assert _structured_max_output_tokens(AgentRouteEnvelope) >= 8_192
