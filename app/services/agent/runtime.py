"""Explicit application-owned execution loop for read-only PKMS agents."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from app.services.agent.actions import AgentAction
from app.services.agent.actions import AgentActionEnvelope
from app.services.agent.actions import ReadNotesAction
from app.services.agent.actions import RespondAction
from app.services.agent.actions import SearchNotesAction
from app.services.agent.actions import parse_agent_action_json
from app.services.agent.context import AgentContextBuilder
from app.services.agent.inference import InferenceAdapter
from app.services.agent.inference import InferenceAttempt
from app.services.agent.inference import InferenceResponse
from app.services.agent.inference import StructuredInferenceProgress
from app.services.agent.inference import StructuredInferenceError
from app.services.agent.model_policy import InferencePurpose
from app.services.agent.model_policy import SingleModelPolicy
from app.services.agent.permissions import AgentPermissionPolicy
from app.services.agent.prompt_settings import AgentPromptSet
from app.services.agent.tools import ReadOnlyAgentToolRegistry
from app.services.agent.trace import AgentTraceStore


_MAX_ACTION_STEPS = 8


class AgentExecutionError(Exception):
    """Expected failure caused by provider/model output during an agent run."""


@dataclass(frozen=True, slots=True)
class _RunContext:
    session_key: str
    run_id: str
    base_url: str
    selected_model: str
    thinking_level: str
    prompts: AgentPromptSet


@dataclass(slots=True)
class _FinalStreamState:
    thinking: str
    content: str
    usage: dict[str, int]
    did_finish: bool


class AgentRuntime:
    def __init__(
        self,
        *,
        context_builder: AgentContextBuilder,
        inference: InferenceAdapter,
        model_policy: SingleModelPolicy,
        permission_policy: AgentPermissionPolicy,
        tool_registry: ReadOnlyAgentToolRegistry,
        trace_store: AgentTraceStore,
    ) -> None:
        self._context_builder = context_builder
        self._inference = inference
        self._model_policy = model_policy
        self._permission_policy = permission_policy
        self._tool_registry = tool_registry
        self._trace_store = trace_store

    async def stream(
        self,
        *,
        session_key: str,
        base_url: str,
        selected_model: str,
        thinking_level: str,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
    ) -> AsyncIterator[dict[str, object]]:
        run, messages = self._start_run(
            session_key=session_key,
            base_url=base_url,
            selected_model=selected_model,
            thinking_level=thinking_level,
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        # lint: allow-PY001 rationale="record every run failure in the session trace before re-raising"
        try:
            async for event in self._run_steps(run=run, messages=messages):
                yield event
        # lint: allow-PY001 rationale="record interrupted external inference before preserving cancellation"
        except asyncio.CancelledError:
            self._record_failure(
                session_key=session_key,
                run_id=run.run_id,
                error="Agent run interrupted",
            )
            raise
        # lint: allow-PY001 rationale="record internal failure details and immediately re-raise"
        except Exception as exc:
            self._record_failure(
                session_key=session_key,
                run_id=run.run_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _start_run(
        self,
        *,
        session_key: str,
        base_url: str,
        selected_model: str,
        thinking_level: str,
        canonical_messages: list[dict[str, str]],
        prompts: AgentPromptSet,
    ) -> tuple[_RunContext, list[dict[str, str]]]:
        messages = self._context_builder.build_initial_messages(
            canonical_messages=canonical_messages,
            prompts=prompts,
        )
        run_id = self._trace_store.start_run(
            session_key=session_key,
            model=selected_model,
            user_message=canonical_messages[-1]["content"],
        )
        run = _RunContext(
            session_key=session_key,
            run_id=run_id,
            base_url=base_url,
            selected_model=selected_model,
            thinking_level=thinking_level,
            prompts=prompts,
        )
        return run, messages

    async def _run_steps(
        self,
        *,
        run: _RunContext,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, object]]:
        current_messages = messages
        for _ in range(_MAX_ACTION_STEPS):
            yield self._status_event("planning", "started", "Preparing action selection")
            progress_queue: asyncio.Queue[StructuredInferenceProgress] = asyncio.Queue()
            action_task = asyncio.create_task(
                self._select_action(
                    run=run,
                    messages=current_messages,
                    on_progress=lambda progress: self._publish_inference_progress(
                        run=run,
                        progress_queue=progress_queue,
                        progress=progress,
                    ),
                )
            )
            async for progress in self._stream_progress_until_complete(
                progress_queue=progress_queue,
                action_task=action_task,
            ):
                yield self._progress_status_event(progress)
            action, current_messages = await action_task
            yield self._selected_action_status_event(action)
            if isinstance(action, RespondAction):
                async for event in self._stream_final_response(
                    run=run,
                    messages=current_messages,
                    action=action,
                ):
                    yield event
                return
            status_label = self._tool_status_label(action)
            yield self._status_event(action.kind, "started", status_label)
            current_messages = self._execute_tool(
                run=run,
                messages=current_messages,
                action=action,
            )
            yield self._status_event(action.kind, "completed", status_label)
        raise AgentExecutionError(f"Agent exceeded {_MAX_ACTION_STEPS} action steps")

    async def _select_action(
        self,
        *,
        run: _RunContext,
        messages: list[dict[str, str]],
        on_progress: Callable[[StructuredInferenceProgress], None],
    ) -> tuple[AgentAction, list[dict[str, str]]]:
        model = self._model_policy.for_stage(
            purpose=InferencePurpose.ACTION_SELECTION,
            selected_model=run.selected_model,
        )
        response = await self._request_action_inference(
            run=run,
            model=model,
            messages=messages,
            on_progress=on_progress,
        )
        action = parse_agent_action_json(response.content)
        self._record_structured_attempts(
            run=run,
            attempts=response.attempts,
            parsed=action.model_dump(),
        )
        self._record_action(run=run, action=action)
        return action, messages

    async def _request_action_inference(
        self,
        *,
        run: _RunContext,
        model: str,
        messages: list[dict[str, str]],
        on_progress: Callable[[StructuredInferenceProgress], None],
    ) -> InferenceResponse:
        # lint: allow-PY001 rationale="capture Instructor retry attempts before surfacing an external inference failure"
        try:
            return await self._inference.infer_structured(
                base_url=run.base_url,
                model=model,
                thinking_level=run.thinking_level,
                messages=messages,
                response_model=AgentActionEnvelope,
                on_progress=on_progress,
            )
        except StructuredInferenceError as exc:
            self._record_structured_attempts(
                run=run,
                attempts=exc.attempts,
                parsed={},
            )
            raise AgentExecutionError(str(exc)) from exc

    @staticmethod
    async def _stream_progress_until_complete(
        *,
        progress_queue: asyncio.Queue[StructuredInferenceProgress],
        action_task: asyncio.Task[tuple[AgentAction, list[dict[str, str]]]],
    ) -> AsyncIterator[StructuredInferenceProgress]:
        try:
            while not action_task.done():
                receive_task = asyncio.create_task(progress_queue.get())
                completed, _ = await asyncio.wait(
                    {action_task, receive_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if receive_task in completed:
                    yield receive_task.result()
                    continue
                receive_task.cancel()
                with suppress(asyncio.CancelledError):
                    await receive_task
            while not progress_queue.empty():
                yield progress_queue.get_nowait()
        finally:
            if not action_task.done():
                action_task.cancel()
                with suppress(asyncio.CancelledError):
                    await action_task

    def _record_action(
        self,
        *,
        run: _RunContext,
        action: AgentAction,
    ) -> None:
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="ACTION",
            label=f"Action: {action.kind}",
            detail={"action": action.model_dump()},
            duration_ms=0.0,
        )

    def _record_inference_progress(
        self,
        *,
        run: _RunContext,
        progress: StructuredInferenceProgress,
    ) -> None:
        event = self._progress_status_event(progress)
        if progress.phase == "attempt_started":
            self._record_wire_request(
                run=run,
                purpose=InferencePurpose.ACTION_SELECTION,
                attempt=progress.attempt,
                max_attempts=progress.max_attempts,
                wire_request=progress.wire_request,
            )
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="MODEL_STATUS",
            label=event["label"],
            detail={
                "phase": progress.phase,
                "attempt": progress.attempt,
                "max_attempts": progress.max_attempts,
                "failure_kind": progress.failure_kind,
                "error_type": progress.error_type,
                "error_message": progress.error_message,
            },
            duration_ms=progress.duration_ms,
        )

    def _publish_inference_progress(
        self,
        *,
        run: _RunContext,
        progress_queue: asyncio.Queue[StructuredInferenceProgress],
        progress: StructuredInferenceProgress,
    ) -> None:
        self._record_inference_progress(run=run, progress=progress)
        progress_queue.put_nowait(progress)

    def _execute_tool(
        self,
        *,
        run: _RunContext,
        messages: list[dict[str, str]],
        action: SearchNotesAction | ReadNotesAction,
    ) -> list[dict[str, str]]:
        spec = self._tool_registry.spec_for(action)
        decision = self._permission_policy.authorize(spec=spec)
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="POLICY_DECISION",
            label=f"Allowed: {spec.name}",
            detail={
                "tool": spec.name,
                "allowed": decision.allowed,
                "permission": decision.permission,
                "mutates": spec.mutates,
                "reason": decision.reason,
            },
            duration_ms=0.0,
        )
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="TOOL_CALL",
            label=f"Tool call: {spec.name}",
            detail={"tool": spec.name, "arguments": action.model_dump()},
            duration_ms=0.0,
        )
        started_at = time.perf_counter()
        result = self._tool_registry.execute(action)
        duration_ms = (time.perf_counter() - started_at) * 1_000
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="TOOL_RESULT",
            label=f"Tool result: {spec.name}",
            detail={"tool": spec.name, "payload": result.payload},
            duration_ms=duration_ms,
        )
        with_action = self._context_builder.append_action(messages=messages, action=action)
        return self._context_builder.append_tool_result(
            messages=with_action,
            result=result,
            prompts=run.prompts,
        )

    async def _stream_final_response(
        self,
        *,
        run: _RunContext,
        messages: list[dict[str, str]],
        action: RespondAction,
    ) -> AsyncIterator[dict[str, object]]:
        model = self._model_policy.for_stage(
            purpose=InferencePurpose.FINAL_RESPONSE,
            selected_model=run.selected_model,
        )
        final_messages = self._context_builder.append_final_request(
            messages=messages,
            action=action,
            prompts=run.prompts,
        )
        yield self._status_event("respond", "started", "Writing response")
        started_at = time.perf_counter()
        state = _FinalStreamState(thinking="", content="", usage={}, did_finish=False)
        async for event in self._inference.stream_text(
            base_url=run.base_url,
            model=model,
            thinking_level=run.thinking_level,
            messages=final_messages,
            on_request=lambda wire_request: self._record_wire_request(
                run=run,
                purpose=InferencePurpose.FINAL_RESPONSE,
                attempt=1,
                max_attempts=1,
                wire_request=wire_request,
            ),
        ):
            should_yield = self._consume_final_event(event=event, state=state)
            if should_yield:
                yield event
        self._validate_final_stream(state)
        duration_ms = (time.perf_counter() - started_at) * 1_000
        self._record_final_response(run=run, state=state, duration_ms=duration_ms)
        self._trace_store.complete_run(session_key=run.session_key, run_id=run.run_id)
        yield self._status_event("respond", "completed", "Response complete")
        yield {"type": "done"}

    @staticmethod
    def _consume_final_event(
        *,
        event: dict[str, object],
        state: _FinalStreamState,
    ) -> bool:
        event_type = event["type"]
        if event_type in {"thinking_delta", "content_delta"}:
            if "text" not in event:
                raise RuntimeError(f"Inference {event_type} is missing text")
            text = event["text"]
            if not isinstance(text, str) or text == "":
                raise RuntimeError(f"Inference {event_type} must contain text")
            if event_type == "thinking_delta":
                state.thinking += text
            else:
                state.content += text
            return True
        if event_type != "done":
            raise RuntimeError(f"Unknown inference stream event: {event_type}")
        state.did_finish = True
        raw_usage = {}
        if "usage" in event:
            raw_usage = event["usage"]
        if not isinstance(raw_usage, dict):
            raise RuntimeError("Inference done event usage must be an object")
        if not all(
            isinstance(key, str) and isinstance(value, int)
            for key, value in raw_usage.items()
        ):
            raise RuntimeError("Inference done event usage values must be integers")
        state.usage = dict(raw_usage)
        return False

    @staticmethod
    def _validate_final_stream(state: _FinalStreamState) -> None:
        if not state.did_finish:
            raise AgentExecutionError("Final response stream ended before completion")
        if state.content == "":
            raise AgentExecutionError("Ollama returned an empty final response")

    def _record_final_response(
        self,
        *,
        run: _RunContext,
        state: _FinalStreamState,
        duration_ms: float,
    ) -> None:
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="MODEL_RESPONSE",
            label="Model response: final-response",
            detail={
                "raw_response": state.content,
                "reasoning": state.thinking,
                "usage": state.usage,
                "validation": "not-applicable",
                "parsed": {},
                "errors": [],
            },
            duration_ms=duration_ms,
        )
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="FINAL_RESPONSE",
            label="Final response",
            detail={"content": state.content},
            duration_ms=0.0,
        )

    def _record_wire_request(
        self,
        *,
        run: _RunContext,
        purpose: InferencePurpose,
        attempt: int,
        max_attempts: int,
        wire_request: dict[str, object],
    ) -> None:
        self._trace_store.append_event(
            session_key=run.session_key,
            run_id=run.run_id,
            event_type="OLLAMA_REQUEST",
            label=(
                f"Ollama wire request: {purpose.value} · "
                f"attempt {attempt} of {max_attempts}"
            ),
            detail={
                "purpose": purpose.value,
                "attempt": attempt,
                "max_attempts": max_attempts,
                **wire_request,
            },
            duration_ms=0.0,
        )

    def _record_structured_attempts(
        self,
        *,
        run: _RunContext,
        attempts: list[InferenceAttempt],
        parsed: dict[str, object],
    ) -> None:
        for attempt_number, attempt in enumerate(attempts, start=1):
            is_success = attempt.error == "" and attempt_number == len(attempts)
            self._trace_store.append_event(
                session_key=run.session_key,
                run_id=run.run_id,
                event_type="MODEL_RESPONSE",
                label="Model response: action-selection",
                detail={
                    "raw_response": attempt.response,
                    "validation": "valid" if is_success else "invalid",
                    "parsed": parsed if is_success else {},
                    "errors": [] if attempt.error == "" else [attempt.error],
                },
                duration_ms=attempt.duration_ms,
            )

    def _record_failure(self, *, session_key: str, run_id: str, error: str) -> None:
        self._trace_store.append_event(
            session_key=session_key,
            run_id=run_id,
            event_type="ERROR",
            label="Agent run failed",
            detail={"error": error},
            duration_ms=0.0,
        )
        self._trace_store.fail_run(session_key=session_key, run_id=run_id, error=error)

    @staticmethod
    def _tool_status_label(action: SearchNotesAction | ReadNotesAction) -> str:
        if isinstance(action, SearchNotesAction):
            return "Searching notes"
        count = len(action.note_ids)
        noun = "notes"
        if count == 1:
            noun = "note"
        return f"Reading {count} {noun}"

    @staticmethod
    def _progress_status_event(
        progress: StructuredInferenceProgress,
    ) -> dict[str, object]:
        if progress.attempt < 1 or progress.attempt > progress.max_attempts:
            raise ValueError("Structured inference progress attempt is invalid")
        attempt_label = f"attempt {progress.attempt} of {progress.max_attempts}"
        if progress.phase == "attempt_started":
            label = f"Waiting for Ollama · {attempt_label}"
            if progress.attempt > 1:
                label = f"Instructor retrying · {label}"
            return AgentRuntime._status_event("model_request", "started", label)
        if progress.phase == "response_received":
            return AgentRuntime._status_event(
                "validation",
                "started",
                f"Ollama responded · validating {attempt_label}",
            )
        if progress.phase == "retrying":
            return AgentRuntime._status_event(
                "retry",
                "started",
                f"{progress.failure_kind} ({progress.error_type}) · Instructor will retry",
            )
        if progress.phase == "attempt_failed":
            return AgentRuntime._status_event(
                "retry",
                "completed",
                f"{progress.failure_kind} ({progress.error_type}) · no retries remain",
            )
        if progress.phase == "attempt_succeeded":
            return AgentRuntime._status_event(
                "validation",
                "completed",
                f"Structured action validated · {attempt_label}",
            )
        raise ValueError(f"Unsupported structured inference phase: {progress.phase}")

    @staticmethod
    def _selected_action_status_event(action: AgentAction) -> dict[str, object]:
        if isinstance(action, SearchNotesAction):
            query_label = action.query
            if len(query_label) > 120:
                query_label = f"{query_label[:117]}…"
            label = f"Selected action · Search notes · {query_label}"
        elif isinstance(action, ReadNotesAction):
            count = len(action.note_ids)
            noun = "notes"
            if count == 1:
                noun = "note"
            label = f"Selected action · Read {count} {noun}"
        elif isinstance(action, RespondAction):
            label = "Selected action · Respond to user"
        else:
            raise TypeError(f"Unsupported selected action: {type(action)}")
        return AgentRuntime._status_event(action.kind, "completed", label)

    @staticmethod
    def _status_event(action: str, status: str, label: str) -> dict[str, object]:
        if status not in {"started", "completed"}:
            raise ValueError("Unsupported action status")
        return {
            "type": "action_status",
            "action": action,
            "status": status,
            "label": label,
        }
