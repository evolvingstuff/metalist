from __future__ import annotations

import pytest

import app.server_runtime as server_runtime
from app.server_runtime import apply_main_cli_args_to_environ
from app.server_runtime import apply_namespace_arg_to_environ
from app.server_runtime import resolve_database_runtime_config
from app.server_runtime import resolve_main_server_config
from app.server_runtime import resolve_main_mcp_url
from app.server_runtime import resolve_request_host_for_https_redirect
from app.server_runtime import resolve_https_redirect_url
from app.server_runtime import resolve_mcp_agent_public_origin


def test_resolve_main_server_config_defaults_to_lan_http_without_tls(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_CERT_PATH", tmp_path / "missing-cert.pem")
    monkeypatch.setattr(server_runtime, "_DEFAULT_KEY_PATH", tmp_path / "missing-key.pem")

    config = resolve_main_server_config(environ={})

    assert config.host == "0.0.0.0"
    assert config.port == 8000
    assert config.https_port is None
    assert config.proxy_headers is True
    assert config.forwarded_allow_ips == "127.0.0.1,::1"
    assert config.ssl_certfile is None
    assert config.ssl_keyfile is None


def test_resolve_main_server_config_accepts_remote_bind_and_tls_files(tmp_path) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")

    config = resolve_main_server_config(
        environ={
            "METALIST_HOST": "0.0.0.0",
            "METALIST_PORT": "8443",
            "METALIST_HTTPS_PORT": "9443",
            "METALIST_PROXY_HEADERS": "0",
            "METALIST_FORWARDED_ALLOW_IPS": "10.0.0.10",
            "METALIST_TLS_CERT": str(cert_path),
            "METALIST_TLS_KEY": str(key_path),
        }
    )

    assert config.host == "0.0.0.0"
    assert config.port == 8443
    assert config.https_port == 9443
    assert config.proxy_headers is False
    assert config.forwarded_allow_ips == "10.0.0.10"
    assert config.ssl_certfile == str(cert_path)
    assert config.ssl_keyfile == str(key_path)


def test_resolve_main_server_config_requires_cert_and_key_together() -> None:
    with pytest.raises(
        RuntimeError,
        match="must be set together",
    ):
        resolve_main_server_config(
            environ={"METALIST_SSL_CERTFILE": "/tmp/cert.pem"},
        )


def test_resolve_main_server_config_requires_tls_when_https_port_is_set(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_CERT_PATH", tmp_path / "missing-cert.pem")
    monkeypatch.setattr(server_runtime, "_DEFAULT_KEY_PATH", tmp_path / "missing-key.pem")

    with pytest.raises(
        RuntimeError,
        match="METALIST_HTTPS_PORT requires TLS certs",
    ):
        resolve_main_server_config(
            environ={"METALIST_HTTPS_PORT": "3443"},
        )


def test_resolve_main_server_config_uses_default_cert_paths(tmp_path, monkeypatch) -> None:
    cert_path = tmp_path / "metalist-cert.pem"
    key_path = tmp_path / "metalist-key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")
    monkeypatch.setattr(server_runtime, "_DEFAULT_CERT_PATH", cert_path)
    monkeypatch.setattr(server_runtime, "_DEFAULT_KEY_PATH", key_path)

    config = resolve_main_server_config(
        environ={},
    )

    assert config.host == "0.0.0.0"
    assert config.port == 8000
    assert config.https_port == 8443
    assert config.ssl_certfile == str(cert_path)
    assert config.ssl_keyfile == str(key_path)


def test_resolve_main_server_config_enables_https_for_remote_bind_when_default_certs_exist(
    tmp_path,
    monkeypatch,
) -> None:
    cert_path = tmp_path / "metalist-cert.pem"
    key_path = tmp_path / "metalist-key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")
    monkeypatch.setattr(server_runtime, "_DEFAULT_CERT_PATH", cert_path)
    monkeypatch.setattr(server_runtime, "_DEFAULT_KEY_PATH", key_path)

    config = resolve_main_server_config(
        environ={"METALIST_HOST": "0.0.0.0"},
    )

    assert config.host == "0.0.0.0"
    assert config.port == 8000
    assert config.https_port == 8443
    assert config.ssl_certfile == str(cert_path)
    assert config.ssl_keyfile == str(key_path)


def test_resolve_database_runtime_config_defaults_to_legacy_database_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)

    config = resolve_database_runtime_config(
        environ={},
        argv=[],
    )

    assert config.test_mode is False
    assert config.namespace is None
    assert config.database_path == tmp_path / "metalist2.db"
    assert config.database_url == f"sqlite:///{tmp_path / 'metalist2.db'}"


def test_resolve_database_runtime_config_uses_namespaced_database_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)

    config = resolve_database_runtime_config(
        environ={"METALIST_NAMESPACE": "work"},
        argv=[],
    )

    assert config.test_mode is False
    assert config.namespace == "work"
    assert config.database_path == tmp_path / "work.metalist.db"
    assert config.database_url == f"sqlite:///{tmp_path / 'work.metalist.db'}"


def test_resolve_database_runtime_config_rejects_invalid_namespace() -> None:
    with pytest.raises(
        RuntimeError,
        match="Namespace must contain only lowercase letters, digits, and '-'",
    ):
        resolve_database_runtime_config(
            environ={"METALIST_NAMESPACE": "Work.Space"},
            argv=[],
        )


def test_resolve_database_runtime_config_rejects_namespace_in_test_mode() -> None:
    with pytest.raises(
        RuntimeError,
        match="Namespace selection cannot be combined with TEST_MODE or --test",
    ):
        resolve_database_runtime_config(
            environ={"METALIST_NAMESPACE": "work"},
            argv=["--test"],
        )


def test_apply_main_cli_args_to_environ_sets_namespace_and_ports() -> None:
    environ: dict[str, str] = {}

    parsed = apply_main_cli_args_to_environ(
        argv=[
            "--namespace",
            "work",
            "--port",
            "8123",
            "--https-port",
            "8444",
            "--mcp-port",
            "8766",
        ],
        environ=environ,
    )

    assert parsed.namespace == "work"
    assert parsed.port == 8123
    assert parsed.https_port == 8444
    assert parsed.mcp_port == 8766
    assert parsed.test_mode is False
    assert environ["METALIST_NAMESPACE"] == "work"
    assert environ["METALIST_PORT"] == "8123"
    assert environ["METALIST_HTTPS_PORT"] == "8444"
    assert environ["MCP_AGENT_WEB_PORT"] == "8766"


def test_apply_main_cli_args_to_environ_rejects_namespace_in_test_mode() -> None:
    with pytest.raises(
        RuntimeError,
        match="Namespace selection cannot be combined with TEST_MODE or --test",
    ):
        apply_main_cli_args_to_environ(
            argv=["--namespace", "work", "--test"],
            environ={},
        )


def test_apply_namespace_arg_to_environ_bootstraps_known_args_only() -> None:
    environ: dict[str, str] = {}

    namespace = apply_namespace_arg_to_environ(
        argv=["--namespace", "work", "--input", "/tmp/example.json"],
        environ=environ,
    )

    assert namespace == "work"
    assert environ["METALIST_NAMESPACE"] == "work"


def test_resolve_main_mcp_url_tracks_main_app_port_and_prefix() -> None:
    mcp_url = resolve_main_mcp_url(
        environ={"API_PREFIX": "/api3"},
        host="0.0.0.0",
        port=8123,
    )

    assert mcp_url == "http://127.0.0.1:8123/api3/mcp"


def test_resolve_request_host_for_https_redirect_prefers_browser_host_header() -> None:
    request_host = resolve_request_host_for_https_redirect(
        host_header="localhost:8000",
        forwarded_host_header=None,
        fallback_host="0.0.0.0",
    )

    assert request_host == "localhost"


def test_resolve_https_redirect_url_does_not_redirect_localhost_host_header_when_bind_host_is_wildcard() -> None:
    request_host = resolve_request_host_for_https_redirect(
        host_header="localhost:8000",
        forwarded_host_header=None,
        fallback_host="0.0.0.0",
    )

    redirect_url = resolve_https_redirect_url(
        environ={"METALIST_HTTPS_PORT": "3443", "METALIST_HOST": "0.0.0.0"},
        request_scheme="http",
        request_host=request_host,
        request_path="/",
        request_query="",
    )

    assert redirect_url is None


def test_resolve_https_redirect_url_redirects_remote_http_requests_by_hostname() -> None:
    redirect_url = resolve_https_redirect_url(
        environ={"METALIST_HTTPS_PORT": "3443"},
        request_scheme="http",
        request_host="192.168.1.25",
        request_path="/",
        request_query="",
    )

    assert redirect_url == "https://192.168.1.25:3443/"


def test_resolve_https_redirect_url_uses_default_https_port_when_default_certs_exist(
    tmp_path,
    monkeypatch,
) -> None:
    cert_path = tmp_path / "metalist-cert.pem"
    key_path = tmp_path / "metalist-key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")
    monkeypatch.setattr(server_runtime, "_DEFAULT_CERT_PATH", cert_path)
    monkeypatch.setattr(server_runtime, "_DEFAULT_KEY_PATH", key_path)

    redirect_url = resolve_https_redirect_url(
        environ={"METALIST_HOST": "0.0.0.0"},
        request_scheme="http",
        request_host="10.0.0.31",
        request_path="/notes",
        request_query="a=1",
    )

    assert redirect_url == "https://10.0.0.31:8443/notes?a=1"


def test_resolve_https_redirect_url_does_not_redirect_localhost_http_requests() -> None:
    redirect_url = resolve_https_redirect_url(
        environ={"METALIST_HTTPS_PORT": "3443"},
        request_scheme="http",
        request_host="127.0.0.1",
        request_path="/notes",
        request_query="a=1",
    )

    assert redirect_url is None


def test_resolve_mcp_agent_public_origin_uses_explicit_origin() -> None:
    origin = resolve_mcp_agent_public_origin(
        environ={"MCP_AGENT_PUBLIC_ORIGIN": "https://notes.example.com"},
        request_scheme="https",
        request_host="notes.example.com",
    )

    assert origin == "https://notes.example.com"


def test_resolve_mcp_agent_public_origin_maps_loopback_to_request_host() -> None:
    origin = resolve_mcp_agent_public_origin(
        environ={"MCP_AGENT_WEB_PORT": "8765"},
        request_scheme="https",
        request_host="laptop.example.com",
    )

    assert origin == "https://laptop.example.com:8765"
