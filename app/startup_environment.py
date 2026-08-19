from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values


ENVIRONMENT_VARIABLE_NAME = "METALIST_ENVIRONMENT"
DEVELOPMENT_ENVIRONMENT = "development"
PRODUCTION_ENVIRONMENT = "production"
_ALLOWED_ENVIRONMENTS = frozenset(
    {
        DEVELOPMENT_ENVIRONMENT,
        PRODUCTION_ENVIRONMENT,
    }
)


def _normalize_environment(raw_environment: str, *, source: str) -> str:
    environment = raw_environment.strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        allowed = ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
        raise RuntimeError(
            f"{ENVIRONMENT_VARIABLE_NAME} from {source} must be one of: {allowed}",
        )
    return environment


def resolve_startup_environment(
    *,
    repo_root: Path,
    environ: Mapping[str, str],
) -> str:
    if not isinstance(repo_root, Path):
        raise TypeError(f"repo_root must be a Path, got {type(repo_root)}")

    if ENVIRONMENT_VARIABLE_NAME in environ:
        return _normalize_environment(
            environ[ENVIRONMENT_VARIABLE_NAME],
            source="process environment",
        )

    dotenv_path = repo_root / ".env"
    if not dotenv_path.is_file():
        return PRODUCTION_ENVIRONMENT

    dotenv_environment = dotenv_values(dotenv_path).get(ENVIRONMENT_VARIABLE_NAME)
    if dotenv_environment is None:
        return PRODUCTION_ENVIRONMENT

    return _normalize_environment(
        dotenv_environment,
        source=str(dotenv_path),
    )
