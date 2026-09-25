from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.services.agent.actions import ContextualWebActionEnvelope
from app.services.agent.actions import OpenWebPagesAction
from app.services.agent.actions import RespondAction
from app.services.agent.context import AgentContextBuilder
from app.services.agent.web_settings import AgentWebSettings


def test_full_web_prompt_requires_page_attempt_for_current_public_fact() -> None:
    builder = AgentContextBuilder()
    messages = builder.append_web_access_context(
        messages=[{"role": "user", "content": "what is the price of QQQ?"}],
        settings=AgentWebSettings(mode="full"),
        available_urls=(),
    )
    messages = builder.append_web_action_request(
        messages=messages,
        settings=AgentWebSettings(mode="full"),
    )
    access_payload = json.loads(messages[-2]["content"].split("\n", 1)[1])
    action_payload = json.loads(messages[-1]["content"].split("\n", 1)[1])

    assert "google search result pages" in access_payload["explanation"].lower()
    instruction = action_payload["instruction"].lower()
    assert "must choose open_web_pages before respond" in instruction
    assert "https://www.google.com/search?q=" in instruction
    assert "https://www.google.com/finance/quote/qqq:nasdaq?hl=en" in instruction
    assert "never repeat a url" in instruction
    assert "do not respond that live data is unavailable" in instruction


def test_contextual_web_action_supports_batched_duplicate_urls() -> None:
    action = ContextualWebActionEnvelope(
        kind="open_web_pages",
        urls=["https://example.com/a", "https://example.com/a"],
        reason="Read both requested entries and let the application deduplicate.",
    ).to_action()
    assert action == OpenWebPagesAction(
        kind="open_web_pages",
        urls=["https://example.com/a", "https://example.com/a"],
        rationale="Read both requested entries and let the application deduplicate.",
    )


def test_contextual_web_action_respond_requires_empty_urls() -> None:
    action = ContextualWebActionEnvelope(
        kind="respond",
        urls=[],
        reason="No page is needed.",
    ).to_action()
    assert action == RespondAction(kind="respond", basis="No page is needed.")


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "open_web_pages", "urls": [], "reason": "Missing URLs"},
        {"kind": "respond", "urls": ["https://example.com"], "reason": "Bad"},
        {"kind": "open_web_pages", "urls": ["  "], "reason": "Bad"},
        {"kind": "open_web_pages", "urls": ["https://e.test"] * 9, "reason": "Too many"},
    ],
)
def test_contextual_web_action_rejects_invalid_shapes(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ContextualWebActionEnvelope.model_validate(payload)
