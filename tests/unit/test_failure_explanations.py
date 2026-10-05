import pytest

from app.services.agent.actions import ContextualWebActionEnvelope
from app.services.agent.actions import ScopedRouteEnvelope
from app.services.agent.failure_explanations import FailureSetup
from app.services.agent.failure_explanations import explain_structured_failure
from app.services.agent.help_catalog import MetaListHelpResponse
from app.services.agent.inference import InferenceAttempt


_SETUP = FailureSetup(model="gpt-5.6-terra", thinking_level="medium", web_mode="none")


def _cut_off_attempt(*, limit: int, reasoning: int, content: str) -> InferenceAttempt:
    return InferenceAttempt(
        request={"max_completion_tokens": limit, "reasoning_effort": "medium"},
        response={
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "length"}],
            "usage": {"completion_tokens": limit, "completion_tokens_details": {"reasoning_tokens": reasoning}},
        },
        error="IncompleteOutputException: The output is incomplete due to a max_tokens length limit.",
        duration_ms=4_000.0,
        validation_errors=(),
    )


def _rejected_attempt(*, content: str, validation_errors: tuple[dict[str, str], ...]) -> InferenceAttempt:
    return InferenceAttempt(
        request={"max_completion_tokens": 512, "reasoning_effort": "medium"},
        response={
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 120, "completion_tokens_details": {"reasoning_tokens": 64}},
        },
        error="ValidationError: 1 validation error for ScopedRouteEnvelope",
        duration_ms=1_500.0,
        validation_errors=validation_errors,
    )


def test_a_routing_step_cut_off_by_thinking_is_explained_in_plain_words() -> None:
    message = explain_structured_failure(
        response_model=ScopedRouteEnvelope,
        attempts=[
            _cut_off_attempt(limit=512, reasoning=512, content=""),
            _cut_off_attempt(limit=512, reasoning=498, content='{"kind":"metal'),
        ],
        setup=_SETUP,
    )

    # Which step failed, what happened on each attempt, the setup, and what to try.
    assert "deciding how to handle your request" in message
    assert "Attempt 1: the reply was cut off at the 512-token output limit; all 512 tokens went to thinking, so no answer was written." in message
    assert "Attempt 2: the reply was cut off at the 512-token output limit after 498 tokens of thinking, before the answer was complete." in message
    assert "Setup: gpt-5.6-terra, Medium thinking, web access off." in message
    assert "lower thinking level" in message
    # The message stands on its own; Agent Debug is only for raw details.
    assert "Agent Debug" in message
    assert not message.startswith("Open Agent Debug")


def test_a_rejected_route_shows_what_the_model_chose_and_which_rule_it_broke() -> None:
    message = explain_structured_failure(
        response_model=ScopedRouteEnvelope,
        attempts=[
            _rejected_attempt(
                content='{"kind":"respond","help_topics":["data"],"reason":"Needs the GitHub changelog"}',
                validation_errors=({"field": "", "kind": "value_error",
                                    "problem": "Only metalist_help requires nonempty help_topics", "value": ""},),
            ),
            _rejected_attempt(
                content='{"kind":"metalist_help","help_topics":["release_notes"],"reason":"Product question"}',
                validation_errors=({"field": "help_topics.0", "kind": "literal_error",
                                    "problem": "Input should be 'notes', 'search', 'tags'", "value": "release_notes"},),
            ),
        ],
        setup=_SETUP,
    )

    assert ("Attempt 1: the answer did not match the required format: Only metalist_help requires nonempty help_topics. "
            "It chose: kind=respond, help_topics=[data].") in message
    assert ("Attempt 2: the answer did not match the required format: help_topics.0 was 'release_notes', "
            "which is not one of the allowed values. It chose: kind=metalist_help, help_topics=[release_notes].") in message
    assert "rephrase" in message


def test_other_steps_and_setups_are_named() -> None:
    web_message = explain_structured_failure(
        response_model=ContextualWebActionEnvelope,
        attempts=[_rejected_attempt(
            content='{"kind":"open_web_pages","urls":[],"reason":"Look it up"}',
            validation_errors=({"field": "", "kind": "value_error",
                                "problem": "open_web_pages requires at least one URL", "value": ""},),
        )],
        setup=FailureSetup(model="gpt-5.6-sol", thinking_level="high", web_mode="full"),
    )
    assert "choosing which web pages to open" in web_message
    assert "Setup: gpt-5.6-sol, High thinking, full web access." in web_message

    help_message = explain_structured_failure(
        response_model=MetaListHelpResponse,
        attempts=[InferenceAttempt(
            request={"max_completion_tokens": 8192},
            response={"choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]},
            error="ValueError: Instructor stream returned no structured output",
            duration_ms=900.0,
            validation_errors=(),
        )],
        setup=FailureSetup(model="gpt-5.6-luna", thinking_level="off", web_mode="contextual"),
    )
    assert "answering from MetaList's built-in help" in help_message
    assert "Attempt 1: the reply was empty." in help_message
    assert "Setup: gpt-5.6-luna, thinking off, contextual web access." in help_message


def test_an_unknown_step_fails_loudly() -> None:
    class UnknownStep:
        pass

    # An unknown step must not get a made-up description.
    with pytest.raises(KeyError):
        explain_structured_failure(response_model=UnknownStep, attempts=[], setup=_SETUP)
