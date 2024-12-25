import uuid

import pytest
from sqlalchemy.orm import scoped_session, sessionmaker
from app.models.database import engine, DBNote, Base
from app.models.linked_list import LinkedListManager

@pytest.fixture(scope='module')
def db_session():
    """Set up a database session for testing."""
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    session = scoped_session(sessionmaker(bind=engine))
    yield session
    session.remove()

def test_sequence_add(db_session):
    # Clear existing notes
    db_session.query(DBNote).delete()
    db_session.commit()

    K = 100

    for k in range(1, K + 1):
        # Add new note
        note_id = str(k)
        LinkedListManager.create_note_top(db_session, note_id)

        # Update note value
        note = db_session.query(DBNote).get(note_id)
        note.content = str(k)
        db_session.commit()

    # Verify the sequence
    current_note = db_session.query(DBNote).filter(DBNote.prev_id == None).first()
    for expected_value in range(K, 0, -1):
        assert current_note.content == str(expected_value), f"Expected {expected_value}, got {current_note.content}"
        current_note = db_session.query(DBNote).filter(DBNote.id == current_note.next_id).first()

    assert current_note is None, "There should be no more notes in the sequence"


def test_sequence_add_v2(db_session):
    # Clear existing notes
    db_session.query(DBNote).delete()
    db_session.commit()

    K = 100

    added = []

    for k in range(K):
        # Add new note
        note_id = str(uuid.uuid4())
        LinkedListManager.create_note_top(db_session, note_id)
        db_session.commit()
        added.append(note_id)

    assert len(added) == K, f"Expected {K} notes, got {len(added)}"

    for k, note_id in enumerate(reversed(added)):
        note = db_session.query(DBNote).get(note_id)
        note.content = str(k)
        db_session.commit()

    # Verify the sequence
    current_note = db_session.query(DBNote).filter(DBNote.prev_id == None).first()
    for expected_value in range(K):
        assert current_note.content == str(expected_value), f"Expected {expected_value}, got {current_note.content}"
        current_note = db_session.query(DBNote).filter(DBNote.id == current_note.next_id).first()

    assert current_note is None, "There should be no more notes in the sequence"