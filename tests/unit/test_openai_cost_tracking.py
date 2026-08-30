from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.agent.openai_cost_tracking import OpenAICostTracker
from app.services.agent.openai_cost_tracking import OpenAITokenUsage
from app.services.agent.openai_cost_tracking import estimate_openai_request_cost


def test_openai_request_cost_prices_all_token_categories() -> None:
    usage = OpenAITokenUsage(
        prompt_tokens=1_000,
        cached_input_tokens=200,
        cache_write_tokens=100,
        output_tokens=50,
        total_tokens=1_050,
    )

    cost = estimate_openai_request_cost(model="gpt-5.6-sol", usage=usage)

    assert usage.uncached_input_tokens == 700
    assert cost == Decimal("0.00438")


@pytest.mark.parametrize(
    ("model", "expected_cost"),
    [
        ("gpt-5.6-sol", Decimal("0.0438")),
        ("gpt-5.6-terra", Decimal("0.0229")),
        ("gpt-5.6-luna", Decimal("0.00229")),
    ],
)
def test_openai_request_cost_uses_supported_short_context_model_rates(
    model: str,
    expected_cost: Decimal,
) -> None:
    usage = OpenAITokenUsage(
        prompt_tokens=10_000,
        cached_input_tokens=2_000,
        cache_write_tokens=1_000,
        output_tokens=500,
        total_tokens=10_500,
    )

    assert estimate_openai_request_cost(model=model, usage=usage) == expected_cost


def test_openai_request_cost_switches_to_long_context_rates_above_threshold() -> None:
    boundary_usage = OpenAITokenUsage(
        prompt_tokens=272_000,
        cached_input_tokens=0,
        cache_write_tokens=0,
        output_tokens=1_000,
        total_tokens=273_000,
    )
    long_usage = OpenAITokenUsage(
        prompt_tokens=272_001,
        cached_input_tokens=0,
        cache_write_tokens=0,
        output_tokens=1_000,
        total_tokens=273_001,
    )

    boundary_cost = estimate_openai_request_cost(
        model="gpt-5.6-sol",
        usage=boundary_usage,
    )
    long_cost = estimate_openai_request_cost(
        model="gpt-5.6-sol",
        usage=long_usage,
    )

    assert boundary_cost == Decimal("1.108")
    assert long_cost == Decimal("2.206008")


def test_openai_cost_tracker_accumulates_and_resets_in_memory() -> None:
    tracker = OpenAICostTracker()
    usage = OpenAITokenUsage(
        prompt_tokens=1_000,
        cached_input_tokens=200,
        cache_write_tokens=100,
        output_tokens=50,
        total_tokens=1_050,
    )

    tracker.record(model="gpt-5.6-sol", usage=usage)
    tracker.record(model="gpt-5.6-sol", usage=usage)

    snapshot = tracker.snapshot()
    assert snapshot.estimated_cost_usd == Decimal("0.00876")
    assert snapshot.uncached_input_tokens == 1_400
    assert snapshot.cached_input_tokens == 400
    assert snapshot.cache_write_tokens == 200
    assert snapshot.output_tokens == 100

    tracker.reset()

    assert tracker.snapshot().estimated_cost_usd == Decimal(0)
    assert tracker.snapshot().uncached_input_tokens == 0
    assert tracker.snapshot().cached_input_tokens == 0
    assert tracker.snapshot().cache_write_tokens == 0
    assert tracker.snapshot().output_tokens == 0


def test_openai_usage_rejects_overlapping_cache_categories() -> None:
    with pytest.raises(
        ValueError,
        match="cached and cache-write tokens exceed prompt tokens",
    ):
        OpenAITokenUsage(
            prompt_tokens=100,
            cached_input_tokens=80,
            cache_write_tokens=30,
            output_tokens=5,
            total_tokens=105,
        )
