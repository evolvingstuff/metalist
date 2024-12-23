from typing import List, Optional
from sqlalchemy.orm import Session

class LinkedListManager:
    @staticmethod
    def validate_list(db: Session, model_class, parent_id: Optional[str] = None) -> bool:
        """Validate the linked list structure"""
        items = []
        current = db.query(model_class).filter(
            model_class.prev_id == None,
            model_class.parent_id == parent_id
        ).first()
        
        while current:
            items.append(current.id)
            
            # Check for circular references
            if current.next_id in items:
                print(f"Circular reference detected: {current.next_id} already seen")
                return False
                
            # Validate bidirectional links
            if current.next_id:
                next_note = db.query(model_class).get(current.next_id)
                if next_note and next_note.prev_id != current.id:
                    print(f"Broken bidirectional link: {current.id} -> {current.next_id}")
                    return False
            
            current = db.query(model_class).filter(model_class.id == current.next_id).first()
        
        return True

    @staticmethod
    def get_ordered_list(db: Session, model_class, parent_id: Optional[str] = None) -> List:
        """Get all notes in linked list order for a specific parent"""
        items = []
        current = db.query(model_class).filter(
            model_class.prev_id == None,
            model_class.parent_id == parent_id
        ).first()
        
        while current:
            items.append(current)
            current = db.query(model_class).filter(
                model_class.id == current.next_id,
                model_class.parent_id == parent_id
            ).first()
            
        return items

    @staticmethod
    def insert_after(db: Session, model_class, note_id: str, target_id: str):
        """Insert note after target in the linked list"""
        note = db.query(model_class).get(note_id)
        target = db.query(model_class).get(target_id)
        
        if not note or not target or note_id == target_id:
            return
            
        # First, remove note from its current position
        if note.prev_id:
            prev = db.query(model_class).get(note.prev_id)
            if prev:
                prev.next_id = note.next_id
        if note.next_id:
            next = db.query(model_class).get(note.next_id)
            if next:
                next.prev_id = note.prev_id
                
        # Then insert after target
        note.next_id = target.next_id
        note.prev_id = target_id
        
        if target.next_id:
            next = db.query(model_class).get(target.next_id)
            if next:
                next.prev_id = note_id
        
        target.next_id = note_id
        db.commit()

    @staticmethod
    def insert_before(db: Session, model_class, note_id: str, target_id: str):
        """Insert note before target in the linked list"""
        note = db.query(model_class).get(note_id)
        target = db.query(model_class).get(target_id)
        
        if not note or not target or note_id == target_id:
            return
            
        # First, remove note from its current position
        if note.prev_id:
            prev = db.query(model_class).get(note.prev_id)
            if prev:
                prev.next_id = note.next_id
        if note.next_id:
            next = db.query(model_class).get(note.next_id)
            if next:
                next.prev_id = note.prev_id
                
        # Then insert before target
        note.prev_id = target.prev_id
        note.next_id = target_id
        
        if target.prev_id:
            prev = db.query(model_class).get(target.prev_id)
            if prev:
                prev.next_id = note_id
        
        target.prev_id = note_id
        db.commit()

    @staticmethod
    def validate_and_fix_list(db: Session, model_class, parent_id: Optional[str] = None) -> List:
        """Validate and fix the linked list if needed"""
        # Count notes with no prev_id (should be exactly one)
        head_count = db.query(model_class).filter(
            model_class.prev_id == None,
            model_class.parent_id == parent_id
        ).count()
        
        # Count notes with no next_id (should be exactly one)
        tail_count = db.query(model_class).filter(
            model_class.next_id == None,
            model_class.parent_id == parent_id
        ).count()
        
        if head_count != 1 or tail_count != 1:
            print(f"Invalid list structure: {head_count} heads, {tail_count} tails")
            # Fix the list by ordering by creation date
            notes = db.query(model_class).filter(
                model_class.parent_id == parent_id
            ).order_by(model_class.created_at).all()
            
            # Reset all links
            for note in notes:
                note.prev_id = None
                note.next_id = None
            
            # Rebuild chain
            for i in range(len(notes)-1):
                notes[i].next_id = notes[i+1].id
                notes[i+1].prev_id = notes[i].id
            
            db.commit()
            print("List structure fixed")
            
        return LinkedListManager.get_ordered_list(db, model_class, parent_id)

    @staticmethod
    def detect_corruption(db: Session, model_class, parent_id: Optional[str] = None) -> bool:
        """Detect any corruption in the linked list structure"""
        # Get all notes at this level
        notes = db.query(model_class).filter(model_class.parent_id == parent_id).all()
        note_dict = {note.id: note for note in notes}
        
        # Check for basic corruption
        head_count = sum(1 for note in notes if note.prev_id is None)
        tail_count = sum(1 for note in notes if note.next_id is None)
        
        if head_count != 1:
            print(f"ERROR: Found {head_count} notes with no prev_id (should be exactly 1)")
            return True
            
        if tail_count != 1:
            print(f"ERROR: Found {tail_count} notes with no next_id (should be exactly 1)")
            return True
            
        # Check for circular references and bidirectional integrity
        seen_ids = set()
        current = next((note for note in notes if note.prev_id is None), None)
        
        while current:
            if current.id in seen_ids:
                print(f"ERROR: Circular reference detected at note {current.id}")
                return True
            seen_ids.add(current.id)
            
            # Check bidirectional links
            if current.next_id:
                next_note = note_dict.get(current.next_id)
                if not next_note:
                    print(f"ERROR: Note {current.id} points to non-existent next_id {current.next_id}")
                    return True
                if next_note.prev_id != current.id:
                    print(f"ERROR: Broken bidirectional link between {current.id} and {current.next_id}")
                    return True
            
            current = note_dict.get(current.next_id) if current.next_id else None
            
        # Check if we visited all notes
        if len(seen_ids) != len(notes):
            print(f"ERROR: Only visited {len(seen_ids)} notes out of {len(notes)} total")
            return True
            
        return False

    @staticmethod
    def move_note(db: Session, model_class, note_id: str, target_id: str, insert_before: bool, new_parent_id: Optional[str] = None):
        """Move a note relative to a target, optionally changing its parent"""
        note = db.query(model_class).get(note_id)
        target = db.query(model_class).get(target_id)
        
        if not note or not target or note_id == target_id:
            return
            
        print(f"\nBefore move:")
        print(f"Note {note_id}: prev={note.prev_id}, next={note.next_id}, parent={note.parent_id}")
        print(f"Target {target_id}: prev={target.prev_id}, next={target.next_id}, parent={target.parent_id}")
            
        # Store original next/prev before unlinking
        original_prev_id = note.prev_id
        original_next_id = note.next_id
        old_parent_id = note.parent_id
            
        print(f"\nUnlinking from original position:")
        print(f"Original prev_id={original_prev_id}, next_id={original_next_id}")
            
        # First, remove note from its current position
        if original_prev_id:
            prev = db.query(model_class).get(original_prev_id)
            if prev:
                prev.next_id = original_next_id
                print(f"Updated prev note {prev.id}: next_id -> {prev.next_id}")
        if original_next_id:
            next = db.query(model_class).get(original_next_id)
            if next:
                next.prev_id = original_prev_id
                print(f"Updated next note {next.id}: prev_id -> {next.prev_id}")
                
        # Update parent if needed
        if new_parent_id != old_parent_id:
            print(f"\nChanging parent: {old_parent_id} -> {new_parent_id}")
            note.parent_id = new_parent_id
            
            # When moving to a new parent, reset links
            note.prev_id = None
            note.next_id = None
            
            # If the target is the new parent, we're done
            if target_id == new_parent_id:
                db.commit()
                return
                
        # Handle reordering
        print(f"\nReordering within new parent {new_parent_id}:")
        if insert_before:
            original_target_prev_id = target.prev_id
            note.prev_id = original_target_prev_id
            note.next_id = target_id
            target.prev_id = note_id
            if original_target_prev_id:
                prev = db.query(model_class).get(original_target_prev_id)
                if prev:
                    prev.next_id = note_id
                    print(f"Updated prev note {prev.id}: next_id -> {note_id}")
            print(f"Updated target {target_id}: prev_id -> {note_id}")
        else:
            original_target_next_id = target.next_id
            note.next_id = original_target_next_id
            note.prev_id = target_id
            target.next_id = note_id
            if original_target_next_id:
                next = db.query(model_class).get(original_target_next_id)
                if next:
                    next.prev_id = note_id
                    print(f"Updated next note {next.id}: prev_id -> {note_id}")
            print(f"Updated target {target_id}: next_id -> {note_id}")
        
        print(f"\nAfter move:")
        print(f"Note {note_id}: prev={note.prev_id}, next={note.next_id}, parent={note.parent_id}")
        print(f"Target {target_id}: prev={target.prev_id}, next={target.next_id}, parent={target.parent_id}")
        
        db.commit()