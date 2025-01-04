from tests.unit.common import *
from app.models.linked_list_new import LinkedListManager


def test_move_note_after(db):
    # Create test notes in order: 3 -> 2 -> 1
    LinkedListManager.create_note_top(db, "1")
    LinkedListManager.create_note_top(db, "2")
    LinkedListManager.create_note_top(db, "3")
    db.commit()
    
    # Move note 3 after note 2 (should become: 2 -> 3 -> 1)
    LinkedListManager.move_note(
        db,
        note_id="3",
        sibling_id="2",
        position=MovePosition.AFTER
    )
    
    # Verify the new order through positions
    notes = LinkedListManager.get_ordered_child_list(db)
    assert [note.id for note in notes] == ["2", "3", "1"]
    
    # Verify positions are correctly ordered
    note2 = db.get(DBNote, "2")
    note3 = db.get(DBNote, "3")
    note1 = db.get(DBNote, "1")
    
    assert note2.position < note3.position < note1.position
    assert note2.indent == note3.indent == note1.indent == 0


def test_move_note_before(db):
    # Create test notes in order: 3 -> 2 -> 1
    LinkedListManager.create_note_top(db, "1")
    LinkedListManager.create_note_top(db, "2")
    LinkedListManager.create_note_top(db, "3")
    db.commit()
    
    # Move note 3 before note 1 (should become: 2 -> 3 -> 1)
    LinkedListManager.move_note(
        db,
        note_id="3",
        sibling_id="1",
        position=MovePosition.BEFORE
    )
    
    # Verify the new order through positions
    notes = LinkedListManager.get_ordered_child_list(db)
    assert [note.id for note in notes] == ["2", "3", "1"]
    
    # Verify positions are correctly ordered
    note2 = db.get(DBNote, "2")
    note3 = db.get(DBNote, "3")
    note1 = db.get(DBNote, "1")
    
    assert note2.position < note3.position < note1.position
    assert note2.indent == note3.indent == note1.indent == 0


def test_move_note_as_child(db):
    # Create test notes in order: 3 -> 2 -> 1
    LinkedListManager.create_note_top(db, "1")
    LinkedListManager.create_note_top(db, "2")
    LinkedListManager.create_note_top(db, "3")
    db.commit()
    
    # Move note 3 as child of note 2
    LinkedListManager.move_note(
        db,
        note_id="3",
        target_note=db.get(DBNote, "2")
    )
    
    # Verify root level order
    root_notes = LinkedListManager.get_ordered_child_list(db)
    assert [note.id for note in root_notes] == ["2", "1"]
    
    # Verify note 3 is now a child of note 2
    note2_children = LinkedListManager.get_children(db, db.get(DBNote, "2"))
    assert [note.id for note in note2_children] == ["3"]
    
    # Verify positions and indents
    note2 = db.get(DBNote, "2")
    note3 = db.get(DBNote, "3")
    note1 = db.get(DBNote, "1")
    
    assert note2.position < note3.position < note1.position
    assert note2.indent == 0
    assert note3.indent == 1
    assert note1.indent == 0 