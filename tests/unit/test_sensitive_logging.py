from __future__ import annotations

import logging
from pathlib import Path

from app.security.validation_errors import summarize_validation_errors
from app.services.transaction_manager import TransactionManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_search_context_logging_never_contains_search_text(caplog) -> None:
    manager = TransactionManager()
    manager.last_search_query = "previous private search"
    manager.command_stack_size = 2

    with caplog.at_level(logging.DEBUG):
        manager.check_context_change("current private search")

    assert "previous private search" not in caplog.text
    assert "current private search" not in caplog.text
    assert "Search context changed" in caplog.text


def test_validation_error_summary_discards_rejected_input_and_context() -> None:
    secret = "correct horse battery staple"
    summarized = summarize_validation_errors(
        [
            {
                "type": "string_too_short",
                "loc": ("body", "password"),
                "msg": "String should have at least 12 characters",
                "input": secret,
                "ctx": {"submitted": secret},
                "url": "https://errors.example.invalid/secret",
            }
        ]
    )

    assert summarized == [
        {
            "type": "string_too_short",
            "loc": ["body", "password"],
        }
    ]
    assert secret not in repr(summarized)


def test_server_search_telemetry_never_binds_plaintext_query() -> None:
    paths = (
        PROJECT_ROOT / "app" / "services" / "snapshot.py",
        PROJECT_ROOT / "app" / "services" / "search_index.py",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "query=search" not in source, path


def test_uvicorn_access_log_is_disabled_because_request_targets_can_contain_searches() -> None:
    source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

    assert "access_log=False" in source
