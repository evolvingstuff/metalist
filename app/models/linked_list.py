from typing import List, Optional, Any
from sqlalchemy.orm import Session
from .enums import MovePosition
from .database import DBNote
from ..global_state_mod import global_state


class LinkedListManager:

    # TODO is this recursive beyond one level of sub note?
    @staticmethod
    def validate_list(db: Session, parent_id: Optional[str] = None) -> bool:
        """Validate the linked list structure"""
        db.expire_all()  # TODO useful?
        notes = db.query(DBNote).filter(DBNote.parent_id == parent_id).all()
        
        if not notes:
            return True

        for note in notes:
            db.refresh(note)

        # Single note case
        if len(notes) == 1:
            note = notes[0]
            # Must be both head and tail, with correct parent
            return (note.prev_id is None and 
                   note.next_id is None and 
                   note.parent_id == parent_id)

        # Multiple notes - should have exactly one head and one tail
        heads = [note for note in notes if note.prev_id is None]
        tails = [note for note in notes if note.next_id is None]

        if len(heads) != 1 or len(tails) != 1:
            return False

        # Traverse from head and verify links
        head = heads[0]
        seen = {head.id}
        current = head

        # Verify head's parent
        if head.parent_id != parent_id:
            return False

        while current.next_id:
            next_note = next((note for note in notes if note.id == current.next_id), None)
            # Explicit checks for each condition
            if not next_note:
                return False  # Next note doesn't exist
            if next_note.id in seen:
                return False  # Circular reference
            if next_note.prev_id != current.id:
                return False  # Broken bidirectional link
            if next_note.parent_id != parent_id:
                return False  # Wrong parent
            seen.add(next_note.id)
            current = next_note

        # Verify we found all notes and the tail is correct
        return (len(seen) == len(notes) and 
                current.next_id is None and  # Explicit tail check
                current.parent_id == parent_id)  # Tail has correct parent

    @staticmethod
    def get_ordered_child_list(db: Session, parent_id: Optional[str] = None) -> List[Any]:
        """Get an ordered list of child notes for the given parent_id"""
        query = db.query(DBNote)
        if parent_id is None:
            # When getting root notes, we need ALL notes that have no parent
            query = query.filter(DBNote.parent_id.is_(None))
        else:
            query = query.filter(DBNote.parent_id == parent_id)
        
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
    def _would_create_cycle(db, note_id: str, new_parent_id: str) -> bool:
        """Check if moving note to new_parent would create a parent-child cycle"""
        if not new_parent_id:
            return False

        current = new_parent_id
        seen = set()
        while current and current not in seen:
            if current == note_id:
                return True
            seen.add(current)
            parent = db.get(DBNote, current)
            if not parent:
                break
            current = parent.parent_id
        return False


    @staticmethod
    def undo(db: Session) -> None:
        command_stack = global_state["command_stack"]
        # TODO refactor this
        if command_stack.current_index >= 0:
            command_stack.undo(db)
            return True
        return False

    @staticmethod
    def redo(db: Session) -> None:
        command_stack = global_state["command_stack"]
        # TODO refactor this
        if command_stack.current_index < len(command_stack.stack) - 1:
            command_stack.redo(db)
            return True
        return False

    @staticmethod
    def create_note_top(db: Session, note_id: str, parent_id: Optional[str] = None) -> None:
        """Create a new note and insert it as the new head of the linked list"""
        try:
            if note_id is None:
                raise ValueError("Note ID must be specified")
            # Create new note with no links initially
            db_note = DBNote(id=note_id, content="", parent_id=parent_id)
            db.add(db_note)

            # Find the current head
            current_head = db.query(DBNote).filter(
                DBNote.prev_id == None, 
                DBNote.parent_id == parent_id
            ).first()

            if current_head and current_head.id != note_id:  # Make sure we're not looking at ourselves
                # Make new note the head by linking it to current head
                current_head.prev_id = note_id
                db_note.next_id = current_head.id

            db.flush()  # an attempt to make the note available for the next query
        except Exception as e:
            print(e)
            raise

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

            if sibling_id is None:
                # Case 1: Find existing head at this level
                existing_head = next((n for n in target_notes if n.prev_id is None), None)
                if existing_head:
                    # Make existing head point to our note
                    existing_head.prev_id = note_id
                    note.next_id = existing_head.id
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
        except Exception as e:
            print(e)
            raise

    @staticmethod
    def get_note(db: Session, note_id: str) -> DBNote:
        db_note = db.query(DBNote).filter(DBNote.id == note_id).first()
        if not db_note:
            raise ValueError(f"Note with id {note_id} not found")
        return db_note

    @staticmethod
    def update_note(db: Session, note_id: str, content: str):
        db_note = LinkedListManager.get_note(db, note_id)
        db_note.content = content

    @staticmethod
    def delete_note(db: Session, note_id: str) -> None:
        """Delete a note and ALL its descendants, updating surrounding links"""
        try:
            note = db.get(DBNote, note_id)
            if not note:
                raise ValueError(f"Note {note_id} not found")

            def get_all_descendant_ids(parent_id: str) -> set[str]:
                """Recursively get IDs of all descendants"""
                descendants = set()
                children = db.query(DBNote).filter(DBNote.parent_id == parent_id).all()
                for child in children:
                    descendants.add(child.id)
                    descendants.update(get_all_descendant_ids(child.id))
                return descendants

            # Delete all descendants first
            descendant_ids = get_all_descendant_ids(note_id)
            for descendant_id in descendant_ids:
                descendant = db.get(DBNote, descendant_id)
                db.delete(descendant)

            # Update links of surrounding notes at the original note's level
            if note.prev_id:
                prev_note = db.get(DBNote, note.prev_id)
                prev_note.next_id = note.next_id
            if note.next_id:
                next_note = db.get(DBNote, note.next_id)
                next_note.prev_id = note.prev_id

            # Delete the original note
            db.delete(note)
        except Exception as e:
            print(e)
            raise


    @staticmethod
    def create_note_drop(db: Session, note_id: str, new_parent_id: str = None, sibling_id: str = None, position: MovePosition = None):
        # First create the note at root level
        LinkedListManager.create_note_top(db, note_id)

        # TODO: possible to fail at next step but original update still made...
        
        # Then move it to the desired location (either under a parent or relative to siblings)
        LinkedListManager.move_note(
            db=db,
            note_id=note_id,
            new_parent_id=new_parent_id,
            sibling_id=sibling_id,
            position=position
        )