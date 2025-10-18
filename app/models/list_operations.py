from typing import Optional
from sqlalchemy.orm import Session
from .database import DBNote
from .enums import MovePosition
from ..services.note_store import store as note_store


class ListOperations:
    """Handles linked list manipulation operations"""
    
    @staticmethod
    def move_note(db: Session, note_id: str, new_parent_id: Optional[str] = None,
                  sibling_id: Optional[str] = None, position: Optional[MovePosition] = None):
        """Move a note to a new position"""
        try:
            print(f"DEBUG: Moving note {note_id} to new_parent_id={new_parent_id}, sibling_id={sibling_id}, position={position}")
            # Get the note to move
            note = db.get(DBNote, note_id)
            if not note:
                print(f"Note {note_id} not found")
                raise ValueError(f"Note {note_id} not found")

            # Validate position parameters
            if sibling_id and position is None:
                raise ValueError("Position must be specified when sibling_id is provided")
            if position and not sibling_id:
                raise ValueError("Position cannot be specified without a sibling_id")

            # Prevent moving a note to itself as a sibling
            if sibling_id == note_id:
                raise ValueError("Cannot move note relative to itself")

            # Prevent moving a note to its current position
            if new_parent_id == note.parent_id and sibling_id is None:
                raise ValueError("Note is already at this position")

            old_prev_id = note.prev_id
            old_next_id = note.next_id

            def is_descendant(parent_id: str, potential_child_id: str) -> bool:
                """Check if potential_child_id is a descendant of parent_id"""
                current = db.get(DBNote, potential_child_id)
                while current and current.parent_id:
                    if current.parent_id == parent_id:
                        return True
                    current = db.get(DBNote, current.parent_id)
                return False

            if new_parent_id and is_descendant(note_id, new_parent_id):
                raise ValueError("Cannot create circular parent-child relationship")

            if new_parent_id == note_id:
                raise ValueError("Cannot make a note its own parent")

            # Get all notes at the target level
            target_notes = db.query(DBNote).filter(DBNote.parent_id == new_parent_id).all()

            # Step 1: Unlink note from current position
            if old_prev_id:
                prev_note = db.get(DBNote, old_prev_id)
                if prev_note:
                    prev_note.next_id = old_next_id
            if old_next_id:
                next_note = db.get(DBNote, old_next_id)
                if next_note:
                    next_note.prev_id = old_prev_id

            # Step 2: Clear note's links
            note.prev_id = None
            note.next_id = None
            note.parent_id = new_parent_id

            if note_store.loaded:
                if old_prev_id:
                    prev_note = db.get(DBNote, old_prev_id)
                    if prev_note:
                        note_store.update_metadata_from_db(prev_note)
                if old_next_id:
                    next_note = db.get(DBNote, old_next_id)
                    if next_note:
                        note_store.update_metadata_from_db(next_note)

            if sibling_id is None:
                # Case 1: Find existing head at this level
                existing_head = next((n for n in target_notes if n.prev_id is None), None)
                if existing_head:
                    # Make existing head point to our note
                    existing_head.prev_id = note_id
                    note.next_id = existing_head.id
                if note_store.loaded:
                    note_store.update_metadata_from_db(note)
                    for candidate in target_notes:
                        note_store.update_metadata_from_db(candidate)
                return

            # Case 2: Positioning relative to a sibling
            sibling = db.get(DBNote, sibling_id)
            if not sibling:
                raise ValueError(f"Sibling note {sibling_id} not found")

            if sibling.parent_id != new_parent_id:
                raise ValueError("Sibling must have the same parent")

            if position == MovePosition.BEFORE:
                note.next_id = sibling_id
                note.prev_id = sibling.prev_id
                sibling.prev_id = note_id
                if note.prev_id:
                    prev_note = db.get(DBNote, note.prev_id)
                    if prev_note:
                        prev_note.next_id = note_id
            else:  # Position.AFTER
                note.prev_id = sibling_id
                note.next_id = sibling.next_id
                sibling.next_id = note_id
                if note.next_id:
                    next_note = db.get(DBNote, note.next_id)
                    if next_note:
                        next_note.prev_id = note_id
            if note_store.loaded:
                note_store.update_metadata_from_db(note)
                note_store.update_metadata_from_db(sibling)
                if note.prev_id and note.prev_id != sibling_id:
                    prev_note = db.get(DBNote, note.prev_id)
                    if prev_note:
                        note_store.update_metadata_from_db(prev_note)
                if note.next_id:
                    next_note = db.get(DBNote, note.next_id)
                    if next_note:
                        note_store.update_metadata_from_db(next_note)
                for candidate in target_notes:
                    note_store.update_metadata_from_db(candidate)
        except Exception as e:
            print(e)
            raise
