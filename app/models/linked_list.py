from typing import List, Optional, Any
from sqlalchemy.orm import Session
from enum import Enum

class Position(Enum):
    BEFORE = "before"
    AFTER = "after"

class LinkedListManager:
    @staticmethod
    def validate_list(db: Session, model_class, parent_id: Optional[str] = None) -> bool:
        """Validate the linked list structure"""
        notes = db.query(model_class).filter(model_class.parent_id == parent_id).all()
        if not notes:
            return True

        # Single note case
        if len(notes) == 1:
            return True  # Any link state is valid for a single note

        # Multiple notes - should have exactly one head and one tail
        heads = [note for note in notes if note.prev_id is None]
        tails = [note for note in notes if note.next_id is None]

        if len(heads) != 1 or len(tails) != 1:
            return False

        # Traverse from head and verify links
        head = heads[0]
        seen = {head.id}
        current = head

        while current.next_id:
            next_note = next((note for note in notes if note.id == current.next_id), None)
            if not next_note or next_note.id in seen or next_note.prev_id != current.id:
                return False
            seen.add(next_note.id)
            current = next_note

        return len(seen) == len(notes)

    @staticmethod
    def get_ordered_child_list(db: Session, model_class, parent_id: Optional[str] = None) -> List[Any]:
        """Get an ordered list of child notes for the given parent_id"""
        query = db.query(model_class)
        if parent_id is None:
            # When getting root notes, we need ALL notes that have no parent
            query = query.filter(model_class.parent_id.is_(None))
        else:
            query = query.filter(model_class.parent_id == parent_id)
        
        # Get all notes for this level
        all_notes = query.all()
        if not all_notes:
            return []
        
        # Find notes with no prev_id
        first_notes = [note for note in all_notes if note.prev_id is None]
        if len(first_notes) > 1:
            raise ValueError(f"Invalid state: Multiple notes without prev_id found at same level: {[n.id for n in first_notes]}")
        elif len(first_notes) == 0:
            raise ValueError(f"Invalid state: No note without prev_id found at this level")
        
        first = first_notes[0]
        
        # Build ordered list
        ordered = [first]
        current = first
        seen = {first.id}
        
        # Follow next_id chain
        while current.next_id:
            next_note = next((note for note in all_notes if note.id == current.next_id), None)
            if not next_note:
                raise ValueError(f"Invalid state: Note {current.id} points to non-existent next_id {current.next_id}")
            if next_note.id in seen:
                raise ValueError(f"Invalid state: Circular reference detected at note {current.id}")
            ordered.append(next_note)
            seen.add(next_note.id)
            current = next_note
        
        # Verify we found all notes
        if len(ordered) != len(all_notes):
            missing = set(note.id for note in all_notes) - seen
            raise ValueError(f"Invalid state: Notes not in chain: {missing}")
        
        return ordered

    @staticmethod
    def _would_create_cycle(db, model_class, note_id: str, new_parent_id: str) -> bool:
        """Check if moving note to new_parent would create a parent-child cycle"""
        if not new_parent_id:
            return False

        current = new_parent_id
        seen = set()
        while current and current not in seen:
            if current == note_id:
                return True
            seen.add(current)
            parent = db.query(model_class).get(current)
            if not parent:
                break
            current = parent.parent_id
        return False

    @staticmethod
    def move_note(
        db: Session,
        model_class,
        note_id: str,
        new_parent_id: str,
        sibling_id: Optional[str] = None,
        position: Optional[Position] = None
    ):
        """Move a note to a new parent, optionally positioning it relative to a sibling"""
        if sibling_id == note_id:
            raise ValueError("Cannot move note relative to itself")
        
        if new_parent_id == note_id:
            raise ValueError("Cannot make note a child of itself")
        
        if sibling_id is not None and position is None:
            raise ValueError("Position must be specified when sibling_id is provided")
        
        if sibling_id is None and position is not None:
            raise ValueError("Position cannot be specified without a sibling_id")

        note = db.query(model_class).get(note_id)
        if not note:
            raise ValueError(f"Note {note_id} not found")

        # Store original state for rollback
        old_prev_id = note.prev_id
        old_next_id = note.next_id
        old_parent_id = note.parent_id

        def is_descendant(parent_id: str, potential_child_id: str) -> bool:
            """Check if potential_child_id is a descendant of parent_id"""
            current = db.query(model_class).get(potential_child_id)
            while current and current.parent_id:
                if current.parent_id == parent_id:
                    return True
                current = db.query(model_class).get(current.parent_id)
            return False

        if new_parent_id and is_descendant(note_id, new_parent_id):
            raise ValueError("Cannot create circular parent-child relationship")

        try:
            # Step 1: Unlink note from current position
            if old_prev_id:
                prev_note = db.query(model_class).get(old_prev_id)
                if prev_note:
                    prev_note.next_id = old_next_id
            if old_next_id:
                next_note = db.query(model_class).get(old_next_id)
                if next_note:
                    next_note.prev_id = old_prev_id

            # Step 2: Clear note's links
            note.prev_id = None
            note.next_id = None
            note.parent_id = new_parent_id

            if sibling_id is None:
                # Case 1: Becoming the only/first child
                db.commit()
                return

            # Case 2: Positioning relative to a sibling
            sibling = db.query(model_class).get(sibling_id)
            if not sibling:
                raise ValueError(f"Sibling note {sibling_id} not found")

            if sibling.parent_id != new_parent_id:
                raise ValueError("Sibling must have the same parent")

            if position == Position.BEFORE:
                note.next_id = sibling_id
                note.prev_id = sibling.prev_id
                sibling.prev_id = note_id
                if note.prev_id:
                    prev_note = db.query(model_class).get(note.prev_id)
                    if prev_note:
                        prev_note.next_id = note_id
            else:  # Position.AFTER
                note.prev_id = sibling_id
                note.next_id = sibling.next_id
                sibling.next_id = note_id
                if note.next_id:
                    next_note = db.query(model_class).get(note.next_id)
                    if next_note:
                        next_note.prev_id = note_id

            db.commit()

        except Exception as e:
            db.rollback()
            note.prev_id = old_prev_id
            note.next_id = old_next_id
            note.parent_id = old_parent_id
            db.commit()
            raise