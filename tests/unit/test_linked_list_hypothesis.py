from __future__ import annotations

import random

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.database import Base, DBNote
from app.models.enums import MovePosition
from app.models.linked_list import LinkedListManager
from app.services.content_cache import clear_cache
from app.services.note_service import NoteService
from app.services.transaction_manager import TransactionManager
from tests.unit.common import transaction_scope


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _refresh_ids(db: Session) -> list[str]:
    with transaction_scope(db):
        ids = [note.id for note in db.query(DBNote.id).all()]
    return ids


def _ensure_linked_list_ok(db: Session) -> None:
    with transaction_scope(db):
        assert LinkedListManager.validate_list(db, None)


def _random_operation(db: Session, tm: TransactionManager, rng: random.Random) -> None:
    ids = _refresh_ids(db)
    client_id = "hypothesis-seed"

    with NoteService(db, tm, client_id) as service:
        if not ids or rng.random() < 0.25:
            # Always allow creating root nodes
            service.create_note()
            return

    op = rng.choice(["child", "sibling", "move", "delete"])
    if op == "delete" and len(ids) == 1:
        op = rng.choice(["child", "sibling", "move"])

    target_id = rng.choice(ids)

    if op == "child":
        with NoteService(db, tm, client_id) as service:
            service.create_child_note(target_id)
    elif op == "sibling":
        with NoteService(db, tm, client_id) as service:
            service.create_sibling_note(target_id)
    elif op == "move":
        potential_parents = ids + [None]
        new_parent = rng.choice(potential_parents)
        if new_parent == target_id:
            return

        sibling_id = None
        position = None
        if new_parent:
            siblings = [
                n.id for n in db.query(DBNote).filter(DBNote.parent_id == new_parent, DBNote.id != target_id)
            ]
            if siblings:
                sibling_id = rng.choice(siblings)
                position = rng.choice([MovePosition.BEFORE, MovePosition.AFTER])

        # Avoid no-op moves
        note = db.get(DBNote, target_id)
        if note.parent_id == new_parent and sibling_id is None:
            return
        if new_parent and LinkedListManager._would_create_cycle(db, target_id, new_parent):
            return

        with NoteService(db, tm, client_id) as service:
            service.move_note(target_id, new_parent, sibling_id, position)
    elif op == "delete":
        with NoteService(db, tm, client_id) as service:
            service.delete_note(target_id)


@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_randomized_note_operations(seed: int):
    db = _make_session()
    tm = TransactionManager()
    clear_cache()

    rng = random.Random(seed)

    for _ in range(50):
        _random_operation(db, tm, rng)
        _ensure_linked_list_ok(db)

    db.close()
    clear_cache()
