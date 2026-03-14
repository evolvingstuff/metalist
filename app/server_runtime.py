from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CERT_PATH = _PROJECT_ROOT / "certs" / "metalist-cert.pem"
_DEFAULT_KEY_PATH = _PROJECT_ROOT / "certs" / "metalist-key.pem"
_LOOPBACK_BIND_HOSTS = frozenset({"127.0.0.1", "localhost", "0.0.0.0", "::1"})


@dataclass(frozen=True)
class MainServerConfig:
    host: str
    port: int
    https_port: int | None
    proxy_headers: bool
    forwarded_allow_ips: str
    ssl_certfile: str | None
    ssl_keyfile: str | None


def _read_text(*, environ: Mapping[str, str], name: str, fallback: str) -> str:
    if name in environ:
        value = environ[name]
    else:
        value = fallback
    stripped = value.strip()
    if stripped == "":
        raise RuntimeError(f"{name} must not be empty")
    return stripped


def _read_optional_text(*, environ: Mapping[str, str], name: str) -> str | None:
    if name not in environ:
        return None
    stripped = environ[name].strip()
    if stripped == "":
        raise RuntimeError(f"{name} must not be empty")
    return stripped


def _read_int(*, environ: Mapping[str, str], name: str, fallback: int) -> int:
    if name in environ:
        raw_value = environ[name]
    else:
        raw_value = str(fallback)
    value = raw_value.strip()
    if value == "":
        raise RuntimeError(f"{name} must not be empty")
    if not value.isdigit():
        raise RuntimeError(f"{name} must be numeric, got: {value!r}")
    parsed = int(value)
    if not 0 < parsed < 65536:
        raise RuntimeError(f"{name} must be between 1 and 65535, got: {parsed}")
    return parsed


def _read_optional_int(*, environ: Mapping[str, str], name: str) -> int | None:
    raw_value = _read_optional_text(environ=environ, name=name)
    if raw_value is None:
        return None
    if not raw_value.isdigit():
        raise RuntimeError(f"{name} must be numeric, got: {raw_value!r}")
    parsed = int(raw_value)
    if not 0 < parsed < 65536:
        raise RuntimeError(f"{name} must be between 1 and 65535, got: {parsed}")
    return parsed


def _read_flag(*, environ: Mapping[str, str], name: str, fallback: bool) -> bool:
    if name in environ:
        raw_value = environ[name]
    else:
        raw_value = "1" if fallback else "0"
    value = raw_value.strip().lower()
    if value == "":
        raise RuntimeError(f"{name} must not be empty")
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean env flag {name}={value!r}")


def _resolve_existing_file(*, path_text: str, env_name: str) -> str:
    path = Path(path_text).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"{env_name} file not found: {path}")
    return str(path)


def _format_host_for_url(*, host: str) -> str:
    if ":" in host and not host.startswith("[") and not host.endswith("]"):
        return f"[{host}]"
    return host


def _is_loopback_host(*, host: str) -> bool:
    normalized = host.strip().casefold()
    if normalized == "":
        return False
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _resolve_tls_pair(*, environ: Mapping[str, str]) -> tuple[str | None, str | None]:
    cert_env_value = _read_optional_text(environ=environ, name="METALIST_SSL_CERTFILE")
    key_env_value = _read_optional_text(environ=environ, name="METALIST_SSL_KEYFILE")
    if cert_env_value is None:
        cert_env_value = _read_optional_text(environ=environ, name="METALIST_TLS_CERT")
    if key_env_value is None:
        key_env_value = _read_optional_text(environ=environ, name="METALIST_TLS_KEY")

    if (cert_env_value is None) != (key_env_value is None):
        raise RuntimeError(
            "METALIST_SSL_CERTFILE/METALIST_TLS_CERT and "
            "METALIST_SSL_KEYFILE/METALIST_TLS_KEY must be set together",
        )

    if cert_env_value is not None and key_env_value is not None:
        return (
            _resolve_existing_file(
                path_text=cert_env_value,
                env_name="METALIST_SSL_CERTFILE/METALIST_TLS_CERT",
            ),
            _resolve_existing_file(
                path_text=key_env_value,
                env_name="METALIST_SSL_KEYFILE/METALIST_TLS_KEY",
            ),
        )

    if _DEFAULT_CERT_PATH.is_file() and _DEFAULT_KEY_PATH.is_file():
        return (str(_DEFAULT_CERT_PATH), str(_DEFAULT_KEY_PATH))
    return (None, None)


def _resolve_https_port(*, environ: Mapping[str, str], ssl_certfile: str | None) -> int | None:
    https_port = _read_optional_int(environ=environ, name="METALIST_HTTPS_PORT")
    if https_port is not None:
        return https_port
    if ssl_certfile is not None:
        return 8443
    return None


def resolve_main_server_config(*, environ: Mapping[str, str]) -> MainServerConfig:
    ssl_certfile, ssl_keyfile = _resolve_tls_pair(environ=environ)

    host = _read_text(environ=environ, name="METALIST_HOST", fallback="0.0.0.0")
    port = _read_int(environ=environ, name="METALIST_PORT", fallback=8000)
    https_port = _resolve_https_port(environ=environ, ssl_certfile=ssl_certfile)
    proxy_headers = _read_flag(environ=environ, name="METALIST_PROXY_HEADERS", fallback=True)
    forwarded_allow_ips = _read_text(
        environ=environ,
        name="METALIST_FORWARDED_ALLOW_IPS",
        fallback="127.0.0.1,::1",
    )
    if https_port is not None and ssl_certfile is None:
        raise RuntimeError(
            "METALIST_HTTPS_PORT requires TLS certs via "
            "METALIST_SSL_CERTFILE/METALIST_TLS_CERT or certs/metalist-cert.pem",
        )
    if https_port is not None and https_port == port:
        raise RuntimeError("METALIST_HTTPS_PORT must differ from METALIST_PORT")

    return MainServerConfig(
        host=host,
        port=port,
        https_port=https_port,
        proxy_headers=proxy_headers,
        forwarded_allow_ips=forwarded_allow_ips,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


def resolve_https_redirect_url(
    *,
    environ: Mapping[str, str],
    request_scheme: str,
    request_host: str | None,
    request_path: str,
    request_query: str,
) -> str | None:
    ssl_certfile, _ = _resolve_tls_pair(environ=environ)
    https_port = _resolve_https_port(environ=environ, ssl_certfile=ssl_certfile)
    if https_port is None:
        return None

    scheme = request_scheme.strip().lower()
    if scheme == "":
        raise RuntimeError("request_scheme must not be empty")
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"Unsupported request scheme: {request_scheme!r}")
    if scheme != "http":
        return None
    if request_host is None or request_host.strip() == "":
        raise RuntimeError("request_host must not be empty when HTTPS redirect is enabled")
    if _is_loopback_host(host=request_host):
        return None

    formatted_host = _format_host_for_url(host=request_host.strip())
    query_suffix = ""
    if request_query != "":
        query_suffix = f"?{request_query}"
    return f"https://{formatted_host}:{https_port}{request_path}{query_suffix}"


def resolve_mcp_agent_public_origin(
    *,
    environ: Mapping[str, str],
    request_scheme: str,
    request_host: str | None,
) -> str:
    public_origin = _read_optional_text(environ=environ, name="MCP_AGENT_PUBLIC_ORIGIN")
    if public_origin is not None:
        parsed = urlsplit(public_origin)
        if parsed.scheme not in {"http", "https"}:
            raise RuntimeError(
                "MCP_AGENT_PUBLIC_ORIGIN must start with http:// or https://",
            )
        if parsed.netloc == "":
            raise RuntimeError("MCP_AGENT_PUBLIC_ORIGIN must include a host")
        if parsed.path not in {"", "/"}:
            raise RuntimeError("MCP_AGENT_PUBLIC_ORIGIN must not include a path")
        if parsed.query != "" or parsed.fragment != "":
            raise RuntimeError("MCP_AGENT_PUBLIC_ORIGIN must not include query or fragment")
        return public_origin.rstrip("/")

    configured_host = _read_text(
        environ=environ,
        name="MCP_AGENT_WEB_HOST",
        fallback="127.0.0.1",
    )
    configured_port = _read_int(
        environ=environ,
        name="MCP_AGENT_WEB_PORT",
        fallback=8765,
    )
    resolved_host = configured_host
    if configured_host in _LOOPBACK_BIND_HOSTS and request_host is not None:
        stripped_request_host = request_host.strip()
        if stripped_request_host != "":
            resolved_host = stripped_request_host

    scheme = request_scheme.strip().lower()
    if scheme == "":
        raise RuntimeError("request_scheme must not be empty")
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"Unsupported request scheme: {request_scheme!r}")

    formatted_host = _format_host_for_url(host=resolved_host)
    return f"{scheme}://{formatted_host}:{configured_port}"
