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

def test_move_note_to_empty_parent(db):
    # Create initial structure:
    # Root level: 2 -> 1
    # Under 2: 3
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", next_id="1")
    note3 = TestNote(id="3", content="3", parent_id="2")
    note1.prev_id = "2"
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Move note 3 to be child of note 1 (which has no children)
    LinkedListManager.move_note(db, TestNote, "3", "1", False, "1")
    
    # Verify root level unchanged
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1"]
    
    # Verify note 3 is now under note 1
    child_notes = LinkedListManager.get_ordered_list(db, TestNote, "1")
    assert [note.id for note in child_notes] == ["3"]

def test_move_note_chain(db):
    # Create initial structure:
    # Root: 1 -> 2 -> 3
    note1 = TestNote(id="1", content="1", next_id="2")
    note2 = TestNote(id="2", content="2", next_id="3", prev_id="1")
    note3 = TestNote(id="3", content="3", prev_id="2")
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Move middle note (2) to end
    LinkedListManager.move_note(db, TestNote, "2", "3", False, None)
    
    # Verify new order: 1 -> 3 -> 2
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in notes] == ["1", "3", "2"]
    
    # Verify all links are correct
    note1 = db.query(TestNote).get("1")
    note2 = db.query(TestNote).get("2")
    note3 = db.query(TestNote).get("3")
    
    assert note1.prev_id is None
    assert note1.next_id == "3"
    assert note2.prev_id == "3"
    assert note2.next_id is None
    assert note3.prev_id == "1"
    assert note3.next_id == "2"

def test_move_note_to_parent_with_children(db):
    # Create initial structure:
    # Root: 1 -> 2
    # Under 1: 3
    # Under 2: 4
    note1 = TestNote(id="1", content="1", next_id="2")
    note2 = TestNote(id="2", content="2", prev_id="1")
    note3 = TestNote(id="3", content="3", parent_id="1")
    note4 = TestNote(id="4", content="4", parent_id="2")
    
    db.add_all([note1, note2, note3, note4])
    db.commit()
    
    # Move note 3 to be child of note 2 before note 4
    LinkedListManager.move_note(db, TestNote, "3", "4", True, "2")
    
    # Verify root level unchanged
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1", "2"]
    
    # Verify note 3 is now before note 4 under note 2
    child_notes = LinkedListManager.get_ordered_list(db, TestNote, "2")
    assert [note.id for note in child_notes] == ["3", "4"]
    
    # Verify all links
    note3 = db.query(TestNote).get("3")
    note4 = db.query(TestNote).get("4")
    
    assert note3.parent_id == "2"
    assert note3.prev_id is None
    assert note3.next_id == "4"
    assert note4.prev_id == "3"
    assert note4.next_id is None

def test_move_multiple_notes_sequence(db):
    """Test moving multiple notes in sequence to ensure stability"""
    # Create: 1 -> 2 -> 3 -> 4 -> 5
    notes = []
    for i in range(1, 6):
        note = TestNote(id=str(i), content=str(i))
        if i > 1:
            note.prev_id = str(i-1)
        if i < 5:
            note.next_id = str(i+1)
        notes.append(note)
    
    db.add_all(notes)
    db.commit()
    
    # Move 2 after 4: 1 -> 3 -> 4 -> 2 -> 5
    LinkedListManager.move_note(db, TestNote, "2", "4", False, None)
    # Move 3 after 4: 1 -> 4 -> 3 -> 2 -> 5
    LinkedListManager.move_note(db, TestNote, "3", "4", False, None)
    # Move 1 before 3: 4 -> 1 -> 3 -> 2 -> 5
    LinkedListManager.move_note(db, TestNote, "1", "3", True, None)
    
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in notes] == ["4", "1", "3", "2", "5"]

def test_deep_nesting_moves(db):
    """Test moving notes between different levels of nesting"""
    # Create structure:
    # Root: 1
    #   - 2
    #     - 3
    #       - 4
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", parent_id="1")
    note3 = TestNote(id="3", content="3", parent_id="2")
    note4 = TestNote(id="4", content="4", parent_id="3")
    
    db.add_all([note1, note2, note3, note4])
    db.commit()
    
    # Move 4 to be child of 1
    LinkedListManager.move_note(db, TestNote, "4", "1", False, "1")
    
    # Verify 4 is now direct child of 1
    children = LinkedListManager.get_ordered_list(db, TestNote, "1")
    assert [note.id for note in children] == ["2", "4"]
    
    # Move 3 to root
    LinkedListManager.move_note(db, TestNote, "3", "1", False, None)
    
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1", "3"]

def test_long_chain_operations(db):
    """Test operations on a very long chain"""
    # Create a chain of 20 notes
    notes = []
    for i in range(1, 21):
        note = TestNote(id=str(i), content=str(i))
        if i > 1:
            note.prev_id = str(i-1)
        if i < 20:
            note.next_id = str(i+1)
        notes.append(note)
    
    db.add_all(notes)
    db.commit()
    
    # Move first note (1) to end
    LinkedListManager.move_note(db, TestNote, "1", "20", False, None)
    
    # Move last note (20) to start
    LinkedListManager.move_note(db, TestNote, "20", "2", True, None)
    
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert notes[0].id == "20"
    assert notes[-1].id == "1"
    
    # Verify all links are intact
    for i in range(len(notes)-1):
        assert notes[i].next_id == notes[i+1].id
        assert notes[i+1].prev_id == notes[i].id

def test_invalid_moves(db):
    """Test handling of invalid move operations"""
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", parent_id="1")
    
    db.add_all([note1, note2])
    db.commit()
    
    # Try to move note to itself
    LinkedListManager.move_note(db, TestNote, "1", "1", False, None)
    
    # Try to move note to its child
    LinkedListManager.move_note(db, TestNote, "1", "2", False, "2")
    
    # Verify structure remains unchanged
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1"]
    
    children = LinkedListManager.get_ordered_list(db, TestNote, "1")
    assert [note.id for note in children] == ["2"]

def test_circular_reference_prevention(db):
    """Test prevention of circular parent-child relationships"""
    # Create structure:
    # Root: 1
    #   - 2
    #     - 3
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", parent_id="1")
    note3 = TestNote(id="3", content="3", parent_id="2")
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Try to move parent under its own child
    LinkedListManager.move_note(db, TestNote, "1", "3", False, "3")
    
    # Verify structure remains unchanged
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1"]
    
    level1 = LinkedListManager.get_ordered_list(db, TestNote, "1")
    assert [note.id for note in level1] == ["2"]
    
    level2 = LinkedListManager.get_ordered_list(db, TestNote, "2")
    assert [note.id for note in level2] == ["3"]


def test_bulk_operations(db):
    """Test performance with bulk operations"""
    # Create 100 notes in a chain
    notes = []
    for i in range(1, 101):
        note = TestNote(id=str(i), content=str(i))
        if i > 1:
            note.prev_id = str(i-1)
        if i < 100:
            note.next_id = str(i+1)
        notes.append(note)
    
    db.add_all(notes)
    db.commit()
    
    # Move every 10th note to the end
    for i in range(10, 101, 10):
        LinkedListManager.move_note(db, TestNote, str(i), "100", False, None)
    
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    
    # Verify the moves maintained list integrity
    for i in range(len(notes)-1):
        assert notes[i].next_id == notes[i+1].id
        assert notes[i+1].prev_id == notes[i].id

def test_move_to_start_of_list(db):
    """Test moving a note to the start of a list"""
    # Create structure: 1 -> 2 -> 3 -> 4
    note1 = TestNote(id="1", content="1", next_id="2")
    note2 = TestNote(id="2", content="2", prev_id="1", next_id="3")
    note3 = TestNote(id="3", content="3", prev_id="2", next_id="4")
    note4 = TestNote(id="4", content="4", prev_id="3")
    
    db.add_all([note1, note2, note3, note4])
    db.commit()
    
    # Move note4 to start by inserting before note1
    LinkedListManager.move_note(db, TestNote, "4", "1", True, None)
    
    # Verify new order: 4 -> 1 -> 2 -> 3
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in notes] == ["4", "1", "2", "3"]

def test_move_to_end_of_list(db):
    """Test moving a note to the end of a list"""
    # Create structure: 1 -> 2 -> 3 -> 4
    note1 = TestNote(id="1", content="1", next_id="2")
    note2 = TestNote(id="2", content="2", prev_id="1", next_id="3")
    note3 = TestNote(id="3", content="3", prev_id="2", next_id="4")
    note4 = TestNote(id="4", content="4", prev_id="3")
    
    db.add_all([note1, note2, note3, note4])
    db.commit()
    
    # Move note1 to end by inserting after note4
    LinkedListManager.move_note(db, TestNote, "1", "4", False, None)
    
    # Verify new order: 2 -> 3 -> 4 -> 1
    notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in notes] == ["2", "3", "4", "1"]

def test_move_between_nested_lists(db):
    """Test moving notes between lists at different nesting levels"""
    # Create structure:
    # 1
    #  └─ 2
    #      └─ 3
    # 4
    #  └─ 5
    #      └─ 6
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", parent_id="1")
    note3 = TestNote(id="3", content="3", parent_id="2")
    note4 = TestNote(id="4", content="4")
    note5 = TestNote(id="5", content="5", parent_id="4")
    note6 = TestNote(id="6", content="6", parent_id="5")
    
    db.add_all([note1, note2, note3, note4, note5, note6])
    db.commit()
    
    # Move note3 to be under note4, before note5
    LinkedListManager.move_note(db, TestNote, "3", "5", True, "4")
    
    # Verify note3 is now under note4, before note5
    children = LinkedListManager.get_ordered_list(db, TestNote, "4")
    assert [note.id for note in children] == ["3", "5"]
    
    # Move note5 (with its child note6) to be under note1
    LinkedListManager.move_note(db, TestNote, "5", "2", False, "1")
    
    # Verify note5 is now under note1, after note2
    children = LinkedListManager.get_ordered_list(db, TestNote, "1")
    assert [note.id for note in children] == ["2", "5"]
    
    # Verify note6 maintained its relationship with note5
    assert note6.parent_id == "5"

def test_move_to_empty_list(db):
    """Test moving a note to an empty list"""
    # Create structure:
    # 1 -> 2 -> 3
    # 4 (empty)
    note1 = TestNote(id="1", content="1", next_id="2")
    note2 = TestNote(id="2", content="2", prev_id="1", next_id="3")
    note3 = TestNote(id="3", content="3", prev_id="2")
    note4 = TestNote(id="4", content="4")  # No children
    
    db.add_all([note1, note2, note3, note4])
    db.commit()
    
    # Move note2 to be first child of note4
    LinkedListManager.move_note(db, TestNote, "2", "4", False, "4")
    
    # Verify root level is now 1 -> 3
    root_notes = LinkedListManager.get_ordered_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1", "3"]
    
    # Verify note2 is now the only child of note4
    children = LinkedListManager.get_ordered_list(db, TestNote, "4")
    assert [note.id for note in children] == ["2"]

def test_prevent_circular_nesting(db):
    """Test prevention of circular parent-child relationships"""
    # Create structure:
    # 1
    #  └─ 2
    #      └─ 3
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", parent_id="1")
    note3 = TestNote(id="3", content="3", parent_id="2")
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Try to move note1 under note3 (should fail silently)
    LinkedListManager.move_note(db, TestNote, "1", "3", False, "3")
    
    # Verify structure hasn't changed
    assert note1.parent_id is None
    assert note2.parent_id == "1"
    assert note3.parent_id == "2"
    
    # Try to move note2 under note3 (should fail silently)
    LinkedListManager.move_note(db, TestNote, "2", "3", False, "3")
    
    # Verify structure hasn't changed
    assert note2.parent_id == "1"
    assert note3.parent_id == "2"