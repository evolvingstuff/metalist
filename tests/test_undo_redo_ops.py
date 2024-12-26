from tests.common import *


def test_undo_redo_ops(db):

    SEED = 42
    NODES = 5

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

    # Perform assignment operations
    for i in range(NODES):

        with transaction_scope(db):
             #LinkedListManager.update_note(db, str(i), f"{i}")
             note_id = str(i)
             new_value = f"{i}"
             api_transaction_decorator(lambda:
                                       LinkedListManager.update_note(db, note_id, new_value)
                                       )()

        print(f"\n=== State after {i+1} operations ===")
        visualize_tree(db)

    command_stack = global_state["command_stack"]
    print(f"Command stack: {command_stack.stack}")
    assert len(command_stack.stack) == NODES, f"Expected {NODES} operations, got {len(command_stack.stack)}"
    assert command_stack.current_index == NODES - 1, f"Expected current index {NODES - 1}, got {command_stack.current_index}"

    ##############################
    # UNDO

    for i in range(NODES):
        with transaction_scope(db):
            LinkedListManager.undo(db)
        print(f"\n=== State after undo {i+1} operations ===")
        visualize_tree(db)

    print(f"Command stack: {command_stack.stack}")
    assert len(command_stack.stack) == NODES, f"Expected {NODES} operations, got {len(command_stack.stack)}"
    assert command_stack.current_index == -1, f"Expected current index -1, got {command_stack.current_index}"

    for i in range(NODES):
        with transaction_scope(db):
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
        with transaction_scope(db):
            LinkedListManager.redo(db)
        print(f"\n=== State after redo {i+1} operations ===")
        visualize_tree(db)
        note = LinkedListManager.get_note(db, note_id)
        assert note.content == str(i), f"Expected filled content, got {note.content}"

    print(f"Command stack: {command_stack.stack}")
    assert len(command_stack.stack) == NODES, f"Expected {NODES} operations, got {len(command_stack.stack)}"
    assert command_stack.current_index == NODES-1, f"Expected current index {NODES-1}, got {command_stack.current_index}"

    for i in range(NODES):
        with transaction_scope(db):
            note = LinkedListManager.get_note(db, note_id)
            assert note.content == str(i), f"Expected filled content, got {note.content}"

    # Validate after each operation
    with transaction_scope(db):
        if not LinkedListManager.validate_list(db, None):
            raise ValueError(f"Invalid list structure under parent None")

    print("Validation successful!")

    print('DONZO')
