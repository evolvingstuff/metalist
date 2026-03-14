import uvicorn
import logging
import os
import threading
import http.client
import ssl
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

from app.server_runtime import resolve_main_server_config
from mcp_client import create_web_app
from mcp_client import DEFAULT_MAX_STEPS
from mcp_client import DEFAULT_MAX_EXPRESSIONS
from mcp_client import DEFAULT_HYDRATE_TOP_K
from mcp_client import DEFAULT_MCP_URL
from mcp_client import DEFAULT_OLLAMA_CHAT_URL
from mcp_client import DEFAULT_OLLAMA_MODEL
from mcp_client import DEFAULT_REGEX_ENGINE
from mcp_client import DEFAULT_SEARCH_CONTEXT_QUERY
from mcp_client import DEFAULT_WEB_HOST
from mcp_client import DEFAULT_WEB_PORT
from mcp_client import reset_local_ollama_server


@dataclass(frozen=True)
class _StartedHttpsProxy:
    server: ThreadingHTTPServer
    thread: threading.Thread

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


def _start_agent_web_sidecar() -> None:
    enabled = _env_flag("MCP_AGENT_WEB_ENABLED", True)
    if not enabled:
        print("Agent web app sidecar disabled (MCP_AGENT_WEB_ENABLED=0)")
        return

    if "MCP_AGENT_WEB_HOST" in os.environ:
        host = os.environ["MCP_AGENT_WEB_HOST"]
    else:
        host = DEFAULT_WEB_HOST
    port = _env_int("MCP_AGENT_WEB_PORT", DEFAULT_WEB_PORT)
    if "MCP_AGENT_OLLAMA_MODEL" in os.environ:
        model = os.environ["MCP_AGENT_OLLAMA_MODEL"]
    else:
        model = DEFAULT_OLLAMA_MODEL
    if "MCP_AGENT_MCP_URL" in os.environ:
        mcp_url = os.environ["MCP_AGENT_MCP_URL"]
    else:
        mcp_url = DEFAULT_MCP_URL
    if "MCP_AGENT_OLLAMA_CHAT_URL" in os.environ:
        ollama_chat_url = os.environ["MCP_AGENT_OLLAMA_CHAT_URL"]
    else:
        ollama_chat_url = DEFAULT_OLLAMA_CHAT_URL
    max_steps = _env_int("MCP_AGENT_MAX_STEPS", DEFAULT_MAX_STEPS)
    max_expressions = _env_int(
        "MCP_AGENT_MAX_EXPRESSIONS",
        DEFAULT_MAX_EXPRESSIONS,
    )
    hydrate_top_k = _env_int(
        "MCP_AGENT_HYDRATE_TOP_K",
        DEFAULT_HYDRATE_TOP_K,
    )
    regex_engine = _env_choice(
        "MCP_AGENT_REGEX_ENGINE",
        DEFAULT_REGEX_ENGINE,
        {"python-re", "re2"},
    )
    if "MCP_AGENT_SEARCH_CONTEXT_QUERY" in os.environ:
        search_context_query = os.environ["MCP_AGENT_SEARCH_CONTEXT_QUERY"]
    else:
        search_context_query = DEFAULT_SEARCH_CONTEXT_QUERY
    reset_ollama_on_start = _env_flag("MCP_AGENT_RESET_OLLAMA_ON_START", True)
    if reset_ollama_on_start:
        reset_local_ollama_server(ollama_chat_url=ollama_chat_url)

    agent_app = create_web_app(
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


def _resolve_backend_connect_host(*, host: str) -> str:
    stripped_host = host.strip()
    assert stripped_host != "", "host must not be empty"
    if stripped_host in {"0.0.0.0", "127.0.0.1", "localhost"}:
        return "127.0.0.1"
    if stripped_host == "::":
        return "::1"
    return stripped_host


def _resolve_local_browser_host(*, host: str) -> str:
    stripped_host = host.strip()
    assert stripped_host != "", "host must not be empty"
    if stripped_host in {"0.0.0.0", "127.0.0.1", "localhost"}:
        return "127.0.0.1"
    if stripped_host in {"::", "::1"}:
        return "[::1]"
    return stripped_host


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

if __name__ == "__main__":
    # Configure logging to filter noisy polling endpoints
    logging.getLogger("uvicorn.access").addFilter(FilterCheckUpdates())
    _start_agent_web_sidecar()
    from app.main import app as metalist_app

    main_server_config = resolve_main_server_config(environ=os.environ)
    print(
        "MetaList resolved config: "
        f"host={main_server_config.host} "
        f"http_port={main_server_config.port} "
        f"https_port={main_server_config.https_port} "
        f"ssl_certfile={main_server_config.ssl_certfile!r} "
        f"ssl_keyfile={main_server_config.ssl_keyfile!r}"
    )
    if main_server_config.https_port is not None:
        assert main_server_config.ssl_certfile is not None
        assert main_server_config.ssl_keyfile is not None
        _start_https_proxy_server(
            host=main_server_config.host,
            https_port=main_server_config.https_port,
            backend_host=_resolve_backend_connect_host(host=main_server_config.host),
            backend_port=main_server_config.port,
            ssl_certfile=main_server_config.ssl_certfile,
            ssl_keyfile=main_server_config.ssl_keyfile,
        )
        print(
            f"MetaList HTTP listener: http://{main_server_config.host}:{main_server_config.port}"
        )
    print(
        "MetaList local URL: "
        f"http://{_resolve_local_browser_host(host=main_server_config.host)}:{main_server_config.port}"
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
