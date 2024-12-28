from tests.unit.common import *


def test_sequence_add(db):
    # Clear existing notes
    db.query(DBNote).delete()
    db.commit()

    K = 100

    for k in range(1, K + 1):
        # Add new note
        note_id = str(k)
        LinkedListManager.create_note_top(db, note_id)

        # Update note value
        note = db.get(DBNote, note_id)
        note.content = str(k)
        db.commit()

    # Verify the sequence
    current_note = db.query(DBNote).filter(DBNote.prev_id == None).first()
    for expected_value in range(K, 0, -1):
        assert current_note.content == str(expected_value), f"Expected {expected_value}, got {current_note.content}"
        current_note = db.query(DBNote).filter(DBNote.id == current_note.next_id).first()

    assert current_note is None, "There should be no more notes in the sequence"


def test_sequence_add_v2(db):
    # Clear existing notes
    db.query(DBNote).delete()
    db.commit()

    K = 100

    added = []

    for k in range(K):
        # Add new note
        note_id = str(uuid.uuid4())
        LinkedListManager.create_note_top(db, note_id)
        db.commit()
        added.append(note_id)

    assert len(added) == K, f"Expected {K} notes, got {len(added)}"

    for k, note_id in enumerate(reversed(added)):
        note = db.get(DBNote, note_id)
        note.content = str(k)
        db.commit()

    # Verify the sequence
    current_note = db.query(DBNote).filter(DBNote.prev_id == None).first()
    for expected_value in range(K):
        assert current_note.content == str(expected_value), f"Expected {expected_value}, got {current_note.content}"
        current_note = db.query(DBNote).filter(DBNote.id == current_note.next_id).first()

    assert current_note is None, "There should be no more notes in the sequence"