"""
Note Renderer Module

Provides consistent rendering functions for notes in different modes.
Acts as the single source of truth for note rendering across the application.
"""

import re
from app.core import config
from app.utils.text_utils import strip_html


def strip_comments_from_html(html_content: str) -> str:
    """
    Remove comment patterns like /* text */ from HTML content while preserving HTML structure.
    Also removes empty divs that might be left behind.
    """
    if not html_content:
        return html_content
    
    # Remove /* comment */ patterns (including any whitespace around them)
    content = re.sub(r'/\*[^*]*\*/', '', html_content)
    
    # Remove empty divs that might be left behind
    content = re.sub(r'<div>\s*</div>', '', content)
    
    # Clean up extra whitespace
    content = re.sub(r'\s+', ' ', content).strip()
    
    return content


def render_read_only_mode(note) -> str:
    if config.DEBUG_NOTE_RENDER_MODE:
        return note.content + " [READ ONLY]" # as a test
    else:
        # Strip comments from read-only view
        return strip_comments_from_html(note.content)


def render_editing_mode(note) -> str:
    return note.content


def note_matches_search(note_dict, search_terms):
    """
    Check if a note or any of its descendants contains all search terms.
    
    Args:
        note_dict: Dictionary representation of a note with content and children
        search_terms: List of search terms (all must be present)
        
    Returns:
        True if note or any descendant contains all search terms
    """
    # Check the note's own content using RAW content (for search) not rendered content
    raw_content = note_dict.get('raw_content', note_dict['content'])
    plain_text = strip_html(raw_content).lower()
    if all(term in plain_text for term in search_terms):
        return True
    
    # Recursively check ALL descendants - if any descendant matches, we include this note
    for child in note_dict.get('children', []):
        if note_matches_search(child, search_terms):
            return True
    
    return False


def filter_notes_by_search(notes, search_query):
    """
    Filter notes based on search query using AND logic.
    A note is included if it OR any of its descendants contains ALL search terms.
    
    Args:
        notes: List of note dictionaries
        search_query: Search string from user
        
    Returns:
        Filtered list of notes that match the search
    """
    if not search_query or not search_query.strip():
        return notes
    
    # Split search query into terms and convert to lowercase
    search_terms = [term.lower() for term in search_query.strip().split() if term]
    
    if not search_terms:
        return notes
    
    # Filter notes - include a note if it or ANY descendant contains ALL search terms
    filtered_notes = []
    for note in notes:
        if note_matches_search(note, search_terms):
            filtered_notes.append(note)
    
    return filtered_notes


def build_note_tree(db_manager, db, parent_id=None, editing_note_id=None, search_query=None):
    """
    Build a hierarchical tree of notes with proper rendering applied.
    
    Args:
        db_manager: The database manager (LinkedListManager) with methods to get notes
        db: Database session
        parent_id: Optional ID of parent note to build tree from
        editing_note_id: Optional ID of note currently being edited
        search_query: Optional search string to filter notes
        
    Returns:
        List of note dictionaries with properly rendered content and nested children
    """
    try:
        notes = db_manager.get_ordered_child_list(db, parent_id)
        
        # Build the complete tree first, including all descendants
        note_tree = [{
            'id': note.id,
            'content': render_editing_mode(note) if note.id == editing_note_id else render_read_only_mode(note),
            'raw_content': note.content,  # Keep raw content for search filtering
            'parent_id': note.parent_id or '',
            'children': build_note_tree(db_manager, db, note.id, editing_note_id, search_query),
            'flags': {
                'isEditing': note.id == editing_note_id,
                'isCollapsed': False
            }
        } for note in notes]
        
        # Apply search filtering only when building the top-level tree (parent_id is None)
        # This ensures we filter complete note trees based on whether ANY note in the tree
        # (parent or any descendant) contains ALL the search terms
        if parent_id is None and search_query:
            note_tree = filter_notes_by_search(note_tree, search_query)
        
        return note_tree
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error building note tree")
        raise