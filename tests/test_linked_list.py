import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy import Column, String
from app.models.linked_list import LinkedListManager, Position

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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id=None,
        sibling_id="2",
        position=Position.AFTER
    )
    
    # Verify the new order
    notes = LinkedListManager.get_ordered_child_list(db, TestNote)
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id=None,
        sibling_id="1",
        position=Position.BEFORE
    )
    
    # Verify the new order
    notes = LinkedListManager.get_ordered_child_list(db, TestNote)
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
    
    # Move note 3 as child of note 2 (no siblings yet)
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id="2"
        # No sibling_id or position needed - becoming first child
    )
    
    # Verify the new order at root level
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1"]
    
    # Verify note 3 is now a child of note 2
    child_notes = LinkedListManager.get_ordered_child_list(db, TestNote, "2")
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id=None,
        sibling_id="1",
        position=Position.AFTER
    )
    
    # Verify root level order
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1", "3"]
    
    # Verify note 3 is no longer a child of note 2
    child_notes = LinkedListManager.get_ordered_child_list(db, TestNote, "2")
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
    
    # Move note 3 from being child of 2 to being child of 1, after note 4
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id="1",
        sibling_id="4",
        position=Position.AFTER
    )
    
    # Verify root level unchanged
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1"]
    
    # Verify note 3 is now under note 1
    child_notes = LinkedListManager.get_ordered_child_list(db, TestNote, "1")
    assert [note.id for note in child_notes] == ["4", "3"]
    
    # Verify note 2 has no children
    child_notes = LinkedListManager.get_ordered_child_list(db, TestNote, "2")
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id="1"
        # No sibling_id or position needed - becoming first child
    )
    
    # Verify root level unchanged
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["2", "1"]
    
    # Verify note 3 is now under note 1
    child_notes = LinkedListManager.get_ordered_child_list(db, TestNote, "1")
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="2",
        new_parent_id=None,
        sibling_id="3",
        position=Position.AFTER
    )
    
    # Verify new order: 1 -> 3 -> 2
    notes = LinkedListManager.get_ordered_child_list(db, TestNote)
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id="2",
        sibling_id="4",
        position=Position.BEFORE
    )
    
    # Verify root level unchanged
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1", "2"]
    
    # Verify note 3 is now before note 4 under note 2
    child_notes = LinkedListManager.get_ordered_child_list(db, TestNote, "2")
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="2",
        new_parent_id=None,
        sibling_id="4",
        position=Position.AFTER
    )
    
    # Move 3 after 4: 1 -> 4 -> 3 -> 2 -> 5
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id=None,
        sibling_id="4",
        position=Position.AFTER
    )
    
    # Move 1 before 3: 4 -> 1 -> 3 -> 2 -> 5
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="1",
        new_parent_id=None,
        sibling_id="3",
        position=Position.BEFORE
    )
    
    notes = LinkedListManager.get_ordered_child_list(db, TestNote)
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="4",
        new_parent_id="1",
        sibling_id="2",
        position=Position.AFTER
    )
    
    # Verify 4 is now direct child of 1
    children = LinkedListManager.get_ordered_child_list(db, TestNote, "1")
    assert [note.id for note in children] == ["2", "4"]
    
    # Move 3 to root
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id=None,
        sibling_id="1",
        position=Position.AFTER
    )
    
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="1",
        new_parent_id=None,
        sibling_id="20",
        position=Position.AFTER
    )
    
    # Move last note (20) to start
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="20",
        new_parent_id=None,
        sibling_id="2",
        position=Position.BEFORE
    )
    
    notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert notes[0].id == "20"
    assert notes[-1].id == "1"

def test_invalid_moves(db):
    """Test handling of invalid move operations"""
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2", parent_id="1")
    
    db.add_all([note1, note2])
    db.commit()
    
    # Try to move note to itself
    with pytest.raises(ValueError):
        LinkedListManager.move_note(
            db, 
            TestNote, 
            note_id="1",
            new_parent_id=None,
            sibling_id="1",
            position=Position.AFTER
        )
    
    # Try to move note to its child
    with pytest.raises(ValueError):
        LinkedListManager.move_note(
            db, 
            TestNote, 
            note_id="1",
            new_parent_id="2",
            sibling_id=None
        )
    
    # Verify structure remains unchanged
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1"]
    
    children = LinkedListManager.get_ordered_child_list(db, TestNote, "1")
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
    
    # Try to move parent under its own child - should raise error
    with pytest.raises(ValueError, match="Cannot create circular parent-child relationship"):
        LinkedListManager.move_note(
            db,
            TestNote,
            note_id="1",
            new_parent_id="3"
        )

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
    
    # Move every 10th note after the next note (not itself)
    for i in range(10, 91, 10):
        LinkedListManager.move_note(
            db, 
            TestNote, 
            note_id=str(i),
            new_parent_id=None,
            sibling_id=str(i+2),  # Move after i+2 instead of i
            position=Position.AFTER
        )

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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="4",
        new_parent_id=None,
        sibling_id="1",
        position=Position.BEFORE
    )
    
    # Verify new order: 4 -> 1 -> 2 -> 3
    notes = LinkedListManager.get_ordered_child_list(db, TestNote)
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
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="1",
        new_parent_id=None,
        sibling_id="4",
        position=Position.AFTER
    )
    
    # Verify new order: 2 -> 3 -> 4 -> 1
    notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in notes] == ["2", "3", "4", "1"]

def test_move_between_nested_lists(db):
    """Test moving notes between different nested lists"""
    # Create structure:
    # Root: 1 -> 4
    # Under 1: 2
    # Under 4: 3 -> 5
    note1 = TestNote(id="1", content="1", next_id="4")
    note2 = TestNote(id="2", content="2", parent_id="1")
    note3 = TestNote(id="3", content="3", parent_id="4")
    note4 = TestNote(id="4", content="4", prev_id="1")
    note5 = TestNote(id="5", content="5", parent_id="4", prev_id="3")
    note3.next_id = "5"
    
    db.add_all([note1, note2, note3, note4, note5])
    db.commit()
    
    # Move note 3 to be under note 1, after note 2
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="3",
        new_parent_id="1",
        sibling_id="2",
        position=Position.AFTER
    )
    
    # Verify the moves
    children = LinkedListManager.get_ordered_child_list(db, TestNote, "1")
    assert [note.id for note in children] == ["2", "3"]
    
    children = LinkedListManager.get_ordered_child_list(db, TestNote, "4")
    assert [note.id for note in children] == ["5"]

def test_move_to_empty_list(db):
    """Test moving a note to an empty list"""
    # Create structure:
    # Root: 1 -> 3 -> 4
    # Under 1: 2
    note1 = TestNote(id="1", content="1", next_id="3")
    note2 = TestNote(id="2", content="2", parent_id="1")
    note3 = TestNote(id="3", content="3", prev_id="1", next_id="4")
    note4 = TestNote(id="4", content="4", prev_id="3")  # Link into the chain
    
    db.add_all([note1, note2, note3, note4])
    db.commit()
    
    # Move note 2 to be child of note 4 (which has no children)
    LinkedListManager.move_note(
        db, 
        TestNote, 
        note_id="2",
        new_parent_id="4"
    )
    
    # Verify the moves
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1", "3", "4"]
    
    # Verify note 2 is now under note 4
    children = LinkedListManager.get_ordered_child_list(db, TestNote, "4")
    assert [note.id for note in children] == ["2"]

def test_invalid_position_parameters(db):
    """Test validation of position parameters"""
    note1 = TestNote(id="1", content="1")
    note2 = TestNote(id="2", content="2")
    
    db.add_all([note1, note2])
    db.commit()
    
    # Test: sibling_id without position
    with pytest.raises(ValueError, match="Position must be specified when sibling_id is provided"):
        LinkedListManager.move_note(
            db,
            TestNote,
            note_id="2",
            new_parent_id="1",
            sibling_id="1",
            position=None
        )
    
    # Test: position without sibling_id
    with pytest.raises(ValueError, match="Position cannot be specified without a sibling_id"):
        LinkedListManager.move_note(
            db,
            TestNote,
            note_id="2",
            new_parent_id="1",
            sibling_id=None,
            position=Position.AFTER
        )

def test_move_note_inside_parent(db: Session):
    # Setup: Create three notes in a sequence at root level
    note1 = TestNote(id="1", content="First")
    note2 = TestNote(id="2", content="Second")
    note3 = TestNote(id="3", content="Third")
    
    # Link them together at root level
    note1.next_id = note2.id
    note2.prev_id = note1.id
    note2.next_id = note3.id
    note3.prev_id = note2.id
    
    db.add_all([note1, note2, note3])
    db.commit()
    
    # Verify initial structure
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1", "2", "3"]
    
    # Act: Move note2 to become a child of note1
    LinkedListManager.move_note(
        db=db,
        model_class=TestNote,
        note_id=note2.id,
        new_parent_id=note1.id,
        sibling_id=None,
        position=None
    )
    
    # Refresh notes from database
    note1 = db.query(TestNote).get("1")
    note2 = db.query(TestNote).get("2")
    note3 = db.query(TestNote).get("3")
    
    # Assert:
    # 1. Verify root level notes
    root_notes = LinkedListManager.get_ordered_child_list(db, TestNote)
    assert [note.id for note in root_notes] == ["1", "3"]
    
    # 2. Verify note1's children
    children = LinkedListManager.get_ordered_child_list(db, TestNote, parent_id=note1.id)
    assert [note.id for note in children] == ["2"]
    
    # 3. Verify all links are maintained correctly
    assert note1.next_id == note3.id, "Note1 should link to Note3"
    assert note3.prev_id == note1.id, "Note3 should link back to Note1"
    assert note2.parent_id == note1.id, "Note2 should be child of Note1"
    assert note2.prev_id is None, "Note2 should have no prev as first child"
    assert note2.next_id is None, "Note2 should have no next as only child"

def test_move_note_maintains_single_head(db):
    # Create two root-level notes
    note1 = TestNote(id="note1", content="First")
    note2 = TestNote(id="note2", content="Second")
    db.add_all([note1, note2])
    db.commit()
    
    # Move note2 under note1
    LinkedListManager.move_note(
        db=db,
        model_class=TestNote,
        note_id=note2.id,
        new_parent_id=note1.id,
        sibling_id=None,
        position=None
    )
    
    # Verify only one note has prev_id=None under note1
    notes_without_prev = db.query(TestNote).filter(
        TestNote.prev_id == None,
        TestNote.parent_id == note1.id
    ).all()
    assert len(notes_without_prev) == 1

def test_move_note_with_children_maintains_single_head(db):
    # Create initial structure:
    # Root
    #   blah
    # child 1
    #   child 2
    #   test
    root = TestNote(id="root", content="Root")
    blah = TestNote(id="blah", content="blah", parent_id="root")
    child1 = TestNote(id="child1", content="child 1")
    child2 = TestNote(id="child2", content="child 2", parent_id="child1")
    test = TestNote(id="test", content="test", parent_id="child1", prev_id="child2")
    child2.next_id = "test"
    
    db.add_all([root, blah, child1, child2, test])
    db.commit()
    
    # Try to move Root under child1
    LinkedListManager.move_note(
        db=db,
        model_class=TestNote,
        note_id="root",
        new_parent_id="child1",
        sibling_id=None,
        position=None
    )
    
    # Verify only one note has prev_id=None under child1
    notes_without_prev = db.query(TestNote).filter(
        TestNote.prev_id == None,
        TestNote.parent_id == "child1"
    ).all()
    assert len(notes_without_prev) == 1