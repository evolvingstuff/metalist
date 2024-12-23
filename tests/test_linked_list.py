import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy import Column, String
from app.models.linked_list import LinkedListManager

Base = declarative_base()

class TestNote(Base):
    __tablename__ = "test_notes"
    
    id = Column(String, primary_key=True)
    content = Column(String)
    prev_id = Column(String, nullable=True)
    next_id = Column(String, nullable=True)
    parent_id = Column(String, nullable=True)

@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()

def test_move_note_after(db):
    # Create test notes: 3 -> 2 -> 1
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", next_id="1")
    note3 = TestNote(id="3", content="3", next_id="2")
    note1.prev_id = "2"
    note2.prev_id = "3"
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Move note 3 after note 2 (should become: 2 -> 3 -> 1)
    LinkedListManager.move_note(db, TestNote, "3", "2", False, None)
    
    # Verify the new order
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in notes] == ["2", "3", "1"]
    
    # Verify all bidirectional links
    note2 = db.query(TestNote).get("2")
    note3 = db.query(TestNote).get("3")
    note1 = db.query(TestNote).get("1")
    
    assert note2.prev_id is None
    assert note2.next_id == "3"
    assert note3.prev_id == "2"
    assert note3.next_id == "1"
    assert note1.prev_id == "3"
    assert note1.next_id is None

def test_move_note_before(db):
    # Create test notes: 3 -> 2 -> 1
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", next_id="1")
    note3 = TestNote(id="3", content="3", next_id="2")
    note1.prev_id = "2"
    note2.prev_id = "3"
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Move note 3 before note 1 (should become: 2 -> 3 -> 1)
    LinkedListManager.move_note(db, TestNote, "3", "1", True, None)
    
    # Verify the new order
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in notes] == ["2", "3", "1"]
    
    # Verify all bidirectional links
    note2 = db.query(TestNote).get("2")
    note3 = db.query(TestNote).get("3")
    note1 = db.query(TestNote).get("1")
    
    assert note2.prev_id is None
    assert note2.next_id == "3"
    assert note3.prev_id == "2"
    assert note3.next_id == "1"
    assert note1.prev_id == "3"
    assert note1.next_id is None

def test_move_note_as_child(db):
    # Create test notes: 3 -> 2 -> 1
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", next_id="1")
    note3 = TestNote(id="3", content="3", next_id="2")
    note1.prev_id = "2"
    note2.prev_id = "3"
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Move note 3 as child of note 2
    LinkedListManager.move_note(db, TestNote, "3", "2", False, "2")
    
    # Verify the new order at root level
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1"]
    
    # Verify note 3 is now a child of note 2
    child_notes = LinkedListManager.get_ordered_list(db, TestNote, "2")
    assert [note.id for note in child_notes] == ["3"]
    
    # Verify all links
    note2 = db.query(TestNote).get("2")
    note3 = db.query(TestNote).get("3")
    note1 = db.query(TestNote).get("1")
    
    assert note2.prev_id is None
    assert note2.next_id == "1"
    assert note3.parent_id == "2"
    assert note3.prev_id is None
    assert note3.next_id is None
    assert note1.prev_id == "2"
    assert note1.next_id is None 

def test_move_note_from_child_to_root(db):
    # Create initial structure:
    # Root level: 2 -> 1
    # Under 2: 3
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", next_id="1")
    note3 = TestNote(id="3", content="3", parent_id="2")
    note1.prev_id = "2"
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Move note 3 from being child of 2 to root level after note 1
    LinkedListManager.move_note(db, TestNote, "3", "1", False, None)
    
    # Verify root level order
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1", "3"]
    
    # Verify note 3 is no longer a child of note 2
    child_notes = LinkedListManager.get_ordered_list(db, TestNote, "2")
    assert len(child_notes) == 0
    
    # Verify all links
    note2 = db.query(TestNote).get("2")
    note3 = db.query(TestNote).get("3")
    note1 = db.query(TestNote).get("1")
    
    assert note2.prev_id is None
    assert note2.next_id == "1"
    assert note3.parent_id is None
    assert note3.prev_id == "1"
    assert note3.next_id is None
    assert note1.prev_id == "2"
    assert note1.next_id == "3"

def test_move_note_between_different_parents(db):
    # Create initial structure:
    # Root level: 2 -> 1
    # Under 2: 3
    # Under 1: 4
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", next_id="1")
    note3 = TestNote(id="3", content="3", parent_id="2")
    note4 = TestNote(id="4", content="4", parent_id="1")
    note1.prev_id = "2"
    
    db.add_all([note1, note2, note3, note4])
    db.commit()
    
    # Move note 3 from being child of 2 to being child of 1
    LinkedListManager.move_note(db, TestNote, "3", "4", False, "1")
    
    # Verify root level unchanged
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1"]
    
    # Verify note 3 is now under note 1
    child_notes = LinkedListManager.get_ordered_list(db, TestNote, "1")
    assert [note.id for note in child_notes] == ["4", "3"]
    
    # Verify note 2 has no children
    child_notes = LinkedListManager.get_ordered_list(db, TestNote, "2")
    assert len(child_notes) == 0 