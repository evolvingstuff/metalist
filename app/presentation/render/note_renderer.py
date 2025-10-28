"""
Note Renderer Module

Provides consistent rendering functions for notes in different modes.
Acts as the single source of truth for note rendering across the application.
"""

import re
from app.utils.text_utils import strip_html
from app.services.content_cache import get_cached_content
from app.services.note_store import store as note_store


def highlight_search_terms(html_content: str, search_query: str) -> str:
    """
    Highlight search terms in HTML content while preserving HTML structure.
    
    Args:
        html_content: HTML content to highlight terms in
        search_query: Search query string containing terms to highlight
        
    Returns:
        HTML content with search terms wrapped in highlight spans
    """
    if not html_content or not search_query or not search_query.strip():
        return html_content
    
    # Split search query into terms
    search_terms = [term.lower() for term in search_query.strip().split() if term]
    if not search_terms:
        return html_content
    
    # Create a regex pattern that matches any of the search terms
    # No word boundaries - match subsequences
    # Escape special regex characters in search terms
    escaped_terms = [re.escape(term) for term in search_terms]
    pattern = r'(' + '|'.join(escaped_terms) + r')'
    
    # Function to replace text content while preserving HTML
    def replace_in_text_nodes(match):
        text = match.group(0)
        # Check if we're inside an HTML tag
        if '<' in text or '>' in text:
            return text
        # Wrap matched text in highlight span
        return f'<span class="search-highlight">{text}</span>'
    
    # Split content into HTML tags and text content
    parts = re.split(r'(<[^>]+>)', html_content)
    
    # Process only text parts (odd indices after split)
    for i in range(len(parts)):
        if i % 2 == 0 and parts[i]:  # Text content
            # Apply highlighting with case-insensitive matching
            parts[i] = re.sub(pattern, replace_in_text_nodes, parts[i], flags=re.IGNORECASE)
    
    return ''.join(parts)


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


def apply_redacted_rendering(notes, search_query=None):
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
        elif (note_dict.get('search_relevance') in ['direct_match', 'relevant'] and 
              not note_dict.get('flags', {}).get('isEditing', False) and
              search_query):
            # Apply highlighting to relevant non-editing notes
            note_dict['content'] = highlight_search_terms(note_dict['content'], search_query)
    
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


EMPTY_EDIT_PLACEHOLDER = "<div><br></div>"


def build_note_tree(
    db_manager,
    db,
    parent_id=None,
    editing_note_id=None,
    search_query=None,
    allowed_root_ids=None,
):
    """Build a hierarchical tree, preferring the in-memory store when loaded."""

    try:
        search_active = bool(search_query and str(search_query).strip())
        constrained_roots = allowed_root_ids if not search_active else None

        if note_store.loaded:
            note_tree = _build_tree_from_store(
                parent_id,
                editing_note_id,
                constrained_roots,
            )
        else:
            note_tree = _build_tree_from_db(
                db_manager,
                db,
                parent_id,
                editing_note_id,
                constrained_roots,
            )

        if parent_id is None and search_query:
            note_tree = filter_notes_by_search(note_tree, search_query)
            apply_redacted_rendering(note_tree, search_query)

        return note_tree

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error building note tree")
        raise


def _build_tree_from_store(parent_id, editing_note_id, allowed_root_ids):
    """Recursively construct the note tree using the in-memory store."""

    note_tree = []
    child_ids = note_store.get_children(parent_id)

    if parent_id is None and allowed_root_ids is not None:
        if not allowed_root_ids:
            return []
        if not isinstance(allowed_root_ids, set):
            allowed_root_ids = set(allowed_root_ids)
        child_ids = [note_id for note_id in child_ids if note_id in allowed_root_ids]

    for note_id in child_ids:
        record = note_store.get_note(note_id)
        children = _build_tree_from_store(note_id, editing_note_id, allowed_root_ids)
        is_editing = note_id == editing_note_id

        rendered = render_editing_mode(record) if is_editing else render_read_only_mode(record)
        if is_editing and (not rendered or not rendered.strip()):
            rendered = EMPTY_EDIT_PLACEHOLDER

        note_tree.append(
            {
                'id': record.id,
                'content': rendered,
                'raw_content': record.content,
                'parent_id': record.parent_id or '',
                'children': children,
                'flags': {
                    'isEditing': is_editing,
                    'isCollapsed': bool(record.is_collapsed),
                },
            }
        )

    return note_tree


def _build_tree_from_db(db_manager, db, parent_id, editing_note_id, allowed_root_ids):
    """Fallback tree construction that queries the database."""

    note_tree = []
    notes = db_manager.get_ordered_child_list(db, parent_id)

    if parent_id is None and allowed_root_ids is not None:
        if not allowed_root_ids:
            return []
        if not isinstance(allowed_root_ids, set):
            allowed_root_ids = set(allowed_root_ids)
        notes = [note for note in notes if note.id in allowed_root_ids]

    for note in notes:
        children = _build_tree_from_db(db_manager, db, note.id, editing_note_id, allowed_root_ids)

        decrypted_content = get_cached_content(note.id)
        if decrypted_content is None:
            raise RuntimeError(
                f"CACHE CORRUPTION: Note {note.id} not found in cache! Cache system has failed."
            )

        class DecryptedNote:
            def __init__(self, original_note, decrypted_content):
                self.id = original_note.id
                self.content = decrypted_content
                self.parent_id = original_note.parent_id
                self.created_at = original_note.created_at
                self.updated_at = original_note.updated_at
                self.is_collapsed = getattr(original_note, 'is_collapsed', False)

        decrypted_note = DecryptedNote(note, decrypted_content)
        rendered_content = (
            render_editing_mode(decrypted_note)
            if note.id == editing_note_id
            else render_read_only_mode(decrypted_note)
        )
        if note.id == editing_note_id and (not rendered_content or not rendered_content.strip()):
            rendered_content = EMPTY_EDIT_PLACEHOLDER

        note_tree.append(
            {
                'id': note.id,
                'content': rendered_content,
                'raw_content': decrypted_content,
                'parent_id': note.parent_id or '',
                'children': children,
                'flags': {
                    'isEditing': note.id == editing_note_id,
                    'isCollapsed': bool(getattr(note, 'is_collapsed', False)),
                },
            }
        )

    return note_tree
