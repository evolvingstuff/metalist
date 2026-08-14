from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import app.server_runtime as server_runtime
import app.services.namespace_runtime_guard as namespace_runtime_guard
from app.server_runtime import delete_namespace_launch_profile
from app.server_runtime import save_namespace_launch_profile


def test_namespace_runtime_guard_accepts_registered_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    save_namespace_launch_profile(
        namespace="work",
        port=8001,
        https_port=None,
        mcp_port=None,
    )

    namespace_runtime_guard.assert_namespace_runtime_is_legitimate(namespace="work")


def test_namespace_runtime_guard_rejects_removed_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    save_namespace_launch_profile(
        namespace="work",
        port=8001,
        https_port=None,
        mcp_port=None,
    )
    shutil.rmtree(server_runtime.resolve_namespace_directory(namespace="work"))

    with pytest.raises(RuntimeError, match="database is missing"):
        namespace_runtime_guard.assert_namespace_runtime_is_legitimate(namespace="work")


def test_namespace_runtime_guard_rejects_namespace_without_launch_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    save_namespace_launch_profile(
        namespace="work",
        port=8001,
        https_port=None,
        mcp_port=None,
    )
    delete_namespace_launch_profile(namespace="work")

    with pytest.raises(RuntimeError, match="launch profile is missing"):
        namespace_runtime_guard.assert_namespace_runtime_is_legitimate(namespace="work")


def test_namespace_runtime_guard_terminates_after_failed_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    monkeypatch.setattr(
        namespace_runtime_guard,
        "inspect_namespace_runtime_legitimacy",
        lambda *, namespace: namespace_runtime_guard.NamespaceRuntimeLegitimacy(
            is_legitimate=False,
            failure_reason=f"Namespace {namespace} is gone",
        ),
    )
    monkeypatch.setattr(
        namespace_runtime_guard,
        "_terminate_current_process",
        lambda: events.append("terminate"),
    )

    namespace_runtime_guard._run_namespace_runtime_guard(
        namespace="work",
        check_interval_seconds=5.0,
        sleep=lambda seconds: events.append(("sleep", seconds)),
    )

    assert events == [("sleep", 5.0), "terminate"]
