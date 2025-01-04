from dataclasses import dataclass
from typing import List, Optional, Dict
from .position import Position  # For fractional indexing

@dataclass
class OldSchemaNote:
    id: str
    content: str
    prev_id: Optional[str] = None
    next_id: Optional[str] = None
    parent_id: Optional[str] = None

@dataclass
class NewSchemaNote:
    id: str
    content: str
    position: str
    indent: int

def old_to_new_schema(notes: List[OldSchemaNote]) -> List[NewSchemaNote]:
    """Convert from linked list schema to positional schema"""
    if not notes:
        return []
    
    # First, organize notes by parent_id
    notes_by_parent: Dict[Optional[str], List[OldSchemaNote]] = {}
    for note in notes:
        parent_id = note.parent_id
        if parent_id not in notes_by_parent:
            notes_by_parent[parent_id] = []
        notes_by_parent[parent_id].append(note)
    
    result = []
    
    def get_ordered_notes_at_level(notes_at_level: List[OldSchemaNote]) -> List[OldSchemaNote]:
        """Get notes in correct order based on prev_id/next_id relationships"""
        ordered = []
        # Find the first note (no prev_id)
        current = next((n for n in notes_at_level if n.prev_id is None), None)
        while current:
            ordered.append(current)
            current = next((n for n in notes_at_level if n.prev_id == current.id), None)
        return ordered
    
    # Process root level first (parent_id = None)
    root_notes = get_ordered_notes_at_level(notes_by_parent.get(None, []))
    position = Position.get_first_position()
    for note in root_notes:
        result.append(NewSchemaNote(
            id=note.id,
            content=note.content,
            position=position,
            indent=0
        ))
        position = Position.get_position_between(position, None)
    
    # Process each root note's children
    for root_note in root_notes:
        if root_note.id in notes_by_parent:
            child_notes = get_ordered_notes_at_level(notes_by_parent[root_note.id])
            for child in child_notes:
                result.append(NewSchemaNote(
                    id=child.id,
                    content=child.content,
                    position=position,
                    indent=1
                ))
                position = Position.get_position_between(position, None)
    
    return result

def new_to_old_schema(notes: List[NewSchemaNote]) -> List[OldSchemaNote]:
    """Convert from positional schema to linked list schema"""
    if not notes:
        return []
    
    # Sort notes by indent and position
    sorted_notes = sorted(notes, key=lambda n: (n.indent, n.position))
    print("\nSorted notes:")
    for note in sorted_notes:
        print(f"id: {note.id}, indent: {note.indent}, pos: {note.position}")
    
    # Group notes by indent level
    notes_by_indent: Dict[int, List[NewSchemaNote]] = {}
    for note in sorted_notes:
        if note.indent not in notes_by_indent:
            notes_by_indent[note.indent] = []
        notes_by_indent[note.indent].append(note)
    
    result = []
    
    # Process each indent level
    for indent in sorted(notes_by_indent.keys()):
        notes_at_level = notes_by_indent[indent]
        print(f"\nProcessing indent level {indent}:")
        
        for i, note in enumerate(notes_at_level):
            prev_id = notes_at_level[i-1].id if i > 0 else None
            next_id = notes_at_level[i+1].id if i < len(notes_at_level)-1 else None
            
            # Find parent by looking at the closest note at the previous indent level
            # that comes before this note's position
            parent_id = None
            if indent > 0:  # Only look for parents if we're not at root level
                prev_level_notes = notes_by_indent.get(indent - 1, [])
                print(f"Looking for parent of note {note.id}:")
                print(f"Previous level notes: {[(n.id, n.position) for n in prev_level_notes]}")
                
                # Find the rightmost note at the previous level that comes before this note
                for potential_parent in prev_level_notes:
                    if potential_parent.position < note.position:
                        parent_id = potential_parent.id
                
                print(f"Found parent: {parent_id}")
            
            result.append(OldSchemaNote(
                id=note.id,
                content=note.content,
                prev_id=prev_id,
                next_id=next_id,
                parent_id=parent_id
            ))
            print(f"Created note: id={note.id}, prev={prev_id}, next={next_id}, parent={parent_id}")
    
    return result 