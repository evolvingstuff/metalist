from __future__ import annotations

from pathlib import Path

import pytest

from app.startup_environment import DEVELOPMENT_ENVIRONMENT
from app.startup_environment import PRODUCTION_ENVIRONMENT
from app.startup_environment import resolve_startup_environment


def test_startup_environment_defaults_to_production(tmp_path: Path) -> None:
    environment = resolve_startup_environment(repo_root=tmp_path, environ={})

    assert environment == PRODUCTION_ENVIRONMENT


def test_startup_environment_reads_development_from_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "METALIST_ENVIRONMENT=development\n",
        encoding="utf-8",
    )

    environment = resolve_startup_environment(repo_root=tmp_path, environ={})

    assert environment == DEVELOPMENT_ENVIRONMENT


def test_process_environment_overrides_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "METALIST_ENVIRONMENT=development\n",
        encoding="utf-8",
    )

    environment = resolve_startup_environment(
        repo_root=tmp_path,
        environ={"METALIST_ENVIRONMENT": "production"},
    )

    assert environment == PRODUCTION_ENVIRONMENT


def test_startup_environment_rejects_unknown_value(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="must be one of: development, production"):
        resolve_startup_environment(
            repo_root=tmp_path,
            environ={"METALIST_ENVIRONMENT": "staging"},
        )
