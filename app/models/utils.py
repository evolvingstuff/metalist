from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
import uuid
from datetime import datetime, timezone
from .database import DBNote
from ..utils.encryption import encrypt
from ..services.content_cache import get_cached_content


def copy_note_in_memory(db: Session, note_id: str) -> Dict[str, Any]:
    """
    Serializes a note and all its descendants to a pure data structure.
    
    Args:
        db: Database session
        note_id: ID of the note to serialize
        
    Returns:
        Dictionary representation of the note tree (no database writes)
    """
    # Get the original note
    source_note = db.get(DBNote, note_id)
    if not source_note:
        raise ValueError(f"Source note with ID {note_id} not found")
    
    return _serialize_note_recursive(db, source_note)


def _serialize_note_recursive(db: Session, source_note: DBNote) -> Dict[str, Any]:
    """
    Recursively serializes a note and all its descendants to pure data.
    
    Args:
        db: Database session
        source_note: The source note to serialize
        
    Returns:
        Dictionary representation of the note and its children
    """
    # Get decrypted content from cache - MUST be there
    decrypted_content = get_cached_content(source_note.id)
    if decrypted_content is None:
        raise RuntimeError(f"CACHE CORRUPTION: Note {source_note.id} not found in cache during copy operation!")
    
    # Serialize this note's data
    note_data = {
        "content": decrypted_content,  # Use decrypted content from cache
        "created_at": source_note.created_at.isoformat() if source_note.created_at else None,
        "updated_at": source_note.updated_at.isoformat() if source_note.updated_at else None,
        "children": []
    }
    
    # Get all children of the source note in order
    from .linked_list import LinkedListManager
    ordered_children = LinkedListManager.get_ordered_child_list(db, source_note.id)
    
    # Serialize each child recursively
    for child in ordered_children:
        child_data = _serialize_note_recursive(db, child)
        note_data["children"].append(child_data)
    
    return note_data


def paste_note_from_memory(db: Session, note_data: Dict[str, Any], new_parent_id: Optional[str] = None) -> str:
    """
    Deserializes clipboard data into real database notes with new UUIDs.
    
    Args:
        db: Database session
        note_data: Serialized note data from clipboard
        new_parent_id: Optional parent ID for the pasted note
        
    Returns:
        ID of the new pasted root note
    """
    return _deserialize_note_recursive(db, note_data, new_parent_id)


def _deserialize_note_recursive(db: Session, note_data: Dict[str, Any], new_parent_id: Optional[str] = None) -> str:
    """
    Recursively deserializes note data into real database notes.
    
    Args:
        db: Database session
        note_data: Serialized note data
        new_parent_id: Optional parent ID for the new note
        
    Returns:
        ID of the new note
    """
    # Generate a new ID for the note
    new_id = str(uuid.uuid4())
    
    # Create the new note directly
    new_note = DBNote(
        id=new_id,
        content=encrypt(note_data["content"]),  # Encrypt content before saving
        parent_id=new_parent_id,
        prev_id=None,  # Will be set later if needed
        next_id=None,  # Will be set later if needed
    )
    db.add(new_note)
    db.flush()
    
    # Deserialize children if any
    children_data = note_data.get("children", [])
    if children_data:
        # Deserialize each child recursively
        previous_child_id = None
        for child_data in children_data:
            # Deserialize the child with the new parent ID
            new_child_id = _deserialize_note_recursive(db, child_data, new_id)
            
            # Update prev_id and next_id to maintain sibling order
            if previous_child_id:
                new_child = db.get(DBNote, new_child_id)
                previous_child = db.get(DBNote, previous_child_id)
                
                new_child.prev_id = previous_child_id
                previous_child.next_id = new_child_id
            
            previous_child_id = new_child_id
    
    return new_id


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
        content=source_note.content,  # Content is already encrypted in source_note
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