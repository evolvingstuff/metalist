"""In-memory content cache for encrypted notes.

Provides fast search access to decrypted note content while maintaining
encrypted-at-rest storage. Cache is populated on startup and maintained
manually by the sqlite helper layer and service hooks.
"""

import logging
from typing import Dict, Optional

from app.db import connect_reader
from app.db.notes_sql import fetch_all_for_cache

from ..models.database import SafeSession
from ..utils.encryption import get_encryption_service

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


def populate_cache_from_db(db: SafeSession | None = None) -> None:
    """Populate cache with all notes from database on startup.

    The optional ``db`` parameter is retained for backwards compatibility but
    is no longer used now that the helper layer opens its own read
    connections.
    """
    logger.info("Populating content cache from database...")
    
    try:
        with connect_reader("cache:populate") as connection:
            notes = fetch_all_for_cache(connection)
        
        # Clear existing cache
        clear_cache()
        
        # Decrypt and cache each note's content
        encryption_service = get_encryption_service()
        
        for note in notes:
            note_id = note["id"]
            content = note["content"]
            nonce = note["encryption_nonce"]
            tag = note["encryption_tag"]

            if content is None:
                raise RuntimeError(
                    f"Cache population failed: Note {note_id} has NULL content."
                )

            try:
                # Handle both encrypted and unencrypted content
                if nonce is not None and tag is not None:
                    # Encrypted content - decrypt using new separate fields approach
                    if encryption_service and encryption_service.dek:
                        decrypted_content = encryption_service.decrypt_from_storage(
                            content, nonce, tag
                        )
                    else:
                        # No encryption key available, can't decrypt
                        logger.warning(f"No encryption key available to decrypt note {note_id}")
                        decrypted_content = f"[Encrypted content - login required]"
                else:
                    # Unencrypted content, including empty string which must still be cached
                    decrypted_content = content

                cache_note(note_id, decrypted_content)
            except Exception as e:
                # FAIL FAST AND LOUD - NO SILENT FAILURES
                logger.error(f"🚨 FATAL: Failed to process note {note_id} during cache population: {e}")
                logger.error(f"🚨 Cache system integrity compromised!")
                logger.error(f"🚨 CRASHING IMMEDIATELY")
                raise RuntimeError(f"Cache population failed: Could not process note {note_id}: {e}") from e
        
        logger.info(f"Content cache populated with {len(notes)} notes")
        
    except Exception as e:
        logger.error(f"Failed to populate cache from database: {e}")
        raise


def refresh_encrypted_cache(db: SafeSession) -> None:
    """Refresh cache for encrypted notes when encryption key becomes available.
    
    This should be called after user logs in and encryption key is set.
    
    Args:
        db: Database session to read from
    """
    logger.info("Refreshing encrypted content in cache...")
    
    try:
        encryption_service = get_encryption_service()
        if not encryption_service or not encryption_service.dek:
            logger.warning("No encryption key available for cache refresh")
            return
        
        with SafeSession.allow_reads("cache:refresh_encrypted"):
            rows = fetch_all_for_cache(db.connection())

        encrypted_notes = [
            row
            for row in rows
            if row.get("encryption_nonce") is not None and row.get("encryption_tag") is not None
        ]
        
        refreshed_count = 0
        
        for note in encrypted_notes:
            content = note["content"]
            nonce = note["encryption_nonce"]
            tag = note["encryption_tag"]
            note_id = note["id"]

            if content is None:
                raise RuntimeError(
                    f"Cache refresh failed: Encrypted note {note_id} has NULL content."
                )

            try:
                # Decrypt using separate fields approach
                decrypted_content = encryption_service.decrypt_from_storage(
                    content,
                    nonce,
                    tag,
                )
                cache_note(note_id, decrypted_content)
                refreshed_count += 1
            except Exception as e:
                # FAIL FAST AND LOUD - NO SILENT FAILURES
                logger.error(f"🚨 FATAL: Failed to refresh encrypted note {note_id}: {e}")
                logger.error(f"🚨 Cache refresh system integrity compromised!")
                logger.error(f"🚨 CRASHING IMMEDIATELY")
                raise RuntimeError(f"Cache refresh failed: Could not process note {note_id}: {e}") from e
        
        logger.info(f"Refreshed {refreshed_count} encrypted notes in cache")
        
    except Exception as e:
        logger.error(f"Failed to refresh encrypted cache: {e}")
        raise


def get_all_cached_notes() -> Dict[str, str]:
    """Get all cached content (for debugging).
    
    Returns:
        Copy of entire cache dictionary
    """
    return _search_cache.copy()
