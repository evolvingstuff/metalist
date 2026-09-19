"""Bounded parallel evaluation with shared-prefix warm-up and unchanged requests."""

import asyncio
from collections import deque
from contextlib import aclosing, asynccontextmanager

from app.services.agent.inference import InferenceProviderError
from evals.runner import fingerprint, run_prepared_case


CONCURRENCY = 4


def prefix_key(*, model, thinking_level, messages, response_schema):
    prefix = []
    for message in messages:
        if message["role"] not in {"system", "developer"}:
            break
        prefix.append(message)
    return fingerprint({"model": model, "thinking_level": thinking_level,
        "prefix": prefix, "response_schema": response_schema})


def case_prefix(prepared):
    step = prepared.steps[0]
    return prefix_key(model=prepared.model, thinking_level=prepared.thinking_level,
        messages=[message.model_dump() for message in step.messages], response_schema=step.response_schema)


class CacheAwareAdapter:
    """The first successful call primes each prefix; subsequent calls can overlap.

    No extra warm-up inference, request rewriting, cache keys, or retention changes.
    Provider cache hits are measured separately; a successful call cannot guarantee one.
    """

    def __init__(self, *, adapter, concurrency):
        if type(concurrency) is not int or concurrency < 1:
            raise ValueError("Concurrency must be a positive integer")
        self._adapter = adapter
        self._slots = asyncio.Semaphore(concurrency)
        self._prefix_locks = {}
        self._primed = set()

    @asynccontextmanager
    async def _request_slot(self, key):
        if key not in self._prefix_locks:
            self._prefix_locks[key] = asyncio.Lock()
        lock = self._prefix_locks[key]
        owns_lock = False
        try:
            if key not in self._primed:
                await lock.acquire()
                owns_lock = True
                if key in self._primed:
                    lock.release()
                    owns_lock = False
            async with self._slots:
                yield
                self._primed.add(key)
        finally:
            if owns_lock:
                lock.release()

    async def infer_structured(self, **arguments):
        key = prefix_key(model=arguments["model"], thinking_level=arguments["thinking_level"],
            messages=arguments["messages"], response_schema=arguments["response_model"].model_json_schema())
        async with self._request_slot(key):
            return await self._adapter.infer_structured(**arguments)

    async def stream_text(self, **arguments):
        key = prefix_key(model=arguments["model"], thinking_level=arguments["thinking_level"],
            messages=arguments["messages"], response_schema={})
        async with self._request_slot(key):
            finished = False
            async with aclosing(self._adapter.stream_text(**arguments)) as stream:
                async for event in stream:
                    if event["type"] == "done":
                        finished = True
                    yield event
            if not finished:
                raise InferenceProviderError("Missing completed text output")


async def run_cases(cases, *, prepared_cases, adapter, judge, concurrency, repetitions,
                    on_repetition, on_case):
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("Concurrency must be a positive integer")
    assert len(cases) == len(prepared_cases) and cases
    adapter = CacheAwareAdapter(adapter=adapter, concurrency=concurrency)
    queue = deque(sorted(range(len(cases)), key=lambda index: case_prefix(prepared_cases[index])))
    reports = {}

    async def worker():
        while queue:
            index = queue.popleft()
            report = await run_prepared_case(cases[index], prepared=prepared_cases[index],
                adapter=adapter, judge=judge, repetitions=repetitions,
                on_repetition=lambda outcome: on_repetition(index, outcome))
            reports[index] = report
            on_case(index, report)

    workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(cases)))]
    try:
        await asyncio.gather(*workers)
    finally:
        # Cancel siblings on a programming error or interruption; never leave paid calls running.
        for task in workers:
            if not task.done():
                task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
    assert len(reports) == len(cases)
    return [reports[index] for index in range(len(cases))]
