"""
Note Renderer Module

Provides consistent rendering functions for notes in different modes.
Acts as the single source of truth for note rendering across the application.
"""

from app.core import config

def render_read_only_mode(note) -> str:
    if config.DEBUG_NOTE_RENDER_MODE:
        return note.content + " [READ ONLY]" # as a test
    else:
        return note.content


def render_editing_mode(note) -> str:
    return note.content


def build_note_tree(db_manager, db, parent_id=None, editing_note_id=None):
    """
    Build a hierarchical tree of notes with proper rendering applied.
    
    Args:
        db_manager: The database manager (LinkedListManager) with methods to get notes
        db: Database session
        parent_id: Optional ID of parent note to build tree from
        editing_note_id: Optional ID of note currently being edited
        
    Returns:
        List of note dictionaries with properly rendered content and nested children
    """
    try:
        notes = db_manager.get_ordered_child_list(db, parent_id)
        return [{
            'id': note.id,
            'content': render_editing_mode(note) if note.id == editing_note_id else render_read_only_mode(note),
            'parent_id': note.parent_id or '',
            'children': build_note_tree(db_manager, db, note.id, editing_note_id),
            'flags': {
                'isEditing': note.id == editing_note_id,
                'isCollapsed': False
            }
        } for note in notes]
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error building note tree")
        raise