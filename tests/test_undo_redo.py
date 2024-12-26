import random
import pytest
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.database import Base, DBNote
from app.models.linked_list import LinkedListManager, MovePosition

@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()

@contextmanager
def transaction_scope(db_session):
    try:
        yield
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise e

def test_undo_redo_fuzz(db):
    """Fuzz test with undo/redo operations"""
    SEED = 42
    NODES = 5
    STEPS = 100
    UNDO_REDO_INTERVAL = 5

    random.seed(SEED)

    # Create initial notes in a valid linked list structure
    with transaction_scope(db):
        notes = []
        for i in range(NODES):
            note = DBNote(id=str(i), content=f"Note {i}")
            if i > 0:
                note.prev_id = str(i-1)
                notes[i-1].next_id = str(i)
            notes.append(note)

        db.add_all(notes)

    # Perform random operations interspersed with undo/redo
    for i in range(STEPS):
        operation = random.random()

        if operation < 0.2:  # 20% chance to delete
            note_id = str(random.randint(0, NODES-1))
            print(f"Deleting note {note_id}")
            with transaction_scope(db):
                LinkedListManager.delete_note(db, note_id)
            print("Delete successful!")

        elif operation < 0.4:  # 20% chance to add new note
            new_id = str(NODES)
            NODES += 1
            print(f"Adding new note {new_id}")
            with transaction_scope(db):
                LinkedListManager.create_note_top(db, new_id)
            print("Add successful!")

        else:  # 60% chance for move operation
            note_id = str(random.randint(0, NODES-1))
            new_parent_id = random.choice([str(i) for i in range(NODES)] + [None])
            sibling_id = None
            position = None

            if new_parent_id != note_id:
                print(f"Moving note {note_id} to parent {new_parent_id}")
                with transaction_scope(db):
                    LinkedListManager.move_note(
                        db=db,
                        note_id=note_id,
                        new_parent_id=new_parent_id,
                        sibling_id=sibling_id,
                        position=position
                    )
                print("Move successful!")

        # Every few steps, perform an undo or redo
        if i % UNDO_REDO_INTERVAL == 0:
            if random.choice([True, False]):
                print("Performing undo")
                LinkedListManager.undo(db)
            else:
                print("Performing redo")
                LinkedListManager.redo(db)

        # Validate the list structure
        with transaction_scope(db):
            if not LinkedListManager.validate_list(db, None):
                raise ValueError("Invalid list structure")

    print("Undo/Redo fuzz test completed successfully.") 