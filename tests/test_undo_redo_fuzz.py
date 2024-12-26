from tests.common import *

UNDO_REDO_INTERVAL = 4


def test_fuzz_undo_redo(db):

    """Like test_fuzz_linked_list_with_mutations but includes drag-and-drop creation"""
    SEED = 42
    NODES = 5
    STEPS = 250
    VISUALIZE_INTERVAL = 1

    print(f"\n=== Starting Mutation+Drag Fuzz Test with seed: {SEED} ===")
    random.seed(SEED)

    # Create initial notes in a valid linked list structure
    with transaction_scope(db):
        notes = []
        for i in range(NODES):
            note = DBNote(id=str(i), content=f"Note {i}")
            if i > 0:
                note.prev_id = str(i - 1)
                notes[i - 1].next_id = str(i)
            notes.append(note)

        db.add_all(notes)

    print("\n=== Initial State ===")
    visualize_tree(db)

    next_id = NODES  # For creating new notes
    with transaction_scope(db):
        active_note_ids = {id for (id,) in db.query(DBNote.id).all()}
    active_note_ids = sorted(list(active_note_ids))

    # Operation counters
    operation_counts = {
        'delete': 0,
        'add_click': 0,
        'add_drag': 0,
        'add_sibling': 0,
        'add_child': 0,
        'move': 0
    }

    # Perform random operations
    for i in range(STEPS):
        print(f'testing undo/redo: {i}')
        db.expire_all()
        if i % VISUALIZE_INTERVAL == 0 and i > 0:
            print(f"\n=== State after {i} operations ===")
            visualize_tree(db)

        operation = random.random()

        if operation < 0.2 and len(active_note_ids) > 2:  # 20% chance to delete
            # Delete operation
            note_id = random.choice(active_note_ids)
            print(f"Deleting note {note_id}")
            with transaction_scope(db):
                LinkedListManager.delete_note(db, note_id)
            active_note_ids = {id for (id,) in db.query(DBNote.id).all()}
            active_note_ids = sorted(list(active_note_ids))
            operation_counts['delete'] += 1
            print("Delete successful!")

        elif operation < 0.4:  # 20% chance to add new note
            new_id = str(next_id)
            next_id += 1

            add_type = random.choice(['click', 'drag', 'sibling', 'child'])
            print(f"Adding new note {new_id} via {add_type}")

            if add_type == 'drag' and active_note_ids:
                target_id = random.choice(active_note_ids)
                with transaction_scope(db):
                    target = db.get(DBNote, target_id)

                drop_type = random.choice(['inside', 'before', 'after'])
                print(f"Dragging to {target_id} ({drop_type})")

                if drop_type == 'inside':
                    with transaction_scope(db):
                        LinkedListManager.create_note_drop(
                            db,
                            new_id,
                            new_parent_id=target_id
                        )
                else:
                    with transaction_scope(db):
                        LinkedListManager.create_note_drop(
                            db,
                            new_id,
                            new_parent_id=target.parent_id,
                            sibling_id=target_id,
                            position=MovePosition.BEFORE if drop_type == 'before' else MovePosition.AFTER
                        )
                operation_counts['add_drag'] += 1
            elif add_type == 'sibling' and active_note_ids:
                target_id = random.choice(active_note_ids)
                with transaction_scope(db):
                    # TODO call actual op
                    LinkedListManager.create_note_top(db, new_id)
                    LinkedListManager.move_note(
                        db=db,
                        note_id=new_id,
                        new_parent_id=db.get(DBNote, target_id).parent_id,
                        sibling_id=target_id,
                        position=MovePosition.AFTER
                    )
                operation_counts['add_sibling'] += 1
            elif add_type == 'child' and active_note_ids:
                target_id = random.choice(active_note_ids)
                with transaction_scope(db):
                    # TODO call actual op
                    LinkedListManager.create_note_top(db, new_id)
                    LinkedListManager.move_note(
                        db=db,
                        note_id=new_id,
                        new_parent_id=target_id,
                        sibling_id=None,
                        position=None
                    )
                operation_counts['add_child'] += 1
            else:  # Regular click creation
                with transaction_scope(db):
                    LinkedListManager.create_note_top(db, new_id)
                operation_counts['add_click'] += 1

            active_note_ids.append(new_id)
            active_note_ids.sort()
            print("Add successful!")

        else:  # 60% chance for move operation
            if len(active_note_ids) < 2:
                continue

            note_id = random.choice(active_note_ids)
            with transaction_scope(db):
                note = db.get(DBNote, note_id)
            possible_parents = active_note_ids
            new_parent_id = random.choice(possible_parents + [None])
            sibling_id = None
            position = None

            if new_parent_id == note_id:
                with pytest.raises(ValueError, match="Cannot make a note its own parent"):
                    with transaction_scope(db):
                        LinkedListManager.move_note(
                            db=db,
                            note_id=note_id,
                            new_parent_id=new_parent_id,
                            sibling_id=sibling_id,
                            position=position
                        )
                continue

            print(f"Moving note {note_id} (currently under {note.parent_id})")
            print(f"To parent {new_parent_id}")

            use_sibling = random.choice([True, False])
            if use_sibling and new_parent_id is not None:
                with transaction_scope(db):
                    siblings = db.query(DBNote).filter(
                        DBNote.parent_id == new_parent_id,
                        DBNote.id != note_id
                    ).all()
                if siblings:
                    sibling_id = random.choice([s.id for s in siblings])
                    position = random.choice([MovePosition.BEFORE, MovePosition.AFTER])
                    print(f"Relative to sibling {sibling_id} ({position})")

            try:
                with transaction_scope(db):
                    LinkedListManager.move_note(
                        db=db,
                        note_id=note_id,
                        new_parent_id=new_parent_id,
                        sibling_id=sibling_id,
                        position=position
                    )
                operation_counts['move'] += 1
                print("Move successful!")
            except ValueError as e:
                print(f"Move failed: {str(e)}")
                continue

        ### <<<<<<<<<<
        # Every few steps, perform an undo or redo
        if i % UNDO_REDO_INTERVAL == 0:
            if random.choice([True, False]):
                # raise NotImplementedError("Redo is not implemented yet")
                print("Performing undo")
                with transaction_scope(db):
                    LinkedListManager.undo(db)
                print('UNDO SUCCESSFUL')
            else:
                # raise NotImplementedError("Redo is not implemented yet")
                print("Performing redo")
                with transaction_scope(db):
                    LinkedListManager.redo(db)
                print('REDO SUCCESSFUL')
            print('after undo/redo:')
            visualize_tree(db)
            # raise NotImplementedError("Redo is not implemented yet")

        # Validate after each operation
        with transaction_scope(db):
            if not LinkedListManager.validate_list(db, None):
                raise ValueError(f"Invalid list structure under parent None")

        with transaction_scope(db):
            existing_parents = db.query(DBNote.id).filter(
                DBNote.id.in_(
                    db.query(DBNote.parent_id).filter(DBNote.parent_id.isnot(None))
                )
            ).all()

        for (parent_id,) in existing_parents:
            with transaction_scope(db):
                if not LinkedListManager.validate_list(db, parent_id):
                    raise ValueError(f"Invalid list structure under parent {parent_id}")
        print("Validation successful!")

    # Check that all operations were performed at least once
    for op, count in operation_counts.items():
        if count == 0:
            raise AssertionError(f"Operation '{op}' was never performed.")

    print('DONZO')
