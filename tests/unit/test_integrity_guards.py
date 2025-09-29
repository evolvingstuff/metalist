import pytest

from app.core import config
from app.services.transaction_manager import get_transaction_manager
from app.services.note_service import NoteService
from app.services.integrity import should_run_integrity_checks
from app.models.database import DBNote
from tests.unit.common import db  # noqa: F401


@pytest.fixture
def enable_integrity_checks(monkeypatch):
    original = config.DEV_ENFORCE_INTEGRITY_CHECKS
    monkeypatch.setattr(config, "DEV_ENFORCE_INTEGRITY_CHECKS", True)
    yield
    monkeypatch.setattr(config, "DEV_ENFORCE_INTEGRITY_CHECKS", original)


@pytest.fixture
def transaction_manager():
    tm = get_transaction_manager()
    tm.command_stack.clear_all()
    return tm


def test_create_note_respects_integrity_guards(db, transaction_manager, enable_integrity_checks):
    assert should_run_integrity_checks()
    with NoteService(db, transaction_manager, "client-123") as service:
        result = service.create_note()
        assert result["status"] == "created"
    assert db.query(DBNote).count() == 1


def test_note_count_mismatch_raises(db, transaction_manager, enable_integrity_checks):
    with pytest.raises(RuntimeError):
        with NoteService(db, transaction_manager, "client-123") as service:
            service._set_operation("forced_delta")
            service.expect_note_delta(1)


def test_linked_list_failure_bubbles_up(db, transaction_manager, enable_integrity_checks, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.base_service.assert_linked_list_integrity", boom)

    with pytest.raises(RuntimeError):
        with NoteService(db, transaction_manager, "client-123") as service:
            service.create_note()
