import pytest

from app.services.memory_service import MemoryService
from app.services import memory_service


@pytest.fixture(autouse=True)
def reset_memory_tracker():
    with memory_service._tracker._lock:
        memory_service._tracker._data.clear()
    yield
    with memory_service._tracker._lock:
        memory_service._tracker._data.clear()


def make_note(note_id):
    return {
        'id': note_id,
        'children': [],
    }


def test_choose_note_skips_previous_note(monkeypatch):
    service = MemoryService(db=None)
    notes = [make_note('note-a'), make_note('note-b')]

    monkeypatch.setattr(memory_service.random, 'random', lambda: 0.0)

    selected, _root, _stats, probability = service.choose_note(
        notes,
        previous_note_id='note-a',
    )

    assert selected['id'] == 'note-b'
    assert probability == pytest.approx(1.0)


def test_choose_note_allows_repeat_when_only_option(monkeypatch):
    service = MemoryService(db=None)
    notes = [make_note('only-note')]

    monkeypatch.setattr(memory_service.random, 'random', lambda: 0.0)

    selected, _root, _stats, probability = service.choose_note(
        notes,
        previous_note_id='only-note',
    )

    assert selected['id'] == 'only-note'
    assert 0.0 < probability <= 1.0
