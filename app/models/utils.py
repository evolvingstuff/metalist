from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import uuid
from datetime import datetime, timezone
from .database import DBNote


def copy_note(db: Session, note_id: str, new_parent_id: Optional[str] = None) -> str:
    """
    Creates a deep copy of a note and all its descendants.
    
    Args:
        db: Database session
        note_id: ID of the note to copy
        new_parent_id: Optional parent ID for the copied note
        
    Returns:
        ID of the new copied root note
    """
    # Get the original note
    source_note = db.get(DBNote, note_id)
    if not source_note:
        raise ValueError(f"Source note with ID {note_id} not found")
    
    # Create a mapping of original IDs to new IDs
    id_mapping = {}
    
    # Recursively copy the note and all its descendants
    new_root_id = _copy_note_recursive(db, source_note, id_mapping, new_parent_id)
    
    return new_root_id


def _copy_note_recursive(
    db: Session, 
    source_note: DBNote, 
    id_mapping: Dict[str, str], 
    new_parent_id: Optional[str] = None
) -> str:
    """
    Recursively copies a note and all its descendants.
    
    Args:
        db: Database session
        source_note: The source note to copy
        id_mapping: Mapping from original note IDs to new note IDs
        new_parent_id: Optional parent ID for the new note
        
    Returns:
        ID of the new note
    """
    # Generate a new ID for the note
    new_id = str(uuid.uuid4())
    
    # Add to mapping
    id_mapping[source_note.id] = new_id
    
    # Create a new note with the same content
    new_note = DBNote(
        id=new_id,
        content=source_note.content,
        parent_id=new_parent_id,
        prev_id=None,  # Will be set later if needed
        next_id=None,  # Will be set later if needed
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    
    # Add to database
    db.add(new_note)
    db.flush()  # Ensure the note is persisted
    
    # Get all children of the source note
    children = db.query(DBNote).filter(DBNote.parent_id == source_note.id).all()
    
    # Copy children if any
    if children:
        # First get the ordered child list to preserve order
        from .linked_list import LinkedListManager
        ordered_children = LinkedListManager.get_ordered_child_list(db, source_note.id)
        
        # Copy each child recursively
        previous_copied_id = None
        for child in ordered_children:
            # Copy the child with the new parent ID
            new_child_id = _copy_note_recursive(db, child, id_mapping, new_id)
            
            # Update prev_id and next_id to maintain sibling order
            if previous_copied_id:
                new_child = db.get(DBNote, new_child_id)
                previous_child = db.get(DBNote, previous_copied_id)
                
                new_child.prev_id = previous_copied_id
                previous_child.next_id = new_child_id
            
            previous_copied_id = new_child_id
    
    return new_id