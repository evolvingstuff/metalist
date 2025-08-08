from tests.unit.common import *
from app.services.transaction_manager import get_transaction_manager
from app.services.undo_service import UndoRedoService
from app.services.note_service import NoteService


def test_undo_redo_ops(db):

    NODES = 3

    # Create initial notes in a valid linked list structure
    with transaction_scope(db):
        notes = []
        for i in range(NODES):
            note = DBNote(id=str(i), content=f"")
            if i > 0:
                note.prev_id = str(i - 1)
                notes[i - 1].next_id = str(i)
            notes.append(note)
        db.add_all(notes)

    print("\n=== Initial State ===")
    visualize_tree(db)

    # Get transaction manager
    transaction_manager = get_transaction_manager()
    
    # Perform assignment operations using the service layer (which tracks transactions)
    for i in range(NODES):
        note_id = str(i)
        new_value = f"val{i}"
        
        # Use the NoteService which properly tracks transactions
        with NoteService(db, transaction_manager) as service:
            service.update_note(note_id, new_value)

        print(f"\n=== State after {i+1} operations ===")
        visualize_tree(db)

    command_stack = transaction_manager.command_stack
    print(f"Command stack: {command_stack.stack}")
    assert len(command_stack.stack) == NODES, f"Expected {NODES} operations, got {len(command_stack.stack)}"
    assert command_stack.current_index == NODES - 1, f"Expected current index {NODES - 1}, got {command_stack.current_index}"

    ##############################
    # UNDO
    
    undo_service = UndoRedoService(db, transaction_manager)

    for i in range(NODES):
        result = undo_service.undo()
        print(f"\n=== State after undo {i+1} operations ===")
        visualize_tree(db)

    print(command_stack)
    assert len(command_stack.stack) == NODES, f"Expected {NODES} operations, got {len(command_stack.stack)}"
    assert command_stack.current_index == -1, f"Expected current index -1, got {command_stack.current_index}"

    for i in range(NODES):
        with transaction_scope(db):
            note_id = str(i)
            note = LinkedListManager.get_note(db, note_id)
            assert note.content == "", f"Expected empty content, got {note.content}"

    # Validate after each operation
    with transaction_scope(db):
        if not LinkedListManager.validate_list(db, None):
            raise ValueError(f"Invalid list structure under parent None")

    print("Validation successful!")

    ################################
    # REDO

    for i in range(NODES):
        note_id = str(i)
        result = undo_service.redo()
        print(f"\n=== State after redo {i+1} operations ===")
        visualize_tree(db)
        note = LinkedListManager.get_note(db, note_id)
        assert note.content != '', f"Expected refilled content, got empty string <{note.content}> | loc 1"

    print(command_stack)
    assert len(command_stack.stack) == NODES, f"Expected {NODES} operations, got {len(command_stack.stack)}"
    assert command_stack.current_index == NODES-1, f"Expected current index {NODES-1}, got {command_stack.current_index}"

    for i in range(NODES):
        note_id = str(i)
        with transaction_scope(db):
            note = LinkedListManager.get_note(db, note_id)
            assert note.content != '', f"Expected refilled content, got empty string | loc 1"

    # Validate after each operation
    with transaction_scope(db):
        if not LinkedListManager.validate_list(db, None):
            raise ValueError(f"Invalid list structure under parent None")

    print("Validation successful!")

