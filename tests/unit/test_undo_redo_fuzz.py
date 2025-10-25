import random
import pytest

from tests.unit.common import visualize_tree, DBNote, db  # noqa: F401 - fixture import
from app.services.transaction_manager import get_transaction_manager
from app.services.note_service import NoteService
from app.services.undo_service import UndoRedoService
from app.models.enums import MovePosition
from fastapi import HTTPException

UNDO_REDO_INTERVAL = 4
CLIENT_ID = "fuzz-client"


def refresh_active_ids(db):
    return sorted({id for (id,) in db.query(DBNote.id).all()})


def note_service(db, transaction_manager):
    return NoteService(db, transaction_manager, CLIENT_ID)


def test_fuzz_undo_redo(db):
    """Randomized operations driven through NoteService to exercise undo/redo."""
    seed = 42
    random.seed(seed)

    # Seed initial data directly, then clear undo stack before fuzzing
    initial_notes = []
    for i in range(5):
        note = DBNote(id=str(i), content=f"Note {i}")
        if i > 0:
            note.prev_id = str(i - 1)
            initial_notes[i - 1].next_id = str(i)
        initial_notes.append(note)

    db.add_all(initial_notes)
    db.commit()

    print(f"\n=== Starting Mutation+Drag Fuzz Test with seed: {seed} ===")
    visualize_tree(db)

    transaction_manager = get_transaction_manager()
    transaction_manager.command_stack.clear_all()

    active_note_ids = refresh_active_ids(db)

    operation_counts = {
        'delete': 0,
        'add_click': 0,
        'add_drag': 0,
        'add_sibling': 0,
        'add_child': 0,
        'move': 0
    }

    for step in range(250):
        db.expire_all()
        if step % 1 == 0 and step > 0:
            print(f"\n=== State after {step} operations ===")
            visualize_tree(db)

        op_choice = random.random()

        if op_choice < 0.2 and len(active_note_ids) > 2:
            # Delete
            target_id = random.choice(active_note_ids)
            print(f"Deleting note {target_id}")
            try:
                with note_service(db, transaction_manager) as service:
                    service.delete_note(target_id)
                operation_counts['delete'] += 1
            except (HTTPException, RuntimeError) as exc:
                print(f"Delete failed: {exc}")
                continue
            active_note_ids = refresh_active_ids(db)
            print("Delete successful!")

        elif op_choice < 0.4:
            # Create note in various ways
            add_type = random.choice(['click', 'drag', 'sibling', 'child'])
            print(f"Adding new note via {add_type}")
            try:
                with note_service(db, transaction_manager) as service:
                    if add_type == 'click':
                        result = service.create_note()
                        operation_counts['add_click'] += 1
                    elif add_type == 'drag' and active_note_ids:
                        target_id = random.choice(active_note_ids)
                        target = db.get(DBNote, target_id)
                        drop_type = random.choice(['inside', 'before', 'after'])
                        print(f"Dragging to {target_id} ({drop_type})")
                        created = service.create_note()
                        new_note_id = created['id']
                        if drop_type == 'inside':
                            service.move_note(
                                note_id=new_note_id,
                                new_parent_id=target_id,
                                sibling_id=None,
                                position=None,
                            )
                        else:
                            position = MovePosition.BEFORE if drop_type == 'before' else MovePosition.AFTER
                            service.move_note(
                                note_id=new_note_id,
                                new_parent_id=target.parent_id,
                                sibling_id=target_id,
                                position=position,
                            )
                        result = {"id": new_note_id}
                        operation_counts['add_drag'] += 1
                    elif add_type == 'sibling' and active_note_ids:
                        target_id = random.choice(active_note_ids)
                        result = service.create_sibling_note(target_id)
                        operation_counts['add_sibling'] += 1
                    elif add_type == 'child' and active_note_ids:
                        target_id = random.choice(active_note_ids)
                        result = service.create_child_note(target_id)
                        operation_counts['add_child'] += 1
                    else:
                        result = service.create_note()
                        operation_counts['add_click'] += 1
                new_id = result['id']
                print(f"Add successful! id={new_id}")
            except (HTTPException, RuntimeError) as exc:
                print(f"Add failed: {exc}")
                continue
            active_note_ids = refresh_active_ids(db)

        else:
            # Move
            if len(active_note_ids) < 2:
                continue
            note_id = random.choice(active_note_ids)
            note = db.get(DBNote, note_id)
            potential_parents = active_note_ids + [None]
            new_parent_id = random.choice(potential_parents)
            sibling_id = None
            position = None

            if new_parent_id == note_id:
                continue

            if new_parent_id is not None:
                siblings = db.query(DBNote).filter(
                    DBNote.parent_id == new_parent_id,
                    DBNote.id != note_id
                ).all()
                if siblings and random.choice([True, False]):
                    sibling = random.choice(siblings)
                    sibling_id = sibling.id
                    position = random.choice([MovePosition.BEFORE, MovePosition.AFTER])

            print(f"Moving note {note_id} to parent {new_parent_id} relative to {sibling_id} ({position})")
            try:
                with note_service(db, transaction_manager) as service:
                    service.move_note(
                        note_id=note_id,
                        new_parent_id=new_parent_id,
                        sibling_id=sibling_id,
                        position=position,
                    )
                operation_counts['move'] += 1
                print("Move successful!")
            except (HTTPException, RuntimeError, ValueError) as exc:
                print(f"Move failed: {exc}")
                continue

        # Periodic undo/redo
        if active_note_ids and step % UNDO_REDO_INTERVAL == 0:
            undo_service = UndoRedoService(db, transaction_manager)
            if random.choice([True, False]):
                print("Performing undo")
                result = undo_service.undo(CLIENT_ID)
            else:
                print("Performing redo")
                result = undo_service.redo(CLIENT_ID)
            print(result)
            visualize_tree(db)

        active_note_ids = refresh_active_ids(db)

    print("Operation counts:", operation_counts)
