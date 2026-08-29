from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.services.managed_ollama_runtime as managed_runtime_module
from app.services.managed_ollama_runtime import ManagedOllamaRuntime
from app.services.managed_ollama_runtime import ManagedOllamaRuntimeConfig


class _FakeProcess:
    def __init__(self, *, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def wait(self, *, timeout: float) -> int:
        assert timeout == 5.0
        assert self.returncode is not None
        return self.returncode


def _runtime(tmp_path: Path) -> ManagedOllamaRuntime:
    return ManagedOllamaRuntime(
        config=ManagedOllamaRuntimeConfig(
            host="127.0.0.1",
            port=11435,
            context_tokens=32_768,
            startup_timeout_seconds=30.0,
        ),
        runtime_directory=tmp_path / "runtime",
        logs_directory=tmp_path / "logs",
        environ={"PATH": "/usr/bin"},
    )


def test_managed_runtime_starts_dedicated_local_ollama_with_32k_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    launched: dict[str, object] = {}
    probe_results = iter([False, True])

    monkeypatch.setattr(
        managed_runtime_module.shutil,
        "which",
        lambda executable: "/opt/homebrew/bin/ollama" if executable == "ollama" else None,
    )
    monkeypatch.setattr(
        managed_runtime_module,
        "_probe_ollama_version",
        lambda **kwargs: "0.33.0" if next(probe_results) else "",
    )
    monkeypatch.setattr(
        managed_runtime_module,
        "_find_listening_pids_for_port",
        lambda **kwargs: [4242],
    )

    def fake_popen(command, **kwargs):
        launched["command"] = command
        launched["kwargs"] = kwargs
        return _FakeProcess(pid=4242)

    monkeypatch.setattr(managed_runtime_module.subprocess, "Popen", fake_popen)

    runtime_info = runtime.ensure_running()

    assert runtime_info.base_url == "http://127.0.0.1:11435"
    assert runtime_info.pid == 4242
    assert runtime_info.context_tokens == 32_768
    assert runtime_info.version == "0.33.0"
    assert launched["command"] == ["/opt/homebrew/bin/ollama", "serve"]
    launch_kwargs = launched["kwargs"]
    assert isinstance(launch_kwargs, dict)
    launch_environment = launch_kwargs["env"]
    assert isinstance(launch_environment, dict)
    assert launch_environment["OLLAMA_HOST"] == "127.0.0.1:11435"
    assert launch_environment["OLLAMA_CONTEXT_LENGTH"] == "32768"
    assert launch_environment["OLLAMA_DEBUG_LOG_REQUESTS"] == "false"
    assert launch_environment["OLLAMA_NO_CLOUD"] == "1"
    assert launch_environment["OLLAMA_NOHISTORY"] == "1"
    assert launch_environment["OLLAMA_NUM_PARALLEL"] == "1"
    assert launch_kwargs["start_new_session"] is True


def test_managed_runtime_reuses_the_shared_owned_daemon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    runtime.runtime_directory.mkdir(parents=True)
    runtime.state_path.write_text(
        json.dumps(
            {
                "base_url": "http://127.0.0.1:11435",
                "context_tokens": 32768,
                "executable": "/opt/homebrew/bin/ollama",
                "pid": 4242,
                "port": 11435,
                "started_at": "2026-08-29T16:00:00+00:00",
                "version": "0.33.0",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(managed_runtime_module, "_is_process_running", lambda **kwargs: True)
    monkeypatch.setattr(
        managed_runtime_module,
        "_probe_ollama_version",
        lambda **kwargs: "0.33.0",
    )
    monkeypatch.setattr(
        managed_runtime_module,
        "_find_listening_pids_for_port",
        lambda **kwargs: [4242],
    )
    monkeypatch.setattr(
        managed_runtime_module.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("Owned running daemon must be reused"),
    )

    runtime_info = runtime.ensure_running()

    assert runtime_info.pid == 4242
    assert runtime_info.base_url == "http://127.0.0.1:11435"


def test_managed_runtime_refuses_an_unowned_listener(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        managed_runtime_module,
        "_probe_ollama_version",
        lambda **kwargs: "0.33.0",
    )

    with pytest.raises(
        RuntimeError,
        match="port 11435 is already occupied by an Ollama server MetaList does not own",
    ):
        runtime.ensure_running()


def test_managed_runtime_replaces_stale_state_before_starting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    runtime.runtime_directory.mkdir(parents=True)
    runtime.state_path.write_text(
        json.dumps(
            {
                "base_url": "http://127.0.0.1:11435",
                "context_tokens": 32768,
                "executable": "/opt/homebrew/bin/ollama",
                "pid": 1234,
                "port": 11435,
                "started_at": "2026-08-29T15:00:00+00:00",
                "version": "0.32.0",
            }
        ),
        encoding="utf-8",
    )
    probe_results = iter([False, False, True])
    monkeypatch.setattr(managed_runtime_module, "_is_process_running", lambda **kwargs: False)
    monkeypatch.setattr(
        managed_runtime_module,
        "_probe_ollama_version",
        lambda **kwargs: "0.33.0" if next(probe_results) else "",
    )
    monkeypatch.setattr(
        managed_runtime_module,
        "_find_listening_pids_for_port",
        lambda **kwargs: [5678],
    )
    monkeypatch.setattr(
        managed_runtime_module.shutil,
        "which",
        lambda executable: "/opt/homebrew/bin/ollama" if executable == "ollama" else None,
    )
    monkeypatch.setattr(
        managed_runtime_module.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(pid=5678),
    )

    runtime_info = runtime.ensure_running()

    assert runtime_info.pid == 5678
    stored_state = json.loads(runtime.state_path.read_text(encoding="utf-8"))
    assert stored_state["pid"] == 5678
    assert stored_state["context_tokens"] == 32768
