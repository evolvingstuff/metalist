"""In-memory content cache for encrypted notes.

Provides fast search access to decrypted note content while maintaining
encrypted-at-rest storage. Cache is populated on startup and maintained
automatically via SQLAlchemy events.
"""

import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session

from ..models.database import DBNote
from ..utils.encryption import decrypt

logger = logging.getLogger(__name__)

# Global in-memory cache: {note_id: decrypted_content}
_search_cache: Dict[str, str] = {}


def get_cached_content(note_id: str) -> Optional[str]:
    """Retrieve decrypted content from cache.
    
    Args:
        note_id: ID of note to retrieve
        
    Returns:
        Decrypted content or None if not in cache
    """
    return _search_cache.get(note_id)


def cache_note(note_id: str, decrypted_content: str) -> None:
    """Add or update note content in cache.
    
    Args:
        note_id: ID of note to cache
        decrypted_content: Plain text content to store in cache
    """
    _search_cache[note_id] = decrypted_content
    logger.debug(f"Cached content for note {note_id[:8]}...")


def remove_cached_note(note_id: str) -> None:
    """Remove note from cache.
    
    Args:
        note_id: ID of note to remove
    """
    if note_id in _search_cache:
        del _search_cache[note_id]
        logger.debug(f"Removed cached content for note {note_id[:8]}...")


def get_cache_size() -> int:
    """Get current number of notes in cache.
    
    Returns:
        Number of cached notes
    """
    return len(_search_cache)


def clear_cache() -> None:
    """Clear all cached content."""
    global _search_cache
    _search_cache = {}
    logger.info("Cache cleared")


def populate_cache_from_db(db: Session) -> None:
    """Populate cache with all notes from database on startup.
    
    Args:
        db: Database session to read from
    """
    logger.info("Populating content cache from database...")
    
    try:
        # Get all notes from database
        notes = db.query(DBNote).all()
        
        # Clear existing cache
        clear_cache()
        
        # Decrypt and cache each note's content
        for note in notes:
            if note.content:  # Skip empty content
                decrypted_content = decrypt(note.content)
                cache_note(note.id, decrypted_content)
        
        logger.info(f"Content cache populated with {len(notes)} notes")
        
    except Exception as e:
        logger.error(f"Failed to populate cache from database: {e}")
        raise


def get_all_cached_notes() -> Dict[str, str]:
    """Get all cached content (for debugging).
    
    Returns:
        Copy of entire cache dictionary
    """
    return _search_cache.copy()