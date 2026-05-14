from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import faulthandler
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

from loguru import logger

from app.server_runtime import resolve_runtime_logs_directory


_LOG_ROTATION = "25 MB"
_LOG_RETENTION = "14 days"
_DIRECT_APPEND_LOG_MAX_BYTES = 25 * 1024 * 1024
_DIRECT_APPEND_LOG_TAIL_BYTES = 10 * 1024 * 1024
_DIRECT_APPEND_LOG_RECYCLE_INTERVAL_SECONDS = 300.0
_LOG_DIRECTORY_MAX_BYTES = 512 * 1024 * 1024
_DIRECT_APPEND_LOG_PATTERNS = (
    "namespace-*.log",
    "namespace-delete-*.log",
    "*-server.fault.log",
)
_EVENT_LOOP_PROBE_INTERVAL_SECONDS = 1.0
_EVENT_LOOP_STALL_SECONDS = 5.0
_EVENT_LOOP_STALL_LOG_INTERVAL_SECONDS = 5.0
_SLOW_REQUEST_SECONDS = 10.0
_SLOW_REQUEST_LOG_INTERVAL_SECONDS = 10.0
_REQUEST_WATCH_INTERVAL_SECONDS = 2.0
_diagnostic_file_handle = None
_process_diagnostics_configured = False
_request_watchdog_started = False
_event_loop_watchdog_started = False
_direct_append_log_recycler_started = False


@dataclass
class ActiveRequest:
    request_id: str
    method: str
    path: str
    query: str
    client: str
    user_agent: str
    started_at: float
    last_logged_at: float


@dataclass(frozen=True)
class SlowRequestLog:
    request_id: str
    method: str
    path: str
    query: str
    client: str
    user_agent: str
    duration_seconds: float


@dataclass(frozen=True)
class LogDiskUsage:
    file_count: int
    total_bytes: int
    largest_file_path: Path
    largest_file_bytes: int


_active_requests: dict[str, ActiveRequest] = {}
_active_requests_lock = threading.Lock()


def _diagnostic_log_path(*, namespace: str) -> Path:
    if namespace.strip() == "":
        raise ValueError("namespace must not be empty")
    logs_directory = resolve_runtime_logs_directory()
    logs_directory.mkdir(parents=True, exist_ok=True)
    return logs_directory / f"{namespace}-server.log"


def configure_process_diagnostics(*, namespace: str, enabled: bool) -> Path | None:
    global _diagnostic_file_handle
    global _process_diagnostics_configured

    if not enabled:
        return None
    if _process_diagnostics_configured:
        return _diagnostic_log_path(namespace=namespace)

    log_path = _diagnostic_log_path(namespace=namespace)
    logger.add(
        str(log_path),
        level="INFO",
        backtrace=False,
        diagnose=False,
        rotation=_LOG_ROTATION,
        retention=_LOG_RETENTION,
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | pid={process} thread={thread.name} | {message} | {extra}",
    )

    fault_path = log_path.with_suffix(".fault.log")
    recycle_direct_append_log_file(path=fault_path)
    _diagnostic_file_handle = fault_path.open("a", buffering=1)
    faulthandler.enable(file=_diagnostic_file_handle, all_threads=True)
    if hasattr(signal, "SIGUSR1"):
        faulthandler.register(
            signal.SIGUSR1,
            file=_diagnostic_file_handle,
            all_threads=True,
            chain=False,
        )

    sys.excepthook = _log_unhandled_exception
    threading.excepthook = _log_unhandled_thread_exception
    _process_diagnostics_configured = True

    logger.info(
        "[diagnostics] process diagnostics enabled log_path={log_path} fault_log_path={fault_log_path}",
        log_path=str(log_path),
        fault_log_path=str(fault_path),
    )
    start_request_watchdog()
    start_direct_append_log_recycler()
    assert_log_disk_usage_within_bounds()
    return log_path


def recycle_direct_append_log_file(*, path: Path) -> bool:
    if not isinstance(path, Path):
        raise TypeError(f"path must be a Path, got {type(path)}")
    if not path.exists():
        return False
    size_bytes = path.stat().st_size
    if size_bytes <= _DIRECT_APPEND_LOG_MAX_BYTES:
        return False

    tail_bytes = path.read_bytes()[-_DIRECT_APPEND_LOG_TAIL_BYTES:]
    marker = (
        b"\n[diagnostics] log compacted because it exceeded "
        + str(_DIRECT_APPEND_LOG_MAX_BYTES).encode("ascii")
        + b" bytes; retained tail follows\n"
    )
    path.write_bytes(marker + tail_bytes)
    logger.warning(
        "[diagnostics] compacted append log path={path} old_size={old_size} retained_bytes={retained_bytes}",
        path=str(path),
        old_size=size_bytes,
        retained_bytes=len(tail_bytes),
    )
    return True


def recycle_direct_append_logs() -> int:
    logs_directory = resolve_runtime_logs_directory()
    if not logs_directory.exists():
        return 0
    recycled_count = 0
    for pattern in _DIRECT_APPEND_LOG_PATTERNS:
        for path in logs_directory.glob(pattern):
            if not path.is_file():
                continue
            if recycle_direct_append_log_file(path=path):
                recycled_count += 1
    return recycled_count


def _iter_log_files(*, logs_directory: Path) -> list[Path]:
    if not isinstance(logs_directory, Path):
        raise TypeError(f"logs_directory must be a Path, got {type(logs_directory)}")
    if not logs_directory.exists():
        return []
    return sorted(path for path in logs_directory.iterdir() if path.is_file())


def _matches_direct_append_pattern(*, path: Path) -> bool:
    for pattern in _DIRECT_APPEND_LOG_PATTERNS:
        if path.match(pattern):
            return True
    return False


def calculate_log_disk_usage(*, logs_directory: Path) -> LogDiskUsage:
    log_files = _iter_log_files(logs_directory=logs_directory)
    if len(log_files) == 0:
        return LogDiskUsage(
            file_count=0,
            total_bytes=0,
            largest_file_path=logs_directory,
            largest_file_bytes=0,
        )

    total_bytes = 0
    largest_file_path = log_files[0]
    largest_file_bytes = -1
    for path in log_files:
        size_bytes = path.stat().st_size
        total_bytes += size_bytes
        if size_bytes > largest_file_bytes:
            largest_file_path = path
            largest_file_bytes = size_bytes

    return LogDiskUsage(
        file_count=len(log_files),
        total_bytes=total_bytes,
        largest_file_path=largest_file_path,
        largest_file_bytes=largest_file_bytes,
    )


def assert_log_disk_usage_within_bounds() -> None:
    recycle_direct_append_logs()
    logs_directory = resolve_runtime_logs_directory()
    log_files = _iter_log_files(logs_directory=logs_directory)
    for path in log_files:
        if not _matches_direct_append_pattern(path=path):
            continue
        size_bytes = path.stat().st_size
        if size_bytes > _DIRECT_APPEND_LOG_MAX_BYTES:
            raise RuntimeError(
                f"Log file exceeds direct append cap after recycling: "
                f"path={path} size={size_bytes} cap={_DIRECT_APPEND_LOG_MAX_BYTES}"
            )

    usage = calculate_log_disk_usage(logs_directory=logs_directory)
    if usage.total_bytes > _LOG_DIRECTORY_MAX_BYTES:
        raise RuntimeError(
            f"Log directory exceeds disk bound: directory={logs_directory} "
            f"total={usage.total_bytes} cap={_LOG_DIRECTORY_MAX_BYTES} "
            f"files={usage.file_count} largest={usage.largest_file_path} "
            f"largest_size={usage.largest_file_bytes}"
        )


def start_direct_append_log_recycler() -> None:
    global _direct_append_log_recycler_started

    if _direct_append_log_recycler_started:
        return
    recycle_direct_append_logs()
    thread = threading.Thread(
        target=_direct_append_log_recycler_loop,
        name="metalist-log-recycler",
        daemon=True,
    )
    _direct_append_log_recycler_started = True
    thread.start()


def _direct_append_log_recycler_loop() -> None:
    while True:
        time.sleep(_DIRECT_APPEND_LOG_RECYCLE_INTERVAL_SECONDS)
        recycle_direct_append_logs()


def _log_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical(
        "[diagnostics] unhandled process exception"
    )


def _log_unhandled_thread_exception(args: threading.ExceptHookArgs) -> None:
    if args.thread is None:
        raise RuntimeError("Thread exception hook missing thread")
    logger.opt(
        exception=(args.exc_type, args.exc_value, args.exc_traceback)
    ).critical(
        "[diagnostics] unhandled thread exception thread={thread_name}",
        thread_name=args.thread.name,
    )


def _format_thread_stacks() -> str:
    frames = sys._current_frames()
    lines: list[str] = []
    for thread in threading.enumerate():
        lines.append(f"\n# Thread {thread.name} ident={thread.ident} daemon={thread.daemon}")
        if thread.ident not in frames:
            lines.append("  <no frame>")
            continue
        lines.extend(traceback.format_stack(frames[thread.ident]))
    return "".join(lines)


def log_thread_dump(*, reason: str) -> None:
    if reason.strip() == "":
        raise ValueError("reason must not be empty")
    logger.error(
        "[diagnostics] thread dump reason={reason}\n{stacks}",
        reason=reason,
        stacks=_format_thread_stacks(),
    )


class TrackedRequest:
    def __init__(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        query: str,
        client: str,
        user_agent: str,
        started_at: float,
    ) -> None:
        self._request_id = request_id
        begin_request(
            request_id=request_id,
            method=method,
            path=path,
            query=query,
            client=client,
            user_agent=user_agent,
            started_at=started_at,
        )

    def __enter__(self) -> "TrackedRequest":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_traceback: object,
    ) -> bool:
        duration_ms = finish_request(
            request_id=self._request_id,
            ended_at=time.perf_counter(),
        )
        if exc_type is not None:
            logger.opt(exception=(exc_type, exc, exc_traceback)).error(
                "[diagnostics] request crashed request_id={request_id} duration={duration:.2f} ms",
                request_id=self._request_id,
                duration=duration_ms,
            )
        return False


def track_request(
    *,
    request_id: str,
    method: str,
    path: str,
    query: str,
    client: str,
    user_agent: str,
    started_at: float,
) -> TrackedRequest:
    return TrackedRequest(
        request_id=request_id,
        method=method,
        path=path,
        query=query,
        client=client,
        user_agent=user_agent,
        started_at=started_at,
    )


def begin_request(
    *,
    request_id: str,
    method: str,
    path: str,
    query: str,
    client: str,
    user_agent: str,
    started_at: float,
) -> None:
    assert request_id != ""
    assert method != ""
    assert path.startswith("/")
    request = ActiveRequest(
        request_id=request_id,
        method=method,
        path=path,
        query=query,
        client=client,
        user_agent=user_agent,
        started_at=started_at,
        last_logged_at=started_at,
    )
    with _active_requests_lock:
        _active_requests[request_id] = request


def finish_request(*, request_id: str, ended_at: float) -> float:
    with _active_requests_lock:
        request = _active_requests.pop(request_id)
    duration_ms = (ended_at - request.started_at) * 1000
    return duration_ms


def snapshot_active_requests() -> Mapping[str, ActiveRequest]:
    with _active_requests_lock:
        return dict(_active_requests)


def collect_slow_request_logs(*, now: float, threshold_seconds: float) -> list[SlowRequestLog]:
    if threshold_seconds <= 0.0:
        raise ValueError("threshold_seconds must be positive")
    slow_requests: list[SlowRequestLog] = []
    with _active_requests_lock:
        for request in _active_requests.values():
            duration_seconds = now - request.started_at
            since_last_log_seconds = now - request.last_logged_at
            if duration_seconds < threshold_seconds:
                continue
            if since_last_log_seconds < _SLOW_REQUEST_LOG_INTERVAL_SECONDS:
                continue
            request.last_logged_at = now
            slow_requests.append(
                SlowRequestLog(
                    request_id=request.request_id,
                    method=request.method,
                    path=request.path,
                    query=request.query,
                    client=request.client,
                    user_agent=request.user_agent,
                    duration_seconds=duration_seconds,
                )
            )
    return slow_requests


def start_request_watchdog() -> None:
    global _request_watchdog_started

    if _request_watchdog_started:
        return
    thread = threading.Thread(
        target=_request_watchdog_loop,
        name="metalist-request-watchdog",
        daemon=True,
    )
    _request_watchdog_started = True
    thread.start()


def _request_watchdog_loop() -> None:
    while True:
        time.sleep(_REQUEST_WATCH_INTERVAL_SECONDS)
        slow_requests = collect_slow_request_logs(
            now=time.perf_counter(),
            threshold_seconds=_SLOW_REQUEST_SECONDS,
        )
        for request in slow_requests:
            logger.warning(
                "[diagnostics] slow in-flight request request_id={request_id} method={method} path={path} query={query} client={client} duration={duration:.2f}s user_agent={user_agent}",
                request_id=request.request_id,
                method=request.method,
                path=request.path,
                query=request.query,
                client=request.client,
                duration=request.duration_seconds,
                user_agent=request.user_agent,
            )


class EventLoopWatchdog:
    def __init__(self, *, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._lock = threading.Lock()
        self._last_ack_at = time.perf_counter()
        self._last_logged_at = self._last_ack_at
        self._probe_pending = False

    def start(self) -> None:
        thread = threading.Thread(
            target=self._watch_loop,
            name="metalist-event-loop-watchdog",
            daemon=True,
        )
        thread.start()

    def _ack_probe(self) -> None:
        with self._lock:
            self._last_ack_at = time.perf_counter()
            self._probe_pending = False

    def _schedule_probe_if_needed(self) -> None:
        with self._lock:
            if self._probe_pending:
                return
            self._probe_pending = True
        self._loop.call_soon_threadsafe(self._ack_probe)

    def _watch_loop(self) -> None:
        while True:
            time.sleep(_EVENT_LOOP_PROBE_INTERVAL_SECONDS)
            self._schedule_probe_if_needed()
            self._log_stall_if_needed(now=time.perf_counter())

    def _log_stall_if_needed(self, *, now: float) -> None:
        should_log = False
        blocked_seconds = 0.0
        active_requests = snapshot_active_requests()
        with self._lock:
            blocked_seconds = now - self._last_ack_at
            since_last_log_seconds = now - self._last_logged_at
            if (
                blocked_seconds >= _EVENT_LOOP_STALL_SECONDS
                and since_last_log_seconds >= _EVENT_LOOP_STALL_LOG_INTERVAL_SECONDS
            ):
                self._last_logged_at = now
                should_log = True
        if not should_log:
            return
        logger.error(
            "[diagnostics] event loop unresponsive blocked_for={blocked:.2f}s active_requests={active_count}",
            blocked=blocked_seconds,
            active_count=len(active_requests),
        )
        for request in active_requests.values():
            logger.error(
                "[diagnostics] active during loop stall request_id={request_id} method={method} path={path} query={query} client={client} duration={duration:.2f}s",
                request_id=request.request_id,
                method=request.method,
                path=request.path,
                query=request.query,
                client=request.client,
                duration=now - request.started_at,
            )
        log_thread_dump(reason=f"event loop unresponsive for {blocked_seconds:.2f}s")


def start_asyncio_diagnostics(*, enabled: bool) -> None:
    global _event_loop_watchdog_started

    if not enabled:
        return
    if _event_loop_watchdog_started:
        return
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_handle_asyncio_exception)
    watchdog = EventLoopWatchdog(loop=loop)
    _event_loop_watchdog_started = True
    watchdog.start()
    logger.info("[diagnostics] asyncio diagnostics enabled")


def _handle_asyncio_exception(
    loop: asyncio.AbstractEventLoop,
    context: dict[str, object],
) -> None:
    message = context.get("message")
    exception = context.get("exception")
    if isinstance(exception, BaseException):
        logger.opt(exception=exception).error(
            "[diagnostics] unhandled asyncio exception message={message}",
            message=message,
        )
        return
    logger.error(
        "[diagnostics] asyncio error message={message} context={context}",
        message=message,
        context=context,
    )
