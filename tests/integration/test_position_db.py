"""Tests for position and indent fields with proper DB session management."""
from tests.unit.common import *


def test_create_note_with_position(db):
    """Test that creating a note sets position field correctly."""
    # Create first note
    note1 = DBNote(id="1", content="1", position="a0", indent=0)
    db.add(note1)
    db.commit()
    
    # Create second note
    note2 = DBNote(id="2", content="2", position="a1", indent=0)
    db.add(note2)
    db.commit()
    
    # Verify positions
    note1 = db.get(DBNote, "1")
    note2 = db.get(DBNote, "2")
    print(f"\nDebug positions:")
    print(f"note1.position = {note1.position}")
    print(f"note2.position = {note2.position}")
    assert note1.position == "a0"
    assert note2.position == "a1"
    assert note1.position < note2.position


def test_note_with_children_indentation(db):
    """Test that child notes have correct indentation."""
    # Create parent note
    parent = DBNote(id="parent", content="parent", position="a0", indent=0)
    db.add(parent)
    
    # Create child notes
    child1 = DBNote(
        id="child1",
        content="child1",
        parent_id="parent",
        position="a0",
        indent=1
    )
    child2 = DBNote(
        id="child2",
        content="child2",
        parent_id="parent",
        position="a1",
        indent=1
    )
    db.add_all([child1, child2])
    db.commit()
    
    # Verify indentation
    parent = db.get(DBNote, "parent")
    child1 = db.get(DBNote, "child1")
    child2 = db.get(DBNote, "child2")
    print(f"\nDebug indentation levels:")
    print(f"parent.indent = {parent.indent}")
    print(f"child1.indent = {child1.indent}")
    print(f"child2.indent = {child2.indent}")
    print(f"child1.position = {child1.position}")
    print(f"child2.position = {child2.position}")
    assert parent.indent == 0
    assert child1.indent == 1
    assert child2.indent == 1
    assert child1.position < child2.position


def test_deep_nesting_indentation(db):
    """Test indentation with multiple levels of nesting."""
    # Create a chain: root -> level1 -> level2 -> level3
    root = DBNote(id="root", content="root", position="a0", indent=0)
    level1 = DBNote(
        id="level1",
        content="level1",
        parent_id="root",
        position="a0",
        indent=1
    )
    level2 = DBNote(
        id="level2",
        content="level2",
        parent_id="level1",
        position="a0",
        indent=2
    )
    level3 = DBNote(
        id="level3",
        content="level3",
        parent_id="level2",
        position="a0",
        indent=3
    )
    
    db.add_all([root, level1, level2, level3])
    db.commit()
    
    # Verify indentation at each level
    root = db.get(DBNote, "root")
    level1 = db.get(DBNote, "level1")
    level2 = db.get(DBNote, "level2")
    level3 = db.get(DBNote, "level3")
    print(f"\nDebug indentation levels:")
    print(f"root.indent = {root.indent}")
    print(f"level1.indent = {level1.indent}")
    print(f"level2.indent = {level2.indent}")
    print(f"level3.indent = {level3.indent}")
    assert root.indent == 0
    assert level1.indent == 1
    assert level2.indent == 2
    assert level3.indent == 3


def test_sibling_positions(db):
    """Test that sibling notes maintain correct position ordering."""
    # Create a sequence of sibling notes
    positions = ["a0", "a1", "a2", "a3"]
    notes = []
    
    for i, pos in enumerate(positions):
        note = DBNote(
            id=f"note{i}",
            content=f"content{i}",
            position=pos,
            indent=0
        )
        notes.append(note)
    
    db.add_all(notes)
    db.commit()
    
    # Verify positions are ordered correctly
    for i in range(len(notes)-1):
        curr = db.get(DBNote, f"note{i}")
        next_note = db.get(DBNote, f"note{i+1}")
        print(f"\nDebug positions:")
        print(f"curr.position = {curr.position}")
        print(f"next_note.position = {next_note.position}")
        assert curr.position < next_note.position
