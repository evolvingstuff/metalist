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
    return strip_comments_from_html(note.content)


def render_editing_mode(note) -> str:
    return note.content


def render_redacted_mode(note) -> str:
    """
    Render a note in redacted/dimmed mode for irrelevant search results.
    This is where you can customize how de-emphasized notes appear.
    """
    content = strip_comments_from_html(note.content)
    # Wrap content in a span with reduced opacity
    return f'<span style="opacity: 0.4; filter: grayscale(50%);">{content}</span>'


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


def note_directly_matches(note_dict, search_terms):
    """
    Check if a note directly contains all search terms (not checking descendants).
    """
    raw_content = note_dict.get('raw_content', note_dict['content'])
    plain_text = strip_html(raw_content).lower()
    return all(term in plain_text for term in search_terms)


def mark_search_relevance(notes, search_terms):
    """
    Mark each note with its search relevance level.
    
    Relevance levels:
    - 'direct_match': Note directly contains all search terms
    - 'relevant': Note is ancestor of a match (has matching descendants) OR descendant of a match
    - 'irrelevant': Note has no connection to search terms
    """
    def process_note(note_dict, parent_is_match=False):
        # First check if this note is a direct match
        is_direct_match = note_directly_matches(note_dict, search_terms)
        
        # Process all children to determine if we have matching descendants
        has_matching_descendant = False
        for child in note_dict.get('children', []):
            # Pass down whether current note or any ancestor was a match
            child_relevance = process_note(child, parent_is_match or is_direct_match)
            if child_relevance in ['direct_match', 'relevant']:
                has_matching_descendant = True
        
        # Determine this note's relevance
        if is_direct_match:
            relevance = 'direct_match'
        elif has_matching_descendant or parent_is_match:
            # Relevant if: has matching descendants OR any ancestor was a match
            relevance = 'relevant'
        else:
            relevance = 'irrelevant'
        
        note_dict['search_relevance'] = relevance
        return relevance
    
    # Process each top-level note
    for note in notes:
        process_note(note, parent_is_match=False)
    
    return notes


def apply_redacted_rendering(notes):
    """
    Apply redacted rendering to notes marked as irrelevant.
    This modifies the content of notes in-place based on their search_relevance.
    """
    def process_note(note_dict):
        # Recursively process children first
        for child in note_dict.get('children', []):
            process_note(child)
        
        # Apply redacted rendering to irrelevant notes (unless being edited)
        if (note_dict.get('search_relevance') == 'irrelevant' and 
            not note_dict.get('flags', {}).get('isEditing', False)):
            # Re-render using redacted mode
            # We need to create a simple note object for the render function
            class SimpleNote:
                def __init__(self, content):
                    self.content = content
            
            raw_content = note_dict.get('raw_content', note_dict['content'])
            note_obj = SimpleNote(raw_content)
            note_dict['content'] = render_redacted_mode(note_obj)
    
    for note in notes:
        process_note(note)


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
    
    # Mark search relevance for all notes in filtered results
    mark_search_relevance(filtered_notes, search_terms)
    
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
        note_tree = []
        for note in notes:
            # Build child tree first
            children = build_note_tree(db_manager, db, note.id, editing_note_id, search_query)
            
            # Determine render mode - editing takes precedence
            if note.id == editing_note_id:
                rendered_content = render_editing_mode(note)
            else:
                rendered_content = render_read_only_mode(note)
            
            note_dict = {
                'id': note.id,
                'content': rendered_content,
                'raw_content': note.content,  # Keep raw content for search filtering
                'parent_id': note.parent_id or '',
                'children': children,
                'flags': {
                    'isEditing': note.id == editing_note_id,
                    'isCollapsed': False
                }
            }
            note_tree.append(note_dict)
        
        # Apply search filtering only when building the top-level tree (parent_id is None)
        # This ensures we filter complete note trees based on whether ANY note in the tree
        # (parent or any descendant) contains ALL the search terms
        if parent_id is None and search_query:
            note_tree = filter_notes_by_search(note_tree, search_query)
            # After filtering, apply redacted rendering to irrelevant notes
            apply_redacted_rendering(note_tree)
        
        return note_tree
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error building note tree")
        raise