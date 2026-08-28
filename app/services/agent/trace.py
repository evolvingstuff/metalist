"""Session-only trace capture for the current or most recent agent run."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4


class AgentTraceStore:
    def __init__(self) -> None:
        self._exact_detail_sessions: set[str] = set()
        self._latest_runs: dict[str, dict[str, object]] = {}
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._exact_detail_sessions.clear()
            self._latest_runs.clear()

    def clear_session(self, *, session_key: str) -> None:
        self._validate_session_key(session_key)
        with self._lock:
            self._exact_detail_sessions.discard(session_key)
            self._latest_runs.pop(session_key, None)

    def clear_trace(self, *, session_key: str) -> None:
        self._validate_session_key(session_key)
        with self._lock:
            self._latest_runs.pop(session_key, None)

    def set_exact_details_enabled(self, *, session_key: str, enabled: bool) -> None:
        self._validate_session_key(session_key)
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean")
        with self._lock:
            if enabled:
                self._exact_detail_sessions.add(session_key)
            else:
                self._exact_detail_sessions.discard(session_key)

    def is_exact_details_enabled(self, *, session_key: str) -> bool:
        self._validate_session_key(session_key)
        with self._lock:
            return session_key in self._exact_detail_sessions

    def start_run(self, *, session_key: str, model: str, user_message: str) -> str:
        self._validate_session_key(session_key)
        if not isinstance(model, str) or model == "":
            raise ValueError("Trace model must be non-empty")
        if not isinstance(user_message, str) or user_message == "":
            raise ValueError("Trace user message must be non-empty")
        run_id = str(uuid4())
        with self._lock:
            self._latest_runs[session_key] = {
                "run_id": run_id,
                "model": model,
                "user_message": user_message,
                "status": "running",
                "started_at": self._now_iso(),
                "finished_at": "",
                "error": "",
                "events": [],
            }
        return run_id

    def append_event(
        self,
        *,
        session_key: str,
        run_id: str,
        event_type: str,
        label: str,
        detail: dict[str, object],
        duration_ms: float,
    ) -> None:
        self._validate_event_input(
            session_key=session_key,
            run_id=run_id,
            event_type=event_type,
            label=label,
            detail=detail,
            duration_ms=duration_ms,
        )
        with self._lock:
            run = self._latest_runs.get(session_key)
            if run is None:
                return
            if run["run_id"] != run_id:
                raise RuntimeError("Agent trace run id does not match latest run")
            events = run["events"]
            assert isinstance(events, list)
            events.append(
                {
                    "sequence": len(events) + 1,
                    "type": event_type,
                    "label": label,
                    "timestamp": self._now_iso(),
                    "duration_ms": round(duration_ms, 3),
                    "detail": deepcopy(detail),
                }
            )

    def complete_run(self, *, session_key: str, run_id: str) -> None:
        self._finish_run(session_key=session_key, run_id=run_id, status="complete", error="")

    def fail_run(self, *, session_key: str, run_id: str, error: str) -> None:
        if not isinstance(error, str) or error == "":
            raise ValueError("Trace failure error must be non-empty")
        self._finish_run(session_key=session_key, run_id=run_id, status="error", error=error)

    def snapshot(self, *, session_key: str) -> dict[str, object]:
        self._validate_session_key(session_key)
        with self._lock:
            run = self._latest_runs.get(session_key)
            return {
                "enabled": session_key in self._exact_detail_sessions,
                "has_trace": run is not None,
                "run": deepcopy(run) if run is not None else {},
            }

    def _finish_run(self, *, session_key: str, run_id: str, status: str, error: str) -> None:
        self._validate_session_key(session_key)
        if not isinstance(run_id, str) or run_id == "":
            raise ValueError("run_id must be non-empty")
        if status not in {"complete", "error"}:
            raise ValueError("Unsupported trace completion status")
        with self._lock:
            run = self._latest_runs.get(session_key)
            if run is None:
                return
            if run["run_id"] != run_id:
                raise RuntimeError("Agent trace run id does not match latest run")
            run["status"] = status
            run["finished_at"] = self._now_iso()
            run["error"] = error

    @staticmethod
    def _validate_session_key(session_key: str) -> None:
        if not isinstance(session_key, str) or session_key == "":
            raise ValueError("session_key must be a non-empty string")

    @staticmethod
    def _validate_event_input(
        *,
        session_key: str,
        run_id: str,
        event_type: str,
        label: str,
        detail: dict[str, object],
        duration_ms: float,
    ) -> None:
        AgentTraceStore._validate_session_key(session_key)
        if not isinstance(run_id, str) or run_id == "":
            raise ValueError("run_id must be non-empty")
        if not isinstance(event_type, str) or event_type == "":
            raise ValueError("event_type must be non-empty")
        if not isinstance(label, str) or label == "":
            raise ValueError("label must be non-empty")
        if not isinstance(detail, dict):
            raise TypeError("detail must be a dictionary")
        if not isinstance(duration_ms, (int, float)) or duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


agent_trace_store = AgentTraceStore()
