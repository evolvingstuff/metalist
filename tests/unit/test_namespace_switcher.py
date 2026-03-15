from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import app.server_runtime as server_runtime
import app.services.namespace_switcher as namespace_switcher
from app.server_runtime import delete_namespace_launch_profile
from app.server_runtime import load_namespace_launch_profile
from app.server_runtime import NamespaceLaunchProfile
from app.server_runtime import save_namespace_launch_profile
from app.services.namespace_switcher import build_namespace_catalog
from app.services.namespace_switcher import delete_current_namespace
from app.services.namespace_switcher import open_or_launch_namespace
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


def test_open_or_launch_namespace_opens_running_namespace_and_updates_future_profile(
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
    launched = {"count": 0}

    def _never_launch(*, environ, chosen_profile):
        launched["count"] += 1

    monkeypatch.setattr(namespace_switcher, "_find_running_namespace_port", lambda **kwargs: 8123)
    monkeypatch.setattr(namespace_switcher, "_launch_namespace_process", _never_launch)
    monkeypatch.setattr(namespace_switcher, "_wait_for_namespace_ready", lambda **kwargs: None)
    monkeypatch.setattr(namespace_switcher, "_assert_ports_are_available_for_launch", lambda **kwargs: None)

    result = open_or_launch_namespace(
        environ={},
        current_namespace="default",
        namespace="work",
        port=8124,
        https_port=None,
        mcp_port=8767,
    )

    assert result.action == "opened-running"
    assert result.url == "http://127.0.0.1:8123"
    assert result.saved_for_next_launch is True
    assert launched["count"] == 0
    saved_profile = load_namespace_launch_profile(namespace="work")
    assert saved_profile is not None
    assert saved_profile.port == 8124
    assert saved_profile.mcp_port == 8767


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
        confirmation_text=" permanently delete ",
    )

    assert result.deleted_namespace == "work"
    assert result.delete_job_id == "11111111-1111-1111-1111-111111111111"
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
            confirmation_text="permanently delete",
        )


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
