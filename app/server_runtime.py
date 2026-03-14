from __future__ import annotations

import argparse
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CERT_PATH = _PROJECT_ROOT / "certs" / "metalist-cert.pem"
_DEFAULT_KEY_PATH = _PROJECT_ROOT / "certs" / "metalist-key.pem"
_LOOPBACK_BIND_HOSTS = frozenset({"127.0.0.1", "localhost", "0.0.0.0", "::1"})
_DEFAULT_API_PREFIX = "/api2"
_DEFAULT_V1_API_PREFIX = "/api"
_DEFAULT_DATABASE_DIRECTORY = Path.home() / "MetaList"
_DEFAULT_DATABASE_FILENAME = "metalist2.db"
_DEFAULT_TEST_DATABASE_URL = "sqlite:///./test.db"
_DEFAULT_TEST_DATABASE_PATH = Path("./test.db")
_NAMESPACE_ENV_NAME = "METALIST_NAMESPACE"
_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class MainServerConfig:
    host: str
    port: int
    https_port: int | None
    proxy_headers: bool
    forwarded_allow_ips: str
    ssl_certfile: str | None
    ssl_keyfile: str | None


@dataclass(frozen=True)
class DatabaseRuntimeConfig:
    database_path: Path
    database_url: str
    namespace: str | None
    test_mode: bool


@dataclass(frozen=True)
class MainCliArgs:
    namespace: str | None
    port: int | None
    https_port: int | None
    mcp_port: int | None
    test_mode: bool


def _parse_port_argument(raw_value: str) -> int:
    value = raw_value.strip()
    if value == "":
        raise argparse.ArgumentTypeError("port must not be empty")
    if not value.isdigit():
        raise argparse.ArgumentTypeError(f"port must be numeric, got: {raw_value!r}")
    parsed = int(value)
    if not 0 < parsed < 65536:
        raise argparse.ArgumentTypeError(f"port must be between 1 and 65535, got: {parsed}")
    return parsed


def _parse_namespace_argument(raw_value: str) -> str:
    try:
        return validate_namespace(namespace=raw_value)
    except RuntimeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def validate_namespace(*, namespace: str) -> str:
    if not isinstance(namespace, str):
        raise TypeError(f"namespace must be a string, got {type(namespace)}")
    normalized = namespace.strip()
    if normalized == "":
        raise RuntimeError("Namespace must not be empty")
    if normalized != normalized.casefold():
        raise RuntimeError("Namespace must contain only lowercase letters, digits, and '-'")
    if _NAMESPACE_PATTERN.fullmatch(normalized) is None:
        raise RuntimeError("Namespace must contain only lowercase letters, digits, and '-'")
    return normalized


def resolve_default_database_path() -> Path:
    return _DEFAULT_DATABASE_DIRECTORY / _DEFAULT_DATABASE_FILENAME


def resolve_namespaced_database_path(*, namespace: str) -> Path:
    normalized = validate_namespace(namespace=namespace)
    return _DEFAULT_DATABASE_DIRECTORY / f"{normalized}.metalist.db"


def resolve_api_prefix(*, environ: Mapping[str, str]) -> str:
    if "API_PREFIX" in environ:
        return environ["API_PREFIX"].rstrip("/")
    return _DEFAULT_API_PREFIX


def resolve_v1_api_prefix(*, environ: Mapping[str, str]) -> str:
    if "V1_API_PREFIX" in environ:
        return environ["V1_API_PREFIX"].rstrip("/")
    return _DEFAULT_V1_API_PREFIX


def resolve_test_mode(*, environ: Mapping[str, str], argv: Sequence[str]) -> bool:
    if "--test" in argv:
        return True
    return environ.get("TEST_MODE") == "1"


def resolve_database_runtime_config(
    *,
    environ: Mapping[str, str],
    argv: Sequence[str],
) -> DatabaseRuntimeConfig:
    test_mode = resolve_test_mode(environ=environ, argv=argv)
    namespace_value = _read_optional_text(environ=environ, name=_NAMESPACE_ENV_NAME)
    namespace: str | None
    if namespace_value is None:
        namespace = None
    else:
        namespace = validate_namespace(namespace=namespace_value)

    if test_mode:
        if namespace is not None:
            raise RuntimeError("Namespace selection cannot be combined with TEST_MODE or --test")
        return DatabaseRuntimeConfig(
            database_path=_DEFAULT_TEST_DATABASE_PATH,
            database_url=_DEFAULT_TEST_DATABASE_URL,
            namespace=None,
            test_mode=True,
        )

    if namespace is None:
        database_path = resolve_default_database_path()
    else:
        database_path = resolve_namespaced_database_path(namespace=namespace)

    return DatabaseRuntimeConfig(
        database_path=database_path,
        database_url=f"sqlite:///{database_path.expanduser()}",
        namespace=namespace,
        test_mode=False,
    )


def apply_namespace_arg_to_environ(
    *,
    argv: Sequence[str],
    environ: MutableMapping[str, str],
) -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--namespace", type=_parse_namespace_argument)
    parsed_args, _ = parser.parse_known_args(list(argv))
    namespace = parsed_args.namespace
    if namespace is None:
        return None
    environ[_NAMESPACE_ENV_NAME] = namespace
    return namespace


def apply_main_cli_args_to_environ(
    *,
    argv: Sequence[str],
    environ: MutableMapping[str, str],
) -> MainCliArgs:
    parser = argparse.ArgumentParser(description="Run the MetaList server")
    parser.add_argument("--namespace", type=_parse_namespace_argument)
    parser.add_argument("--port", type=_parse_port_argument)
    parser.add_argument("--https-port", type=_parse_port_argument)
    parser.add_argument("--mcp-port", type=_parse_port_argument)
    parser.add_argument("--test", action="store_true")
    parsed_args = parser.parse_args(list(argv))

    namespace = parsed_args.namespace
    if namespace is not None and parsed_args.test:
        raise RuntimeError("Namespace selection cannot be combined with TEST_MODE or --test")

    if namespace is not None:
        environ[_NAMESPACE_ENV_NAME] = namespace
    if parsed_args.port is not None:
        environ["METALIST_PORT"] = str(parsed_args.port)
    if parsed_args.https_port is not None:
        environ["METALIST_HTTPS_PORT"] = str(parsed_args.https_port)
    if parsed_args.mcp_port is not None:
        environ["MCP_AGENT_WEB_PORT"] = str(parsed_args.mcp_port)

    return MainCliArgs(
        namespace=namespace,
        port=parsed_args.port,
        https_port=parsed_args.https_port,
        mcp_port=parsed_args.mcp_port,
        test_mode=parsed_args.test,
    )


def resolve_backend_connect_host(*, host: str) -> str:
    stripped_host = host.strip()
    if stripped_host == "":
        raise RuntimeError("host must not be empty")
    if stripped_host in {"0.0.0.0", "127.0.0.1", "localhost"}:
        return "127.0.0.1"
    if stripped_host == "::":
        return "::1"
    return stripped_host


def resolve_local_browser_host(*, host: str) -> str:
    stripped_host = host.strip()
    if stripped_host == "":
        raise RuntimeError("host must not be empty")
    if stripped_host in {"0.0.0.0", "127.0.0.1", "localhost"}:
        return "127.0.0.1"
    if stripped_host in {"::", "::1"}:
        return "[::1]"
    return stripped_host


def resolve_main_mcp_url(*, environ: Mapping[str, str], host: str, port: int) -> str:
    formatted_host = _format_host_for_url(host=resolve_backend_connect_host(host=host))
    api_prefix = resolve_api_prefix(environ=environ)
    return f"http://{formatted_host}:{port}{api_prefix}/mcp"


def resolve_request_host_for_https_redirect(
    *,
    host_header: str | None,
    forwarded_host_header: str | None,
    fallback_host: str | None,
) -> str | None:
    candidate_header: str | None
    if forwarded_host_header is not None and forwarded_host_header.strip() != "":
        candidate_header = forwarded_host_header.split(",", 1)[0].strip()
    elif host_header is not None and host_header.strip() != "":
        candidate_header = host_header.strip()
    else:
        candidate_header = None

    if candidate_header is None:
        return fallback_host

    parsed = urlsplit(f"//{candidate_header}")
    if parsed.hostname is None or parsed.hostname.strip() == "":
        raise RuntimeError(f"Could not parse request host header: {candidate_header!r}")
    return parsed.hostname


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
