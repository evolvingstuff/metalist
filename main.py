import uvicorn
import http.client
import importlib
import logging
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import ssl
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path

from app.server_runtime import apply_main_cli_args_to_environ
from app.server_runtime import ensure_default_tls_pair
from app.server_runtime import MainCliArgs
from app.server_runtime import prepare_database_runtime_path
from app.server_runtime import resolve_backend_connect_host
from app.server_runtime import resolve_database_runtime_config
from app.server_runtime import resolve_local_browser_host
from app.server_runtime import resolve_main_mcp_url
from app.server_runtime import resolve_main_server_config
from app.startup_sanity import assert_startup_sanity
from app.services.exception_capture import CapturedExceptionContext
from app.services.namespace_switcher import NamespaceOpenResult
from app.services.namespace_switcher import open_or_launch_all_namespaces

@dataclass(frozen=True)
class _StartedHttpsProxy:
    server: ThreadingHTTPServer
    thread: threading.Thread


_WAIT_POLL_INTERVAL_SECONDS = 0.25
_TERMINATE_GRACE_SECONDS = 5.0
_KILL_GRACE_SECONDS = 5.0
_EXPLICIT_NAMESPACE_LAUNCH_ENV_NAMES = (
    "METALIST_NAMESPACE",
    "METALIST_PORT",
    "METALIST_HTTPS_PORT",
    "MCP_AGENT_WEB_PORT",
)


def _load_mcp_client_module():
    # Delay importing mcp_client until after CLI/env namespace selection runs.
    return importlib.import_module("mcp_client")


class FilterCheckUpdates(logging.Filter):
    NOISY_PATTERNS = (
        'POST /api/notes/acquire-lock',
        'POST /api2/notes/acquire-lock',
        'POST /api2/notes/release-lock',
        'GET /api/auth/sessions',
        'GET /api2/auth/status',
    )

    def filter(self, record):
        message = record.getMessage()
        return not any(pattern in message for pattern in self.NOISY_PATTERNS)


def _resolve_current_entrypoint() -> str | None:
    raw_value = sys.argv[0].strip()
    if raw_value == "":
        return None
    if os.path.sep in raw_value:
        return os.path.abspath(raw_value)
    if os.path.altsep is not None and os.path.altsep in raw_value:
        return os.path.abspath(raw_value)
    resolved = shutil.which(raw_value)
    if resolved is None:
        return None
    return resolved


def _record_self_executable_for_namespace_launch() -> None:
    entrypoint = _resolve_current_entrypoint()
    if entrypoint is None:
        return
    os.environ["METALIST_SELF_EXECUTABLE"] = entrypoint


def _is_source_main_entrypoint() -> bool:
    entrypoint = _resolve_current_entrypoint()
    if entrypoint is None:
        return False
    return os.path.basename(entrypoint) == "main.py"


def _should_open_or_launch_all_namespaces(
    *,
    original_environ: dict[str, str],
    cli_args: MainCliArgs,
) -> bool:
    if cli_args.test_mode:
        return False
    if cli_args.namespace_requested:
        return False
    if cli_args.port is not None or cli_args.https_port is not None or cli_args.mcp_port is not None:
        return False
    if not _is_source_main_entrypoint():
        return False
    return not any(name in original_environ for name in _EXPLICIT_NAMESPACE_LAUNCH_ENV_NAMES)


def _resolve_agent_web_browser_host(*, environ: dict[str, str]) -> str:
    if "MCP_AGENT_WEB_HOST" in environ:
        host = environ["MCP_AGENT_WEB_HOST"]
        if host.strip() == "":
            raise RuntimeError("MCP_AGENT_WEB_HOST must not be empty")
    else:
        host = _load_mcp_client_module().DEFAULT_WEB_HOST
    return resolve_local_browser_host(host=host)


def _build_https_namespace_url(*, host: str, result: NamespaceOpenResult) -> str:
    https_port = result.saved_profile.https_port
    if https_port is None:
        return "disabled"
    return f"https://{host}:{https_port}"


def _build_mcp_namespace_url(*, environ: dict[str, str], result: NamespaceOpenResult) -> str:
    if not _env_flag_from_mapping(environ=environ, name="MCP_AGENT_WEB_ENABLED", default=True):
        return "disabled"
    mcp_port = result.saved_profile.mcp_port
    if not isinstance(mcp_port, int):
        raise RuntimeError(f"Namespace {result.namespace} is missing an MCP port")
    mcp_host = _resolve_agent_web_browser_host(environ=environ)
    return f"http://{mcp_host}:{mcp_port}"


def _print_namespace_bootstrap_results(
    *,
    environ: dict[str, str],
    launch_results: list[NamespaceOpenResult],
) -> None:
    main_server_config = resolve_main_server_config(environ=environ)
    browser_host = resolve_local_browser_host(host=main_server_config.host)
    print("MetaList namespace bootstrap:")
    print("namespace\taction\thttp\thttps\tmcp")
    for result in launch_results:
        https_url = _build_https_namespace_url(host=browser_host, result=result)
        mcp_url = _build_mcp_namespace_url(environ=environ, result=result)
        print(
            "\t".join(
                [
                    result.namespace,
                    result.action,
                    result.url,
                    https_url,
                    mcp_url,
                ]
            )
        )


def _env_flag(name: str, default: bool) -> bool:
    if name not in os.environ:
        return default

    value = os.environ[name].strip().lower()
    assert value != "", f"Empty env flag: {name}"

    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean env flag {name}={value!r}")


def _env_flag_from_mapping(*, environ: dict[str, str], name: str, default: bool) -> bool:
    if name not in environ:
        return default
    value = environ[name].strip().lower()
    assert value != "", f"Empty env flag: {name}"
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean env flag {name}={value!r}")


def _env_int(name: str, default: int) -> int:
    if name not in os.environ:
        return default
    value = os.environ[name].strip()
    assert value != "", f"Empty env int: {name}"
    if not value.isdigit():
        raise ValueError(f"Invalid integer env {name}={value!r}")
    return int(value)


def _env_choice(name: str, default: str, allowed: set[str]) -> str:
    if name not in os.environ:
        return default
    value = os.environ[name].strip().casefold()
    assert value != "", f"Empty env choice: {name}"
    if value not in allowed:
        raise ValueError(f"Invalid choice env {name}={value!r}; allowed={sorted(allowed)}")
    return value


def _read_process_state(*, pid: int) -> str | None:
    completed = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return None
    process_state = completed.stdout.strip()
    if process_state == "":
        return None
    return process_state


def _is_process_running(*, pid: int) -> bool:
    if not isinstance(pid, int):
        raise TypeError(f"pid must be an int, got {type(pid)}")
    if pid <= 0:
        raise ValueError(f"pid must be positive, got: {pid}")
    kill_capture = CapturedExceptionContext(ProcessLookupError, PermissionError)
    with kill_capture:
        os.kill(pid, 0)
    if kill_capture.captured_exception is not None:
        if isinstance(kill_capture.captured_exception, ProcessLookupError):
            return False
        if isinstance(kill_capture.captured_exception, PermissionError):
            return True
        raise RuntimeError("Unexpected process-probe exception type")
    process_state = _read_process_state(pid=pid)
    if process_state is None:
        return True
    if process_state.startswith("Z"):
        return False
    return True


def _wait_for_process_exit(*, pid: int, timeout_seconds: float) -> bool:
    if not isinstance(timeout_seconds, float):
        raise TypeError(f"timeout_seconds must be a float, got {type(timeout_seconds)}")
    if timeout_seconds < 0.0:
        raise ValueError(f"timeout_seconds must be >= 0.0, got {timeout_seconds}")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_process_running(pid=pid):
            return True
        time.sleep(_WAIT_POLL_INTERVAL_SECONDS)
    return not _is_process_running(pid=pid)


def _send_signal_if_running(*, pid: int, signal_number: int) -> None:
    if not _is_process_running(pid=pid):
        return
    signal_capture = CapturedExceptionContext(ProcessLookupError)
    with signal_capture:
        os.kill(pid, signal_number)
    if signal_capture.captured_exception is not None:
        return


def _stop_process(*, pid: int) -> None:
    if not _is_process_running(pid=pid):
        return

    _send_signal_if_running(pid=pid, signal_number=signal.SIGTERM)
    if _wait_for_process_exit(pid=pid, timeout_seconds=_TERMINATE_GRACE_SECONDS):
        return

    _send_signal_if_running(pid=pid, signal_number=signal.SIGKILL)
    if _wait_for_process_exit(pid=pid, timeout_seconds=_KILL_GRACE_SECONDS):
        return

    raise RuntimeError(f"Timed out waiting for process {pid} to exit")


def _find_listening_pids_for_port(*, port: int) -> list[int]:
    if not isinstance(port, int):
        raise TypeError(f"port must be an int, got {type(port)}")
    if port <= 0 or port > 65535:
        raise ValueError(f"port must be between 1 and 65535, got: {port}")

    lsof_path = shutil.which("lsof")
    if lsof_path is None:
        raise RuntimeError("`lsof` is required to evict listeners from occupied ports")

    completed = subprocess.run(
        [lsof_path, "-nP", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        error_text = completed.stderr.strip()
        raise RuntimeError(
            f"`lsof` failed while checking port {port}: exit={completed.returncode} stderr={error_text!r}"
        )
    stdout = completed.stdout.strip()
    if stdout == "":
        return []

    ordered_pids: list[int] = []
    seen_pids: set[int] = set()
    for raw_line in stdout.splitlines():
        raw_pid = raw_line.strip()
        if raw_pid == "":
            continue
        if not raw_pid.isdigit():
            raise RuntimeError(f"`lsof` returned a non-numeric pid for port {port}: {raw_pid!r}")
        pid = int(raw_pid)
        if pid <= 0:
            raise RuntimeError(f"`lsof` returned invalid pid for port {port}: {pid}")
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        ordered_pids.append(pid)
    return ordered_pids


def _evict_processes_listening_on_port(*, port: int) -> None:
    listener_pids = _find_listening_pids_for_port(port=port)
    if len(listener_pids) == 0:
        return

    current_pid = os.getpid()
    foreign_listener_pids: list[int] = []
    for pid in listener_pids:
        if pid == current_pid:
            raise RuntimeError(
                f"Port {port} is already held by the current MetaList process (pid {current_pid})"
            )
        foreign_listener_pids.append(pid)

    for pid in foreign_listener_pids:
        print(f"Port {port} is in use; terminating pid {pid}")
        _stop_process(pid=pid)


def _start_agent_web_sidecar(*, default_mcp_url: str) -> None:
    mcp_client = _load_mcp_client_module()
    enabled = _env_flag("MCP_AGENT_WEB_ENABLED", True)
    if not enabled:
        print("Agent web app sidecar disabled (MCP_AGENT_WEB_ENABLED=0)")
        return

    if "MCP_AGENT_WEB_HOST" in os.environ:
        host = os.environ["MCP_AGENT_WEB_HOST"]
    else:
        host = mcp_client.DEFAULT_WEB_HOST
    port = _env_int("MCP_AGENT_WEB_PORT", mcp_client.DEFAULT_WEB_PORT)
    _evict_processes_listening_on_port(port=port)
    if "MCP_AGENT_OLLAMA_MODEL" in os.environ:
        model = os.environ["MCP_AGENT_OLLAMA_MODEL"]
    else:
        model = mcp_client.DEFAULT_OLLAMA_MODEL
    if "MCP_AGENT_MCP_URL" in os.environ:
        mcp_url = os.environ["MCP_AGENT_MCP_URL"]
    else:
        mcp_url = default_mcp_url
    if "MCP_AGENT_OLLAMA_CHAT_URL" in os.environ:
        ollama_chat_url = os.environ["MCP_AGENT_OLLAMA_CHAT_URL"]
    else:
        ollama_chat_url = mcp_client.DEFAULT_OLLAMA_CHAT_URL
    max_steps = _env_int("MCP_AGENT_MAX_STEPS", mcp_client.DEFAULT_MAX_STEPS)
    max_expressions = _env_int(
        "MCP_AGENT_MAX_EXPRESSIONS",
        mcp_client.DEFAULT_MAX_EXPRESSIONS,
    )
    hydrate_top_k = _env_int(
        "MCP_AGENT_HYDRATE_TOP_K",
        mcp_client.DEFAULT_HYDRATE_TOP_K,
    )
    regex_engine = _env_choice(
        "MCP_AGENT_REGEX_ENGINE",
        mcp_client.DEFAULT_REGEX_ENGINE,
        {"python-re", "re2"},
    )
    if "MCP_AGENT_SEARCH_CONTEXT_QUERY" in os.environ:
        search_context_query = os.environ["MCP_AGENT_SEARCH_CONTEXT_QUERY"]
    else:
        search_context_query = mcp_client.DEFAULT_SEARCH_CONTEXT_QUERY
    reset_ollama_on_start = _env_flag("MCP_AGENT_RESET_OLLAMA_ON_START", True)
    if reset_ollama_on_start:
        mcp_client.reset_local_ollama_server(ollama_chat_url=ollama_chat_url)

    agent_app = mcp_client.create_web_app(
        default_model=model,
        default_max_steps=max_steps,
        default_max_expressions=max_expressions,
        default_hydrate_top_k=hydrate_top_k,
        default_regex_engine=regex_engine,
        default_search_context_query=search_context_query,
        default_mcp_url=mcp_url,
        default_ollama_chat_url=ollama_chat_url,
    )

    def _run() -> None:
        uvicorn.run(
            agent_app,
            host=host,
            port=port,
            reload=False,
            workers=1,
        )

    link = f"http://{host}:{port}"
    print(f"Agent web app: {link}")
    thread = threading.Thread(target=_run, name="mcp-agent-web", daemon=True)
    thread.start()


def _run_main_listener(
    *,
    app_object,
    host: str,
    port: int,
    proxy_headers: bool,
    forwarded_allow_ips: str,
    ssl_certfile: str | None,
    ssl_keyfile: str | None,
) -> None:
    _evict_processes_listening_on_port(port=port)
    uvicorn.run(
        app_object,
        host=host,
        port=port,
        reload=False,  # Disable auto-reload
        workers=1,  # Limit to a single worker
        proxy_headers=proxy_headers,
        forwarded_allow_ips=forwarded_allow_ips,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


def _start_https_proxy_server(
    *,
    host: str,
    https_port: int,
    backend_host: str,
    backend_port: int,
    ssl_certfile: str,
    ssl_keyfile: str,
) -> None:
    hop_by_hop_headers = frozenset(
        {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
    )

    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _proxy(self) -> None:
            content_length = self.headers.get("Content-Length")
            request_body = b""
            if content_length is not None:
                request_body = self.rfile.read(int(content_length))

            forwarded_headers: dict[str, str] = {}
            for key, value in self.headers.items():
                if key.lower() in hop_by_hop_headers:
                    continue
                forwarded_headers[key] = value

            client_ip = self.client_address[0]
            existing_forwarded_for = self.headers.get("X-Forwarded-For")
            if existing_forwarded_for is not None and existing_forwarded_for.strip() != "":
                forwarded_headers["X-Forwarded-For"] = f"{existing_forwarded_for}, {client_ip}"
            else:
                forwarded_headers["X-Forwarded-For"] = client_ip
            forwarded_headers["X-Forwarded-Proto"] = "https"

            connection = http.client.HTTPConnection(
                host=backend_host,
                port=backend_port,
                timeout=60,
            )
            connection.request(
                method=self.command,
                url=self.path,
                body=request_body,
                headers=forwarded_headers,
            )
            response = connection.getresponse()
            response_body = response.read()

            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                lower_key = key.lower()
                if lower_key in hop_by_hop_headers or lower_key == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response_body)
            connection.close()

        def do_GET(self) -> None:
            self._proxy()

        def do_HEAD(self) -> None:
            self._proxy()

        def do_POST(self) -> None:
            self._proxy()

        def do_PUT(self) -> None:
            self._proxy()

        def do_PATCH(self) -> None:
            self._proxy()

        def do_DELETE(self) -> None:
            self._proxy()

        def do_OPTIONS(self) -> None:
            self._proxy()

        def log_message(self, format, *args) -> None:
            return

    _evict_processes_listening_on_port(port=https_port)
    server = ThreadingHTTPServer((host, https_port), ProxyHandler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=ssl_certfile, keyfile=ssl_keyfile)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    def _run() -> None:
        server.serve_forever()

    link = f"https://{host}:{https_port}"
    print(f"MetaList HTTPS listener: {link}")
    thread = threading.Thread(target=_run, name="metalist-https-proxy", daemon=True)
    thread.start()
    return _StartedHttpsProxy(server=server, thread=thread)

def main(argv: list[str]) -> None:
    # Configure logging to filter noisy polling endpoints
    logging.getLogger("uvicorn.access").addFilter(FilterCheckUpdates())
    _record_self_executable_for_namespace_launch()
    assert_startup_sanity(Path(__file__).resolve().parent)
    original_environ = dict(os.environ)
    cli_args = apply_main_cli_args_to_environ(argv=argv, environ=os.environ)
    if _should_open_or_launch_all_namespaces(
        original_environ=original_environ,
        cli_args=cli_args,
    ):
        ensure_default_tls_pair(environ=os.environ)
        launch_results = open_or_launch_all_namespaces(environ=os.environ)
        _print_namespace_bootstrap_results(environ=os.environ, launch_results=launch_results)
        return
    database_runtime_config = resolve_database_runtime_config(
        environ=os.environ,
        argv=argv,
    )
    if not database_runtime_config.test_mode:
        prepare_database_runtime_path(database_path=database_runtime_config.database_path)
        ensure_default_tls_pair(environ=os.environ)

    main_server_config = resolve_main_server_config(environ=os.environ)
    default_mcp_url = resolve_main_mcp_url(
        environ=os.environ,
        host=main_server_config.host,
        port=main_server_config.port,
    )
    from app.main import app as metalist_app
    _start_agent_web_sidecar(default_mcp_url=default_mcp_url)
    print(
        "MetaList resolved config: "
        f"namespace={database_runtime_config.namespace!r} "
        f"database={database_runtime_config.database_path.expanduser()} "
        f"host={main_server_config.host} "
        f"http_port={main_server_config.port} "
        f"https_port={main_server_config.https_port} "
        f"mcp_url={default_mcp_url} "
        f"ssl_certfile={main_server_config.ssl_certfile!r} "
        f"ssl_keyfile={main_server_config.ssl_keyfile!r}"
    )
    if main_server_config.https_port is not None:
        assert main_server_config.ssl_certfile is not None
        assert main_server_config.ssl_keyfile is not None
        _start_https_proxy_server(
            host=main_server_config.host,
            https_port=main_server_config.https_port,
            backend_host=resolve_backend_connect_host(host=main_server_config.host),
            backend_port=main_server_config.port,
            ssl_certfile=main_server_config.ssl_certfile,
            ssl_keyfile=main_server_config.ssl_keyfile,
        )
        print(
            f"MetaList HTTP listener: http://{main_server_config.host}:{main_server_config.port}"
        )
    print(
        "MetaList local URL: "
        f"http://{resolve_local_browser_host(host=main_server_config.host)}:{main_server_config.port}"
    )
    _run_main_listener(
        app_object=metalist_app,
        host=main_server_config.host,
        port=main_server_config.port,
        proxy_headers=main_server_config.proxy_headers,
        forwarded_allow_ips=main_server_config.forwarded_allow_ips,
        ssl_certfile=None,
        ssl_keyfile=None,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
