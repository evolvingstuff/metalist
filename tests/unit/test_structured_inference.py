import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.services.agent.judging import OutputJudgment
from app.services.agent.staged_summary import SummaryBatchResult
from app.services.agent.staged_summary import SummaryFindingsResult
from app.services.agent.structured_inference import _InstructorTraceCapture
from app.services.agent.structured_inference import _response_finish_reason, _structured_max_output_tokens
from app.services.agent.tagging import TagBatchResult


def test_structured_output_limits_are_bounded_by_response_type() -> None:
    for response_model in (SummaryBatchResult, SummaryFindingsResult, TagBatchResult, OutputJudgment):
        assert _structured_max_output_tokens(response_model) == 8_192

    class UnknownReply(SummaryFindingsResult):
        pass

    with pytest.raises(RuntimeError, match="limit missing"):
        _structured_max_output_tokens(UnknownReply)


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
        SummaryBatchResult.model_validate({"covered_root_ids": [""], "findings": []})
    capture.record_parse_error(rejected.value)

    attempt = capture.freeze()[0]

    assert attempt.validation_errors == (
        {
            "field": "covered_root_ids",
            "kind": "value_error",
            "problem": rejected.value.errors()[0]["msg"],
            # Only simple values are shown; a list is described by its rule alone.
            "value": "",
        },
    )


def test_structured_steps_have_room_for_thinking_before_their_answer() -> None:
    # Reasoning tokens count against the output limit: at Medium or High
    # thinking, 512 tokens could be spent entirely on thinking.
    assert _structured_max_output_tokens(SummaryFindingsResult) >= 8_192
