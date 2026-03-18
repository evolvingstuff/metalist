from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType

import main as main_entrypoint
import pytest
from app.server_runtime import DatabaseRuntimeConfig
from app.server_runtime import MainServerConfig


def test_main_generates_default_tls_pair_on_normal_startup(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    fake_app_module = ModuleType("app.main")
    fake_app_object = object()
    fake_app_module.app = fake_app_object
    monkeypatch.setitem(sys.modules, "app.main", fake_app_module)

    def fake_apply_main_cli_args_to_environ(*, argv, environ) -> None:
        calls.append("apply_main_cli_args_to_environ")

    def fake_resolve_database_runtime_config(*, environ, argv) -> DatabaseRuntimeConfig:
        calls.append("resolve_database_runtime_config")
        return DatabaseRuntimeConfig(
            database_path=tmp_path / "default.metalist.db",
            database_url=f"sqlite:///{tmp_path / 'default.metalist.db'}",
            namespace="default",
            test_mode=False,
        )

    def fake_prepare_database_runtime_path(*, database_path: Path) -> None:
        assert database_path == tmp_path / "default.metalist.db"
        calls.append("prepare_database_runtime_path")

    def fake_ensure_default_tls_pair(*, environ) -> None:
        calls.append("ensure_default_tls_pair")

    def fake_resolve_main_server_config(*, environ) -> MainServerConfig:
        calls.append("resolve_main_server_config")
        return MainServerConfig(
            host="127.0.0.1",
            port=18000,
            https_port=None,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1,::1",
            ssl_certfile=None,
            ssl_keyfile=None,
        )

    def fake_resolve_main_mcp_url(*, environ, host: str, port: int) -> str:
        assert host == "127.0.0.1"
        assert port == 18000
        calls.append("resolve_main_mcp_url")
        return "http://127.0.0.1:18000/api2/mcp"

    def fake_start_agent_web_sidecar(*, default_mcp_url: str) -> None:
        assert default_mcp_url == "http://127.0.0.1:18000/api2/mcp"
        calls.append("_start_agent_web_sidecar")

    def fake_run_main_listener(
        *,
        app_object,
        host: str,
        port: int,
        proxy_headers: bool,
        forwarded_allow_ips: str,
        ssl_certfile,
        ssl_keyfile,
    ) -> None:
        assert app_object is fake_app_object
        assert host == "127.0.0.1"
        assert port == 18000
        assert proxy_headers is True
        assert forwarded_allow_ips == "127.0.0.1,::1"
        assert ssl_certfile is None
        assert ssl_keyfile is None
        calls.append("_run_main_listener")

    monkeypatch.setattr(main_entrypoint, "apply_main_cli_args_to_environ", fake_apply_main_cli_args_to_environ)
    monkeypatch.setattr(
        main_entrypoint,
        "resolve_database_runtime_config",
        fake_resolve_database_runtime_config,
    )
    monkeypatch.setattr(main_entrypoint, "prepare_database_runtime_path", fake_prepare_database_runtime_path)
    monkeypatch.setattr(main_entrypoint, "ensure_default_tls_pair", fake_ensure_default_tls_pair)
    monkeypatch.setattr(main_entrypoint, "resolve_main_server_config", fake_resolve_main_server_config)
    monkeypatch.setattr(main_entrypoint, "resolve_main_mcp_url", fake_resolve_main_mcp_url)
    monkeypatch.setattr(main_entrypoint, "_start_agent_web_sidecar", fake_start_agent_web_sidecar)
    monkeypatch.setattr(main_entrypoint, "_run_main_listener", fake_run_main_listener)
    monkeypatch.setattr(main_entrypoint, "_record_self_executable_for_namespace_launch", lambda: calls.append("_record_self_executable_for_namespace_launch"))

    main_entrypoint.main(argv=[])

    assert calls == [
        "_record_self_executable_for_namespace_launch",
        "apply_main_cli_args_to_environ",
        "resolve_database_runtime_config",
        "prepare_database_runtime_path",
        "ensure_default_tls_pair",
        "resolve_main_server_config",
        "resolve_main_mcp_url",
        "_start_agent_web_sidecar",
        "_run_main_listener",
    ]


def test_main_skips_default_tls_generation_in_test_mode(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    fake_app_module = ModuleType("app.main")
    fake_app_module.app = object()
    monkeypatch.setitem(sys.modules, "app.main", fake_app_module)

    def fake_resolve_database_runtime_config(*, environ, argv) -> DatabaseRuntimeConfig:
        calls.append("resolve_database_runtime_config")
        return DatabaseRuntimeConfig(
            database_path=tmp_path / "test.db",
            database_url="sqlite:///./test.db",
            namespace=None,
            test_mode=True,
        )

    def fail_prepare_database_runtime_path(*, database_path: Path) -> None:
        raise AssertionError("prepare_database_runtime_path should not run in test mode")

    def fail_ensure_default_tls_pair(*, environ) -> None:
        raise AssertionError("ensure_default_tls_pair should not run in test mode")

    def fake_resolve_main_server_config(*, environ) -> MainServerConfig:
        calls.append("resolve_main_server_config")
        return MainServerConfig(
            host="127.0.0.1",
            port=18000,
            https_port=None,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1,::1",
            ssl_certfile=None,
            ssl_keyfile=None,
        )

    monkeypatch.setattr(main_entrypoint, "apply_main_cli_args_to_environ", lambda *, argv, environ: calls.append("apply_main_cli_args_to_environ"))
    monkeypatch.setattr(
        main_entrypoint,
        "resolve_database_runtime_config",
        fake_resolve_database_runtime_config,
    )
    monkeypatch.setattr(main_entrypoint, "prepare_database_runtime_path", fail_prepare_database_runtime_path)
    monkeypatch.setattr(main_entrypoint, "ensure_default_tls_pair", fail_ensure_default_tls_pair)
    monkeypatch.setattr(main_entrypoint, "resolve_main_server_config", fake_resolve_main_server_config)
    monkeypatch.setattr(
        main_entrypoint,
        "resolve_main_mcp_url",
        lambda *, environ, host, port: calls.append("resolve_main_mcp_url") or "http://127.0.0.1:18000/api2/mcp",
    )
    monkeypatch.setattr(main_entrypoint, "_start_agent_web_sidecar", lambda *, default_mcp_url: calls.append("_start_agent_web_sidecar"))
    monkeypatch.setattr(
        main_entrypoint,
        "_run_main_listener",
        lambda **kwargs: calls.append("_run_main_listener"),
    )
    monkeypatch.setattr(main_entrypoint, "_record_self_executable_for_namespace_launch", lambda: calls.append("_record_self_executable_for_namespace_launch"))

    main_entrypoint.main(argv=["--test"])

    assert calls == [
        "_record_self_executable_for_namespace_launch",
        "apply_main_cli_args_to_environ",
        "resolve_database_runtime_config",
        "resolve_main_server_config",
        "resolve_main_mcp_url",
        "_start_agent_web_sidecar",
        "_run_main_listener",
    ]


def test_find_listening_pids_for_port_returns_unique_listener_pids(monkeypatch) -> None:
    class _Completed:
        returncode = 0
        stdout = "123\n123\n456\n"
        stderr = ""

    monkeypatch.setattr(main_entrypoint.shutil, "which", lambda name: "/usr/sbin/lsof")
    monkeypatch.setattr(main_entrypoint.subprocess, "run", lambda *args, **kwargs: _Completed())

    assert main_entrypoint._find_listening_pids_for_port(port=8443) == [123, 456]


def test_evict_processes_listening_on_port_stops_foreign_pids(monkeypatch) -> None:
    stopped_pids: list[int] = []

    monkeypatch.setattr(main_entrypoint, "_find_listening_pids_for_port", lambda *, port: [2345, 6789])
    monkeypatch.setattr(main_entrypoint.os, "getpid", lambda: 9999)
    monkeypatch.setattr(main_entrypoint, "_stop_process", lambda *, pid: stopped_pids.append(pid))

    main_entrypoint._evict_processes_listening_on_port(port=8443)

    assert stopped_pids == [2345, 6789]


def test_run_main_listener_evicts_port_conflicts_before_uvicorn(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        main_entrypoint,
        "_evict_processes_listening_on_port",
        lambda *, port: calls.append(("evict", port)),
    )
    monkeypatch.setattr(
        main_entrypoint.uvicorn,
        "run",
        lambda app_object, **kwargs: calls.append(("uvicorn", kwargs["port"])),
    )

    main_entrypoint._run_main_listener(
        app_object=object(),
        host="127.0.0.1",
        port=18000,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1,::1",
        ssl_certfile=None,
        ssl_keyfile=None,
    )

    assert calls == [
        ("evict", 18000),
        ("uvicorn", 18000),
    ]


def test_start_https_proxy_server_evicts_port_conflicts_before_bind(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class _FakeServer:
        def __init__(self, server_address, handler_class) -> None:
            calls.append(("server_address", server_address))
            self.socket = "raw-socket"
            self.daemon_threads = False

        def serve_forever(self) -> None:
            calls.append(("serve_forever", None))

    class _FakeSslContext:
        def __init__(self, protocol) -> None:
            calls.append(("ssl_protocol", protocol))

        def load_cert_chain(self, *, certfile, keyfile) -> None:
            calls.append(("load_cert_chain", (certfile, keyfile)))

        def wrap_socket(self, socket, server_side):
            calls.append(("wrap_socket", (socket, server_side)))
            return "wrapped-socket"

    class _FakeThread:
        def __init__(self, *, target, name, daemon) -> None:
            calls.append(("thread_init", (name, daemon)))
            self.target = target
            self.started = False

        def start(self) -> None:
            self.started = True
            calls.append(("thread_start", None))

    monkeypatch.setattr(
        main_entrypoint,
        "_evict_processes_listening_on_port",
        lambda *, port: calls.append(("evict", port)),
    )
    monkeypatch.setattr(main_entrypoint, "ThreadingHTTPServer", _FakeServer)
    monkeypatch.setattr(main_entrypoint.ssl, "SSLContext", _FakeSslContext)
    monkeypatch.setattr(main_entrypoint.threading, "Thread", _FakeThread)

    started_proxy = main_entrypoint._start_https_proxy_server(
        host="0.0.0.0",
        https_port=8443,
        backend_host="127.0.0.1",
        backend_port=8000,
        ssl_certfile="/tmp/cert.pem",
        ssl_keyfile="/tmp/key.pem",
    )

    assert calls == [
        ("evict", 8443),
        ("server_address", ("0.0.0.0", 8443)),
        ("ssl_protocol", main_entrypoint.ssl.PROTOCOL_TLS_SERVER),
        ("load_cert_chain", ("/tmp/cert.pem", "/tmp/key.pem")),
        ("wrap_socket", ("raw-socket", True)),
        ("thread_init", ("metalist-https-proxy", True)),
        ("thread_start", None),
    ]
    assert started_proxy.server.socket == "wrapped-socket"
    assert started_proxy.thread.started is True


def test_evict_processes_listening_on_port_raises_if_current_process_owns_listener(monkeypatch) -> None:
    monkeypatch.setattr(main_entrypoint, "_find_listening_pids_for_port", lambda *, port: [4321])
    monkeypatch.setattr(main_entrypoint.os, "getpid", lambda: 4321)

    with pytest.raises(RuntimeError, match="current MetaList process"):
        main_entrypoint._evict_processes_listening_on_port(port=8443)
