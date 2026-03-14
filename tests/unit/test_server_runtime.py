from __future__ import annotations

import pytest

import app.server_runtime as server_runtime
from app.server_runtime import resolve_main_server_config
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
