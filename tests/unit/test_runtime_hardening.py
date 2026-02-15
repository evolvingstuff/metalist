from __future__ import annotations

import pytest

from app.services import runtime_hardening


def test_parse_pmset_values_extracts_all_values() -> None:
    output = """
Battery Power:
 hibernatemode        0
 standby              0
AC Power:
 hibernatemode        0
 standby              1
"""
    values = runtime_hardening._parse_pmset_values(output, "standby")
    assert values == [0, 1]


def test_parse_pmset_values_raises_when_key_missing() -> None:
    with pytest.raises(RuntimeError, match="missing key"):
        runtime_hardening._parse_pmset_values("AC Power:\n sleep 0\n", "hibernatemode")


def test_apply_runtime_hardening_rejects_macos_hibernation(monkeypatch) -> None:
    monkeypatch.setattr(runtime_hardening, "SECURITY_HARDENING_ENABLED", True)
    monkeypatch.setattr(runtime_hardening, "SECURITY_REQUIRE_MACOS_NO_HIBERNATION", True)
    monkeypatch.setattr(runtime_hardening, "SECURITY_REQUIRE_ENCRYPTED_SWAP", False)
    monkeypatch.setattr(runtime_hardening.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(runtime_hardening, "disable_core_dumps", lambda: None)
    monkeypatch.setattr(
        runtime_hardening,
        "_run_command",
        lambda command: "AC Power:\n hibernatemode 3\n standby 0\n autopoweroff 0\n",
    )

    with pytest.raises(RuntimeError, match="hibernatemode=3"):
        runtime_hardening.apply_runtime_hardening()


def test_apply_runtime_hardening_rejects_unencrypted_swap(monkeypatch) -> None:
    monkeypatch.setattr(runtime_hardening, "SECURITY_HARDENING_ENABLED", True)
    monkeypatch.setattr(runtime_hardening, "SECURITY_REQUIRE_MACOS_NO_HIBERNATION", False)
    monkeypatch.setattr(runtime_hardening, "SECURITY_REQUIRE_ENCRYPTED_SWAP", True)
    monkeypatch.setattr(runtime_hardening.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(runtime_hardening, "disable_core_dumps", lambda: None)
    monkeypatch.setattr(
        runtime_hardening,
        "_run_command",
        lambda command: "vm.swapusage: total = 1024.00M  used = 0.00M  free = 1024.00M",
    )

    with pytest.raises(RuntimeError, match="Swap is not reported as encrypted"):
        runtime_hardening.apply_runtime_hardening()


def test_apply_runtime_hardening_non_darwin_only_disables_core(monkeypatch) -> None:
    monkeypatch.setattr(runtime_hardening, "SECURITY_HARDENING_ENABLED", True)
    monkeypatch.setattr(runtime_hardening.sys, "platform", "linux", raising=False)

    called = {"count": 0}

    def _disabled() -> None:
        called["count"] += 1

    monkeypatch.setattr(runtime_hardening, "disable_core_dumps", _disabled)
    runtime_hardening.apply_runtime_hardening()
    assert called["count"] == 1
