from tests.common import *


def test_undo_redo_ops(db):
    note_id = str(uuid.uuid4())
    new_note_id = str(uuid.uuid4())
    new_note_id2 = str(uuid.uuid4())
    new_note_id3 = str(uuid.uuid4())
    with transaction_scope(db):
        LinkedListManager.create_note_top(db, note_id)
        visualize_tree(db)

        # child
        LinkedListManager.create_note_top(db, new_note_id)
        LinkedListManager.move_note(
            db=db,
            note_id=new_note_id,
            new_parent_id=note_id,
            sibling_id=None,
            position=None
        )
        visualize_tree(db)

        # sibling of child
        node = db.get(DBNote, new_note_id)
        LinkedListManager.create_note_top(db, new_note_id2)
        LinkedListManager.move_note(
            db=db,
            note_id=new_note_id2,
            new_parent_id=node.parent_id,
            sibling_id=new_note_id,
            position=MovePosition.AFTER
        )
        visualize_tree(db)

        # drag and drop from +
        LinkedListManager.create_note_drop(
            db,
            new_note_id3,
            node.parent_id,
            sibling_id=new_note_id2,
            position=MovePosition.BEFORE
        )
        visualize_tree(db)
