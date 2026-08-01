from __future__ import annotations

from pathlib import Path

import pytest

from app.startup_sanity import assert_startup_sanity
from app.startup_sanity import collect_startup_sanity_violations


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_startup_sanity_rejects_forbidden_try_except(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "bad.py",
        """
def bad():
    try:
        internal_call()
    except ValueError:
        raise
""".strip()
        + "\n",
    )

    paths, violations = collect_startup_sanity_violations(tmp_path)

    assert len(paths) == 1
    assert any(
        violation.rule_id == "PY001"
        and "exception type not allowlisted: ValueError" in violation.message
        for violation in violations
    )

    with pytest.raises(RuntimeError, match="PY001"):
        assert_startup_sanity(tmp_path)


def test_startup_sanity_rejects_missing_transactional_route(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "routes.py",
        """
from fastapi import APIRouter

router = APIRouter(prefix="/notes")

@router.post("/move")
def move():
    return {"ok": True}
""".strip()
        + "\n",
    )

    _, violations = collect_startup_sanity_violations(tmp_path)

    assert any(
        violation.rule_id == "TXN001"
        and "POST /notes/move (move) missing @transactional_route" in violation.message
        for violation in violations
    )


def test_startup_sanity_rejects_misordered_transactional_route(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "routes.py",
        """
from fastapi import APIRouter

from app.api.transactions import transactional_route

router = APIRouter(prefix="/notes")

@transactional_route
@router.post("/move")
def move():
    return {"ok": True}
""".strip()
        + "\n",
    )

    _, violations = collect_startup_sanity_violations(tmp_path)

    assert any(
        violation.rule_id == "TXN002"
        and "@transactional_route directly below the route decorator" in violation.message
        for violation in violations
    )


def test_startup_sanity_honors_suppression_comments(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "suppressed.py",
        """
def bad():
    # lint: allow-PY001 rationale="intentional suppression for test"
    try:
        internal_call()
    except ValueError:
        raise
""".strip()
        + "\n",
    )

    _, violations = collect_startup_sanity_violations(tmp_path)

    assert any(
        violation.rule_id == "PY001"
        and "exception type not allowlisted: ValueError" in violation.message
        for violation in violations
    )
    assert not any(
        violation.rule_id == "PY001"
        and "try body has no allowlisted external call" in violation.message
        for violation in violations
    )


def test_installed_distribution_scan_excludes_neighboring_packages(tmp_path: Path) -> None:
    _write_file(tmp_path / "main.py", "APP_NAME = 'MetaList'\n")
    _write_file(tmp_path / "mcp_client.py", "COMMAND_NAME = 'metalist-mcp'\n")
    _write_file(tmp_path / "app" / "owned.py", "VALUE = 1\n")
    _write_file(
        tmp_path / "argon2" / "dependency.py",
        "VALUE = environ.get('EXTERNAL_DEFAULT', '1')\n",
    )

    paths, violations = collect_startup_sanity_violations(tmp_path)
    relative_paths = [path.relative_to(tmp_path).as_posix() for path in paths]

    assert relative_paths == ["app/owned.py", "main.py", "mcp_client.py"]
    assert violations == []
