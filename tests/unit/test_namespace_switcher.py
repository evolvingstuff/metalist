from __future__ import annotations

from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

import app.server_runtime as server_runtime
import app.services.namespace_switcher as namespace_switcher
from app.server_runtime import delete_namespace_launch_profile
from app.server_runtime import load_namespace_launch_profile
from app.server_runtime import NamespaceLaunchProfile
from app.server_runtime import save_namespace_launch_profile
from app.services.namespace_switcher import build_namespace_catalog
from app.services.namespace_switcher import build_login_namespace_catalog
from app.services.namespace_switcher import delete_current_namespace
from app.services.namespace_switcher import delete_namespace
from app.services.namespace_switcher import open_login_namespace
from app.services.namespace_switcher import open_or_launch_namespace
from app.services.namespace_switcher import open_or_launch_all_namespaces
from app.services.namespace_switcher import save_namespace_port_profiles
from app.services.namespace_switcher import NamespaceOpenResult
from app.services.namespace_switcher import _probe_namespace_status


def _disable_default_tls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_CERT_PATH", tmp_path / "missing-cert.pem")
    monkeypatch.setattr(server_runtime, "_DEFAULT_KEY_PATH", tmp_path / "missing-key.pem")


def test_build_namespace_catalog_suggests_next_free_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="default",
        port=8000,
        https_port=None,
        mcp_port=8765,
    )
    save_namespace_launch_profile(
        namespace="cla",
        port=8001,
        https_port=None,
        mcp_port=8766,
    )

    catalog = build_namespace_catalog(
        environ={},
        current_namespace="default",
    )

    assert catalog["current_namespace"] == "default"
    assert catalog["current_profile"] == {
        "namespace": "default",
        "port": 8000,
        "https_port": None,
        "mcp_port": 8765,
    }
    assert catalog["new_namespace_profile"] == {
        "namespace": "new-namespace",
        "port": 8002,
        "https_port": None,
        "mcp_port": 8767,
    }

    namespaces = {entry["namespace"]: entry for entry in catalog["namespaces"]}
    assert namespaces["default"]["default_profile"] == {
        "namespace": "default",
        "port": 8000,
        "https_port": None,
        "mcp_port": 8765,
    }
    assert namespaces["cla"]["default_profile"] == {
        "namespace": "cla",
        "port": 8001,
        "https_port": None,
        "mcp_port": 8766,
    }


def test_build_namespace_catalog_includes_existing_database_without_saved_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    database_path = server_runtime.resolve_namespaced_database_path(namespace="work")
    server_runtime.prepare_database_runtime_path(database_path=database_path)
    database_path.write_text("", encoding="utf-8")

    catalog = build_namespace_catalog(
        environ={},
        current_namespace="default",
    )

    namespaces = {entry["namespace"]: entry for entry in catalog["namespaces"]}
    assert namespaces["work"]["database_exists"] is True
    assert namespaces["work"]["has_launch_profile"] is False
    assert namespaces["work"]["default_profile"] == {
        "namespace": "work",
        "port": 8001,
        "https_port": None,
        "mcp_port": 8766,
    }


def test_build_login_namespace_catalog_returns_plain_namespace_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="default",
        port=8000,
        https_port=None,
        mcp_port=8765,
    )
    save_namespace_launch_profile(
        namespace="cla",
        port=8001,
        https_port=None,
        mcp_port=8766,
    )

    catalog = build_login_namespace_catalog(
        environ={},
        current_namespace="default",
    )

    assert catalog == {
        "current_namespace": "default",
        "namespaces": ["default", "cla"],
    }


def test_open_or_launch_namespace_rejects_reserved_current_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)

    with pytest.raises(
        RuntimeError,
        match="HTTP port 8000 conflicts with HTTP port reserved for namespace default",
    ):
        open_or_launch_namespace(
            environ={},
            current_namespace="default",
            namespace="work",
            port=8000,
            https_port=None,
            mcp_port=8766,
        )


def test_open_or_launch_namespace_launches_new_process_and_saves_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    launched: list[tuple[str, int, int]] = []
    waited: list[tuple[str, int]] = []

    def _fake_launch(*, environ, chosen_profile):
        launched.append((chosen_profile.namespace, chosen_profile.port, chosen_profile.mcp_port))

    def _fake_wait(*, environ, namespace, port):
        waited.append((namespace, port))

    monkeypatch.setattr(namespace_switcher, "_find_running_namespace_port", lambda **kwargs: None)
    monkeypatch.setattr(namespace_switcher, "_assert_ports_are_available_for_launch", lambda **kwargs: None)
    monkeypatch.setattr(namespace_switcher, "_launch_namespace_process", _fake_launch)
    monkeypatch.setattr(namespace_switcher, "_wait_for_namespace_ready", _fake_wait)

    result = open_or_launch_namespace(
        environ={},
        current_namespace="default",
        namespace="work",
        port=8123,
        https_port=None,
        mcp_port=8766,
    )

    assert result.action == "launched"
    assert result.url == "http://127.0.0.1:8123"
    assert launched == [("work", 8123, 8766)]
    assert waited == [("work", 8123)]
    saved_profile = load_namespace_launch_profile(namespace="work")
    assert saved_profile is not None
    assert saved_profile.port == 8123
    assert saved_profile.https_port is None
    assert saved_profile.mcp_port == 8766


def test_save_namespace_port_profiles_updates_without_launching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="cla",
        port=8001,
        https_port=None,
        mcp_port=8766,
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_launch_namespace_process",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("_launch_namespace_process should not be called")),
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_restart_running_namespace_process",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("_restart_running_namespace_process should not be called")),
    )

    result = save_namespace_port_profiles(
        environ={},
        current_namespace="default",
        requested_profiles=[
            NamespaceLaunchProfile(
                namespace="cla",
                port=8011,
                https_port=None,
                mcp_port=8776,
            )
        ],
    )

    assert result.message == "Saved ports for 1 namespace(s)."
    assert result.saved_profiles == [
        NamespaceLaunchProfile(
            namespace="cla",
            port=8011,
            https_port=None,
            mcp_port=8776,
        )
    ]
    saved_profile = load_namespace_launch_profile(namespace="cla")
    assert saved_profile == NamespaceLaunchProfile(
        namespace="cla",
        port=8011,
        https_port=None,
        mcp_port=8776,
    )


def test_save_namespace_port_profiles_rejects_batch_conflicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)

    with pytest.raises(
        RuntimeError,
        match="HTTP port 8100 for namespace work conflicts with HTTP port for namespace cla",
    ):
        save_namespace_port_profiles(
            environ={},
            current_namespace="default",
            requested_profiles=[
                NamespaceLaunchProfile(
                    namespace="cla",
                    port=8100,
                    https_port=None,
                    mcp_port=8766,
                ),
                NamespaceLaunchProfile(
                    namespace="work",
                    port=8100,
                    https_port=None,
                    mcp_port=8767,
                ),
            ],
        )


def test_open_login_namespace_uses_catalog_default_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="cla",
        port=8001,
        https_port=None,
        mcp_port=8766,
    )
    opened: list[tuple[str | None, str, int, int | None, int]] = []

    def _fake_open_or_launch_namespace(
        *,
        environ,
        current_namespace,
        namespace,
        port,
        https_port,
        mcp_port,
    ) -> NamespaceOpenResult:
        opened.append((current_namespace, namespace, port, https_port, mcp_port))
        return NamespaceOpenResult(
            namespace=namespace,
            action="opened-running",
            url=f"http://127.0.0.1:{port}",
            saved_profile=NamespaceLaunchProfile(
                namespace=namespace,
                port=port,
                https_port=https_port,
                mcp_port=mcp_port,
            ),
            saved_for_next_launch=False,
            message=f"Opened namespace {namespace}.",
        )

    monkeypatch.setattr(namespace_switcher, "open_or_launch_namespace", _fake_open_or_launch_namespace)

    result = open_login_namespace(
        environ={},
        current_namespace="default",
        namespace="cla",
    )

    assert opened == [("default", "cla", 8001, None, 8766)]
    assert result.url == "http://127.0.0.1:8001"


def test_open_or_launch_all_namespaces_uses_catalog_default_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="default",
        port=8000,
        https_port=None,
        mcp_port=8765,
    )
    save_namespace_launch_profile(
        namespace="cla",
        port=8001,
        https_port=None,
        mcp_port=8766,
    )
    opened: list[tuple[str | None, str, int, int | None, int]] = []

    def _fake_open_or_launch_namespace(
        *,
        environ,
        current_namespace,
        namespace,
        port,
        https_port,
        mcp_port,
    ) -> NamespaceOpenResult:
        opened.append((current_namespace, namespace, port, https_port, mcp_port))
        return NamespaceOpenResult(
            namespace=namespace,
            action="launched",
            url=f"http://127.0.0.1:{port}",
            saved_profile=NamespaceLaunchProfile(
                namespace=namespace,
                port=port,
                https_port=https_port,
                mcp_port=mcp_port,
            ),
            saved_for_next_launch=False,
            message=f"Started namespace {namespace}.",
        )

    monkeypatch.setattr(namespace_switcher, "open_or_launch_namespace", _fake_open_or_launch_namespace)

    results = open_or_launch_all_namespaces(environ={})

    assert opened == [
        (None, "default", 8000, None, 8765),
        (None, "cla", 8001, None, 8766),
    ]
    assert [result.namespace for result in results] == ["default", "cla"]


def test_open_or_launch_all_namespaces_restarts_warm_running_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="default",
        port=8000,
        https_port=None,
        mcp_port=8765,
    )

    def _fake_open_or_launch_namespace(**kwargs) -> NamespaceOpenResult:
        profile = NamespaceLaunchProfile(
            namespace=kwargs["namespace"],
            port=kwargs["port"],
            https_port=kwargs["https_port"],
            mcp_port=kwargs["mcp_port"],
        )
        return NamespaceOpenResult(
            namespace=profile.namespace,
            action="opened-running",
            url=f"http://127.0.0.1:{profile.port}",
            saved_profile=profile,
            saved_for_next_launch=False,
            message=f"Namespace {profile.namespace} is already running with a warm cache.",
        )

    restarted: list[tuple[str, int]] = []
    monkeypatch.setattr(namespace_switcher, "open_or_launch_namespace", _fake_open_or_launch_namespace)
    monkeypatch.setattr(
        namespace_switcher,
        "_restart_running_namespace_process",
        lambda *, environ, namespace, chosen_profile, running_port: restarted.append(
            (namespace, running_port)
        ),
    )

    results = open_or_launch_all_namespaces(environ={})

    assert restarted == [("default", 8000)]
    assert len(results) == 1
    assert results[0].action == "restarted"
    assert results[0].message == "Restarted namespace default."


def test_open_or_launch_all_namespaces_rejects_missing_launch_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    database_path = server_runtime.resolve_namespaced_database_path(namespace="work")
    server_runtime.prepare_database_runtime_path(database_path=database_path)
    database_path.touch()

    with pytest.raises(RuntimeError, match="Namespace default has no launch profile"):
        open_or_launch_all_namespaces(environ={})


def test_restart_running_namespace_process_allows_existing_namespace_ports_before_relaunch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks: list[tuple[str, object]] = []

    monkeypatch.setattr(namespace_switcher, "_find_listening_pids_for_port", lambda *, port: [2345] if port in {8123, 8766} else [])
    monkeypatch.setattr(
        namespace_switcher,
        "_assert_ports_are_available_for_launch",
        lambda *, environ, namespace, chosen_profile, allowed_listener_pids: checks.append(
            ("assert", (namespace, chosen_profile.port, chosen_profile.mcp_port, allowed_listener_pids))
        ),
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_stop_processes_listening_on_port",
        lambda *, port: checks.append(("stop", port)),
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_launch_namespace_process",
        lambda *, environ, chosen_profile: checks.append(("launch", (chosen_profile.namespace, chosen_profile.port))),
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_wait_for_namespace_ready",
        lambda *, environ, namespace, port: checks.append(("wait", (namespace, port))),
    )

    namespace_switcher._restart_running_namespace_process(
        environ={},
        namespace="work",
        chosen_profile=NamespaceLaunchProfile(
            namespace="work",
            port=8123,
            https_port=None,
            mcp_port=8766,
        ),
        running_port=8123,
    )

    assert checks == [
        ("assert", ("work", 8123, 8766, frozenset({2345}))),
        ("stop", 8123),
        ("launch", ("work", 8123)),
        ("wait", ("work", 8123)),
    ]


def test_assert_ports_are_available_for_launch_allows_namespace_owned_mcp_port_on_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        namespace_switcher,
        "resolve_main_server_config",
        lambda *, environ: server_runtime.MainServerConfig(
            host="127.0.0.1",
            port=8000,
            https_port=None,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1,::1",
            ssl_certfile=None,
            ssl_keyfile=None,
        ),
    )
    monkeypatch.setattr(namespace_switcher, "resolve_backend_connect_host", lambda *, host: "127.0.0.1")
    monkeypatch.setattr(namespace_switcher, "resolve_api_prefix", lambda *, environ: "/api2")
    monkeypatch.setattr(
        namespace_switcher,
        "_probe_namespace_status",
        lambda *, host, port, api_prefix: {"namespace": "work"} if port == 8123 else None,
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_is_tcp_port_open",
        lambda *, host, port: port in {8123, 8766},
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_find_listening_pids_for_port",
        lambda *, port: [2345] if port in {8123, 8766} else [],
    )

    namespace_switcher._assert_ports_are_available_for_launch(
        environ={},
        namespace="work",
        chosen_profile=NamespaceLaunchProfile(
            namespace="work",
            port=8123,
            https_port=None,
            mcp_port=8766,
        ),
        allowed_listener_pids=frozenset({2345}),
    )


def test_assert_ports_are_available_for_launch_evicts_conflicting_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evicted_ports: list[int] = []

    monkeypatch.setattr(
        namespace_switcher,
        "resolve_main_server_config",
        lambda *, environ: server_runtime.MainServerConfig(
            host="127.0.0.1",
            port=8000,
            https_port=None,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1,::1",
            ssl_certfile=None,
            ssl_keyfile=None,
        ),
    )
    monkeypatch.setattr(namespace_switcher, "resolve_backend_connect_host", lambda *, host: "127.0.0.1")
    monkeypatch.setattr(namespace_switcher, "resolve_api_prefix", lambda *, environ: "/api2")
    monkeypatch.setattr(
        namespace_switcher,
        "_probe_namespace_status",
        lambda *, host, port, api_prefix: {"namespace": "default"} if port == 8123 else None,
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_is_tcp_port_open",
        lambda *, host, port: port in {8123, 8766},
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_find_listening_pids_for_port",
        lambda *, port: [9999] if port in {8123, 8766} else [],
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_stop_processes_listening_on_port",
        lambda *, port: evicted_ports.append(port),
    )

    namespace_switcher._assert_ports_are_available_for_launch(
        environ={},
        namespace="work",
        chosen_profile=NamespaceLaunchProfile(
            namespace="work",
            port=8123,
            https_port=None,
            mcp_port=8766,
        ),
        allowed_listener_pids=frozenset(),
    )

    assert evicted_ports == [8123, 8766]


def test_launch_namespace_process_uses_recorded_python_script_entrypoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: dict[str, object] = {}

    def _fake_popen(command, **kwargs):
        launched["command"] = command
        launched["env"] = kwargs["env"]
        launched["stdout_name"] = kwargs["stdout"].name

        class _Process:
            pass

        return _Process()

    monkeypatch.setattr(
        namespace_switcher,
        "resolve_runtime_logs_directory",
        lambda: tmp_path / "logs",
    )
    monkeypatch.setattr(namespace_switcher.subprocess, "Popen", _fake_popen)

    namespace_switcher._launch_namespace_process(
        environ={"METALIST_SELF_EXECUTABLE": "/tmp/metalist/main.py"},
        chosen_profile=NamespaceLaunchProfile(
            namespace="work",
            port=8123,
            https_port=None,
            mcp_port=8766,
        ),
    )

    assert launched["command"] == [
        sys.executable,
        "/tmp/metalist/serve_namespace.py",
        "--namespace",
        "work",
        "--port",
        "8123",
        "--mcp-port",
        "8766",
    ]
    assert Path(str(launched["stdout_name"])).parent == tmp_path / "logs"
    launched_env = launched["env"]
    assert isinstance(launched_env, dict)
    assert "METALIST_NAMESPACE" not in launched_env
    assert "METALIST_PORT" not in launched_env
    assert "METALIST_HTTPS_PORT" not in launched_env
    assert "MCP_AGENT_WEB_PORT" not in launched_env


def test_open_or_launch_namespace_restarts_running_namespace_and_updates_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="work",
        port=8123,
        https_port=None,
        mcp_port=8766,
    )
    monkeypatch.setattr(namespace_switcher, "_find_running_namespace_port", lambda **kwargs: 8123)
    restarted: list[tuple[str, int, int]] = []
    monkeypatch.setattr(
        namespace_switcher,
        "_restart_running_namespace_process",
        lambda *, environ, namespace, chosen_profile, running_port: restarted.append(
            (namespace, chosen_profile.port, running_port)
        ),
    )

    result = open_or_launch_namespace(
        environ={},
        current_namespace="default",
        namespace="work",
        port=8124,
        https_port=None,
        mcp_port=8767,
    )

    assert result.action == "restarted"
    assert result.url == "http://127.0.0.1:8124"
    assert result.saved_for_next_launch is True
    assert restarted == [("work", 8124, 8123)]
    saved_profile = load_namespace_launch_profile(namespace="work")
    assert saved_profile is not None
    assert saved_profile.port == 8124
    assert saved_profile.mcp_port == 8767


def test_open_or_launch_namespace_reuses_warm_running_namespace_when_profile_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="work",
        port=8123,
        https_port=None,
        mcp_port=8766,
    )
    monkeypatch.setattr(namespace_switcher, "_find_running_namespace_port", lambda **kwargs: 8123)
    monkeypatch.setattr(
        namespace_switcher,
        "_restart_running_namespace_process",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("unchanged running namespace must not restart")
        ),
    )

    result = open_or_launch_namespace(
        environ={},
        current_namespace="default",
        namespace="work",
        port=8123,
        https_port=None,
        mcp_port=8766,
    )

    assert result.action == "opened-running"
    assert result.url == "http://127.0.0.1:8123"
    assert result.saved_for_next_launch is False
    assert result.message == "Namespace work is already running with a warm cache."


def test_open_or_launch_namespace_short_circuits_current_namespace_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="default",
        port=8000,
        https_port=None,
        mcp_port=8765,
    )

    monkeypatch.setattr(
        namespace_switcher,
        "_find_running_namespace_port",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("_find_running_namespace_port should not be called")),
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_launch_namespace_process",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("_launch_namespace_process should not be called")),
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_wait_for_namespace_ready",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("_wait_for_namespace_ready should not be called")),
    )

    result = open_or_launch_namespace(
        environ={},
        current_namespace="default",
        namespace="default",
        port=8000,
        https_port=None,
        mcp_port=8765,
    )

    assert result.action == "opened-running"
    assert result.url == "http://127.0.0.1:8000"
    assert result.saved_for_next_launch is False
    assert result.message == "Namespace default is already running."


def test_probe_namespace_status_sends_required_tab_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: dict[str, object] = {}

    class _FakeResponse:
        status = 200

        def read(self) -> bytes:
            return b'{"namespace":"work"}'

    class _FakeConnection:
        def __init__(self, *, host, port, timeout):
            requested["host"] = host
            requested["port"] = port
            requested["timeout"] = timeout

        def request(self, method, url, headers):
            requested["method"] = method
            requested["url"] = url
            requested["headers"] = headers

        def getresponse(self):
            return _FakeResponse()

        def close(self):
            requested["closed"] = True

    monkeypatch.setattr(namespace_switcher, "HTTPConnection", _FakeConnection)

    payload = _probe_namespace_status(
        host="127.0.0.1",
        port=8001,
        api_prefix="/api2",
    )

    assert payload == {"namespace": "work"}
    assert requested["method"] == "GET"
    assert requested["url"] == "/api2/auth/status"
    assert requested["headers"] == {"X-Metalist-Tab-Id": "namespace-switcher-probe"}
    assert requested["closed"] is True

def test_delete_current_namespace_launches_default_and_spawns_cleanup_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    _disable_default_tls(monkeypatch, tmp_path)
    save_namespace_launch_profile(
        namespace="default",
        port=8001,
        https_port=None,
        mcp_port=8766,
    )
    launched: list[tuple[str, str, int, int | None, int]] = []
    cleanup_requests: list[tuple[str, int, str]] = []

    def _fake_open_or_launch_namespace(*, environ, current_namespace, namespace, port, https_port, mcp_port):
        launched.append((current_namespace, namespace, port, https_port, mcp_port))
        return NamespaceOpenResult(
            namespace=namespace,
            action="launched",
            url=f"http://127.0.0.1:{port}",
            saved_profile=NamespaceLaunchProfile(
                namespace=namespace,
                port=port,
                https_port=https_port,
                mcp_port=mcp_port,
            ),
            saved_for_next_launch=False,
            message=f"Started namespace {namespace}.",
        )

    monkeypatch.setattr(namespace_switcher, "open_or_launch_namespace", _fake_open_or_launch_namespace)
    monkeypatch.setattr(
        namespace_switcher,
        "create_namespace_deletion_job",
        lambda *, deleted_namespace, redirect_namespace: {
            "job_id": "11111111-1111-1111-1111-111111111111",
            "status": "pending",
            "deleted_namespace": deleted_namespace,
            "redirect_namespace": redirect_namespace,
            "error": "",
        },
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_spawn_namespace_deletion_worker",
        lambda *, namespace, current_pid, job_id: cleanup_requests.append((namespace, current_pid, job_id)),
    )
    monkeypatch.setattr(namespace_switcher.os, "getpid", lambda: 4321)

    result = delete_current_namespace(
        environ={},
        current_namespace="work",
        confirmed_namespace=" work ",
    )

    assert result.deleted_namespace == "work"
    assert result.delete_job_id == "11111111-1111-1111-1111-111111111111"
    assert result.active_namespace_deleted is True
    assert result.message == "Deleting namespace work. Opening the namespace removal page."
    parsed_redirect = urlsplit(result.redirect_url)
    assert parsed_redirect.netloc == "127.0.0.1:8001"
    assert parsed_redirect.path == "/namespace-deleted"
    redirect_query = parse_qs(parsed_redirect.query)
    assert redirect_query == {"job": ["11111111-1111-1111-1111-111111111111"]}
    assert launched == [("work", "default", 8001, None, 8766)]
    assert cleanup_requests == [("work", 4321, "11111111-1111-1111-1111-111111111111")]


def test_delete_current_namespace_rejects_default_namespace() -> None:
    with pytest.raises(RuntimeError, match="Default namespace cannot be deleted"):
        delete_current_namespace(
            environ={},
            current_namespace="default",
            confirmed_namespace="default",
        )


def test_delete_current_namespace_requires_confirmed_namespace_name() -> None:
    with pytest.raises(RuntimeError, match="Type 'work' to confirm namespace deletion"):
        delete_current_namespace(
            environ={},
            current_namespace="work",
            confirmed_namespace="permanently delete",
        )


def test_delete_namespace_removes_inactive_namespace_without_redirect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace_directory = tmp_path / "namespaces" / "cla"
    namespace_directory.mkdir(parents=True)
    stopped_profiles: list[NamespaceLaunchProfile] = []
    target_profile = NamespaceLaunchProfile(
        namespace="cla",
        port=8002,
        https_port=None,
        mcp_port=8767,
    )

    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    monkeypatch.setattr(
        namespace_switcher,
        "_load_saved_profiles_by_namespace",
        lambda: {"cla": target_profile},
    )
    monkeypatch.setattr(
        namespace_switcher,
        "_stop_processes_for_namespace_profile",
        lambda *, profile: stopped_profiles.append(profile),
    )

    result = delete_namespace(
        environ={},
        current_namespace="test",
        target_namespace="cla",
        confirmed_namespace=" cla ",
    )

    assert result.deleted_namespace == "cla"
    assert result.redirect_url == ""
    assert result.delete_job_id == ""
    assert result.active_namespace_deleted is False
    assert result.message == "Deleted namespace cla."
    assert namespace_directory.exists() is False
    assert stopped_profiles == [target_profile]


def test_delete_namespace_launch_profile_removes_saved_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    save_namespace_launch_profile(
        namespace="work",
        port=8123,
        https_port=None,
        mcp_port=8766,
    )

    assert load_namespace_launch_profile(namespace="work") is not None

    delete_namespace_launch_profile(namespace="work")

    assert load_namespace_launch_profile(namespace="work") is None
