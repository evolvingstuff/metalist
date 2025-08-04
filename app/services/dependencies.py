from typing import Generator
from sqlalchemy.orm import Session
from contextlib import contextmanager
from fastapi import Depends
import time
import logging

from ..api.dependencies import get_db
from .note_service import NoteService
from .query_service import NoteQueryService
from .undo_service import UndoRedoService
from .transaction_manager import get_transaction_manager, TransactionManager

logger = logging.getLogger(__name__)

# Configuration for API response delays (same as original)
API_DELAY = {
    "ENABLED": False,  # Set to True to enable artificial delays
    "DEFAULT": 1.0,    # Default delay in seconds
    "RANDOM": False,   # Whether to use random delay within MIN/MAX range
    "MIN": 0.5,        # Minimum random delay (if RANDOM is True)
    "MAX": 2.0,        # Maximum random delay (if RANDOM is True)
    # Per-endpoint delays, override DEFAULT (add as needed)
    "ENDPOINTS": {
        "undo": 1.5,
        "redo": 1.5,
        "get_notes_fragment": 1.0
    }
}


def apply_delay(operation_name: str):
    """Apply configurable delay for testing loading states"""
    if not API_DELAY["ENABLED"]:
        return
        
    # Determine delay time
    delay = API_DELAY["DEFAULT"]
    
    # Check if this endpoint has a specific delay
    if operation_name in API_DELAY["ENDPOINTS"]:
        delay = API_DELAY["ENDPOINTS"][operation_name]
        
    # Apply random delay if configured
    if API_DELAY["RANDOM"]:
        import random
        delay = random.uniform(API_DELAY["MIN"], API_DELAY["MAX"])
        
    # Log the delay (helpful for debugging)
    logger.info(f"[API Delay] Adding {delay:.2f}s delay to {operation_name}...")
    
    # Apply the delay
    time.sleep(delay)


@contextmanager
def get_note_service(db: Session, transaction_manager: TransactionManager) -> Generator[NoteService, None, None]:
    """Dependency injection for NoteService with transaction management"""
    with NoteService(db, transaction_manager) as service:
        yield service


@contextmanager
def get_query_service(db: Session) -> Generator[NoteQueryService, None, None]:
    """Dependency injection for NoteQueryService"""
    with NoteQueryService(db) as service:
        yield service


@contextmanager
def get_undo_service(db: Session, transaction_manager: TransactionManager) -> Generator[UndoRedoService, None, None]:
    """Dependency injection for UndoRedoService"""
    with UndoRedoService(db, transaction_manager) as service:
        yield service