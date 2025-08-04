from typing import List, Optional
from sqlalchemy.orm import Session
from .database import DBNote


class ListTraversal:
    """Handles traversal and validation of linked list structures"""
    
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
    def get_ordered_child_list(db: Session, parent_id: Optional[str] = None) -> List[DBNote]:
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
    def would_create_cycle(db: Session, note_id: str, new_parent_id: str) -> bool:
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