from typing import List, Optional, Any
from sqlalchemy.orm import Session


class LinkedListManager:
    @staticmethod
    def validate_list(db: Session, model_class, parent_id: Optional[str] = None) -> bool:
        """Validate the linked list structure"""
        notes = db.query(model_class).filter(model_class.parent_id == parent_id).all()
        if not notes:
            return True

        # Single note case
        if len(notes) == 1:
            note = notes[0]
            return note.prev_id is None and note.next_id is None

        # Find head
        head = next((note for note in notes if note.prev_id is None), None)
        if not head:
            return False

        # Traverse list and collect seen nodes
        seen = {head.id}
        current = head
        while current.next_id:
            next_note = next((note for note in notes if note.id == current.next_id), None)
            if not next_note:
                return False
            if next_note.id in seen:
                return False
            if next_note.prev_id != current.id:
                return False
            seen.add(next_note.id)
            current = next_note

        return len(seen) == len(notes)

    @staticmethod
    def get_ordered_list(db: Session, model_class, parent_id: Optional[str] = None) -> List[Any]:
        """Get an ordered list of notes"""
        notes = db.query(model_class).filter(model_class.parent_id == parent_id).all()
        if not notes:
            return []

        # Single note case
        if len(notes) == 1:
            return notes

        # Find head
        head = next((note for note in notes if note.prev_id is None), None)
        if not head:
            return notes  # Return all notes if no clear head found

        # Build ordered list
        ordered = [head]
        current = head
        seen = {head.id}
        note_dict = {note.id: note for note in notes}

        while current.next_id:
            if current.next_id not in note_dict:
                break
            next_note = note_dict[current.next_id]
            if next_note.id in seen:
                break
            ordered.append(next_note)
            seen.add(next_note.id)
            current = next_note

        # Add any remaining notes that weren't visited
        remaining = [note for note in notes if note.id not in seen]
        ordered.extend(remaining)

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
            current = parent.parent_id if parent else None
        return False

    @staticmethod
    def move_note(db: Session, model_class, note_id: str, target_id: str, insert_before: bool,
                  new_parent_id: Optional[str] = None):
        """Move a note within a list"""
        note = db.query(model_class).get(note_id)
        target = db.query(model_class).get(target_id)

        if not note or not target or note_id == target_id:
            return

        # Check for cycles
        if LinkedListManager._would_create_cycle(db, model_class, note_id, new_parent_id):
            return

        # Save old state for potential rollback
        old_prev_id = note.prev_id
        old_next_id = note.next_id
        old_parent_id = note.parent_id

        try:
            # Step 1: Remove note from its current position
            if old_prev_id:
                prev_note = db.query(model_class).get(old_prev_id)
                if prev_note:
                    prev_note.next_id = old_next_id

            if old_next_id:
                next_note = db.query(model_class).get(old_next_id)
                if next_note:
                    next_note.prev_id = old_prev_id

            # Step 2: Handle parent changes
            if new_parent_id:
                # Moving to become a child
                note.parent_id = new_parent_id
                if target_id == new_parent_id:
                    # Moving to empty parent - make it the only child
                    note.prev_id = None
                    note.next_id = None
                    db.commit()
                    return

            # Step 3: Set up new links
            target_parent = new_parent_id if new_parent_id is not None else target.parent_id
            note.parent_id = target_parent

            if not insert_before:
                # Insert after target
                next_id = target.next_id
                target.next_id = note_id
                note.prev_id = target_id
                note.next_id = next_id

                if next_id:
                    next_note = db.query(model_class).get(next_id)
                    if next_note:
                        next_note.prev_id = note_id
            else:
                # Insert before target
                prev_id = target.prev_id
                target.prev_id = note_id
                note.next_id = target_id
                note.prev_id = prev_id

                if prev_id:
                    prev_note = db.query(model_class).get(prev_id)
                    if prev_note:
                        prev_note.next_id = note_id

            db.commit()

        except Exception as e:
            # Restore original state
            db.rollback()
            note.prev_id = old_prev_id
            note.next_id = old_next_id
            note.parent_id = old_parent_id
            db.commit()
            raise