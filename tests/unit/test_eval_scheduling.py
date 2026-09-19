import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.actions import ScopedRouteEnvelope
from app.services.agent.history import record_structured_call
from app.services.agent.inference import InferenceProviderError
from app.services.agent.openai_cost_tracking import OpenAITokenUsage
from evals import scheduling
from evals import __main__ as cli
from evals.models import RegressionCase
from evals.runner import prepare_case
from evals.scheduling import CacheAwareAdapter, prefix_key, run_cases


ROOT = Path(__file__).resolve().parents[2]


def arguments(prefix, suffix):
    return {"model": "gpt-5.6-luna", "thinking_level": "off",
        "messages": [{"role": "system", "content": prefix}, {"role": "user", "content": suffix}],
        "response_model": ScopedRouteEnvelope}


def test_prefix_grouping_tracks_instructions_schema_and_model_but_not_scenario_suffix():
    args = arguments("shared instructions", "request A")
    args["response_schema"] = args.pop("response_model").model_json_schema()
    key = prefix_key(**args)
    args["messages"][-1]["content"] = "request B"
    assert prefix_key(**args) == key
    for field, value in [("model", "gpt-5.6-sol"), ("thinking_level", "low"), ("response_schema", {})]:
        assert prefix_key(**{**args, field: value}) != key
    args["messages"][0]["content"] = "different instructions"
    assert prefix_key(**args) != key


def test_cold_prefix_is_serial_then_parallel_with_unchanged_requests():
    async def check():
        started, completed = [], []
        release_first, later_overlap = asyncio.Event(), asyncio.Event()
        active = peak = 0
        class Adapter:
            async def infer_structured(self, **kwargs):
                nonlocal active, peak
                started.append(kwargs)
                active += 1
                peak = max(peak, active)
                if len(started) == 1:
                    await release_first.wait()
                elif active == 2:
                    later_overlap.set()
                else:
                    await later_overlap.wait()
                completed.append(kwargs)
                active -= 1
                return "response"
        adapter = CacheAwareAdapter(adapter=Adapter(), concurrency=2)
        requests = [arguments("same prefix", str(i)) for i in range(3)]
        tasks = [asyncio.create_task(adapter.infer_structured(**request)) for request in requests]
        await asyncio.sleep(0)
        assert started == requests[:1]
        release_first.set()
        assert await asyncio.wait_for(asyncio.gather(*tasks), 1) == ["response"] * 3
        assert started == requests and completed[0] == requests[0]
        assert peak == 2
    asyncio.run(check())


def test_different_cold_prefixes_overlap_but_respect_global_limit():
    async def check():
        active = peak = 0
        first_two = asyncio.Event()
        class Adapter:
            async def infer_structured(self, **kwargs):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                if active == 2:
                    first_two.set()
                await first_two.wait()
                await asyncio.sleep(0)
                active -= 1
        adapter = CacheAwareAdapter(adapter=Adapter(), concurrency=2)
        await asyncio.wait_for(asyncio.gather(*(adapter.infer_structured(**arguments(str(i), "request"))
                                               for i in range(6))), 1)
        assert peak == 2
    asyncio.run(check())


def test_failed_priming_call_is_counted_and_does_not_block_waiters():
    async def check():
        calls = 0
        class Adapter:
            async def infer_structured(self, **kwargs):
                nonlocal calls
                calls += 1
                await asyncio.sleep(0)
                if calls == 1:
                    raise InferenceProviderError("offline")
                return "ok"
        adapter = CacheAwareAdapter(adapter=Adapter(), concurrency=2)
        results = await asyncio.wait_for(asyncio.gather(*(adapter.infer_structured(**arguments("shared", str(i)))
            for i in range(3)), return_exceptions=True), 1)
        assert isinstance(results[0], InferenceProviderError)
        assert results[1:] == ["ok", "ok"]
        assert calls == 3
    asyncio.run(check())


def test_cancelled_stream_releases_prefix_lock_and_closes_provider():
    async def check():
        entered, closed = asyncio.Event(), asyncio.Event()
        calls = 0
        class Adapter:
            async def stream_text(self, **kwargs):
                nonlocal calls
                calls += 1
                try:
                    if calls == 1:
                        entered.set()
                        await asyncio.Event().wait()
                    yield {"type": "content_delta", "text": "ok"}
                    yield {"type": "done"}
                finally:
                    closed.set()
        adapter = CacheAwareAdapter(adapter=Adapter(), concurrency=2)
        args = arguments("shared", "request")
        del args["response_model"]
        async def consume():
            return [event async for event in adapter.stream_text(**args)]
        first = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert closed.is_set()
        assert (await asyncio.wait_for(consume(), 1))[-1]["type"] == "done"
        assert calls == 2
    asyncio.run(check())


def fixture_cases():
    source = RegressionCase.model_validate_json((ROOT / "evals/cases/actions/hello.json").read_text())
    cases = []
    for index in range(4):
        case = source.model_copy(deep=True)
        case.id = f"case-{index}"
        case.steps[0].conversation[-1].content = f"request-{index}"
        cases.append(case)
    return cases


def test_parallel_suite_keeps_trials_and_history_isolated_in_input_order():
    calls = []
    class Adapter:
        @record_structured_call
        async def infer_structured(self, **kwargs):
            payload = json.loads(kwargs["messages"][-1]["content"].split("\n", 1)[1])
            request = payload["current_user_request"]
            calls.append(request)
            await asyncio.sleep(0)
            return SimpleNamespace(content=json.dumps({"kind": "respond", "reason": request}), thinking="", usage={})
    cases = fixture_cases()
    outcomes, finished = [], []
    reports = asyncio.run(run_cases(cases, prepared_cases=[prepare_case(c) for c in cases],
        adapter=Adapter(), judge=None, concurrency=3, repetitions=5,
        on_repetition=lambda index, outcome: outcomes.append((index, outcome)),
        on_case=lambda index, report: finished.append(index)))
    assert [r["case_id"] for r in reports] == [c.id for c in cases]
    assert len(outcomes) == len(calls) == 20
    assert sorted(finished) == list(range(4))
    for index, report in enumerate(reports):
        assert report["counts"] == {"correct": 5, "incorrect": 0, "error": 0}
        assert [o["repetition"] for o in report["outcomes"]] == [1, 2, 3, 4, 5]
        for outcome in report["outcomes"]:
            assert json.loads(outcome["outputs"][0])["reason"] == f"request-{index}"
            assert len(outcome["pairs"]) == 1
            captured = outcome["pairs"][0][0]["invocation"]["messages"]
            assert json.loads(captured[-1]["content"].split("\n", 1)[1])["current_user_request"] == f"request-{index}"


def test_internal_failure_cancels_other_workers(monkeypatch):
    async def check():
        overlap, cancelled = asyncio.Event(), asyncio.Event()
        started = 0
        async def broken(case, **kwargs):
            nonlocal started
            started += 1
            if started == 1:
                await overlap.wait()
                raise AssertionError("programming bug")
            overlap.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        monkeypatch.setattr(scheduling, "run_prepared_case", broken)
        cases = fixture_cases()
        with pytest.raises(AssertionError, match="programming bug"):
            await asyncio.wait_for(run_cases(cases, prepared_cases=[prepare_case(c) for c in cases],
                adapter=object(), judge=None, concurrency=2, repetitions=5,
                on_repetition=lambda *args: None, on_case=lambda *args: None), 1)
        assert cancelled.is_set() and started == 2
    asyncio.run(check())


def test_cli_defaults_save_all_trials_and_actual_cached_usage(tmp_path, monkeypatch):
    class Adapter:
        def __init__(self, *, api_key, cost_tracker):
            self.costs = cost_tracker

        async def infer_structured(self, **kwargs):
            await asyncio.sleep(0)
            self.costs.record(model=kwargs["model"], usage=OpenAITokenUsage(
                prompt_tokens=2000, output_tokens=10, total_tokens=2010, cached_input_tokens=1500, cache_write_tokens=0))
            return SimpleNamespace(content='{"kind":"respond","reason":"fixture"}')

    paths = []
    for case in fixture_cases():
        path = tmp_path / f"{case.id}.json"
        path.write_text(case.model_dump_json())
        paths.append(str(path))
    output = tmp_path / "report"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "OpenAIInferenceAdapter", Adapter)
    monkeypatch.setattr(sys, "argv", ["evals", "run", *paths, "--live", "--output", str(output)])
    cli.main()
    report = json.loads((output / "report.json").read_text())
    assert report["concurrency"] == 4
    assert report["token_usage"] == {"cached_input_tokens": 30000, "uncached_input_tokens": 10000,
                                    "cache_write_tokens": 0, "output_tokens": 200}
    for index, case in enumerate(report["cases"]):
        assert case["repetitions"] == 5 and case["counts"]["correct"] == 5
        assert len(list((output / str(index)).glob("0*.json"))) == 5


def test_serial_option_limits_unrelated_prefixes_to_one_request():
    async def check():
        active = peak = 0
        class Adapter:
            async def infer_structured(self, **kwargs):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0)
                active -= 1
        adapter = CacheAwareAdapter(adapter=Adapter(), concurrency=1)
        await asyncio.gather(*(adapter.infer_structured(**arguments(str(i), "request")) for i in range(3)))
        assert peak == 1
    asyncio.run(check())
