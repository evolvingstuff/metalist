from typing import Optional
from threading import Lock
import logging

from ..models.api_transaction import ApiTransaction
from ..undo_redo import CommandStack

logger = logging.getLogger(__name__)


class TransactionManager:
    """
    Manages transaction state and undo/redo functionality.
    
    This class replaces the global state dictionary with proper dependency injection.
    It maintains the same singleton behavior - only one transaction can be active
    at a time across the entire application.
    """
    
    def __init__(self):
        self.current_transaction: Optional[ApiTransaction] = None
        self.command_stack = CommandStack()
        self.lock = Lock()
        self.last_search_query: Optional[str] = None
    
    def start_transaction(self) -> ApiTransaction:
        """
        Start a new transaction.
        
        Raises:
            Exception: If a transaction is already in progress
            
        Returns:
            ApiTransaction: The newly created transaction
        """
        with self.lock:
            if self.current_transaction is not None:
                raise Exception("Transaction already in progress")
            
            self.current_transaction = ApiTransaction(transaction_manager=self)
            logger.debug(f"Transaction {self.current_transaction.uuid} started")
            return self.current_transaction
    
    def end_transaction(self):
        """End the current transaction and clean up."""
        with self.lock:
            if self.current_transaction:
                logger.debug(f"Transaction {self.current_transaction.uuid} ended")
            self.current_transaction = None
    
    def get_current_transaction(self) -> Optional[ApiTransaction]:
        """Get the currently active transaction, if any."""
        return self.current_transaction
    
    def check_context_change(self, current_search_query: Optional[str] = None):
        """
        Check if the search context has changed and clear undo stack if so.
        
        Args:
            current_search_query: The current search query from the request
        """
        # Normalize empty strings to None for consistent comparison
        normalized_current = current_search_query.strip() if current_search_query else None
        normalized_current = normalized_current if normalized_current else None
        
        normalized_last = self.last_search_query.strip() if self.last_search_query else None
        normalized_last = normalized_last if normalized_last else None
        
        if normalized_current != normalized_last:
            if self.command_stack.stack:
                logger.info(f"Search context changed ('{normalized_last}' → '{normalized_current}'), clearing undo stack (was {len(self.command_stack.stack)} commands)")
                self.command_stack.clear_all()
            else:
                logger.debug(f"Search context changed ('{normalized_last}' → '{normalized_current}'), undo stack was already empty")
            
            self.last_search_query = current_search_query
        else:
            logger.debug(f"Search context unchanged: '{normalized_current}'")

    def add_command_to_stack(self, command):
        """Add a command to the undo/redo stack."""
        self.command_stack.push(command)
        logger.info(f"Command added to stack (size = {len(self.command_stack.stack)})")
    
    def undo(self, db) -> bool:
        """Perform an undo operation."""
        if self.command_stack.current_index >= 0:
            self.command_stack.undo(db)
            return True
        return False
    
    def redo(self, db) -> bool:
        """Perform a redo operation."""
        if self.command_stack.current_index < len(self.command_stack.stack) - 1:
            self.command_stack.redo(db)
            return True
        return False


# Global singleton instance - this is the only global state we need
_transaction_manager_instance: Optional[TransactionManager] = None


def get_transaction_manager() -> TransactionManager:
    """
    Get the singleton TransactionManager instance.
    
    This is a FastAPI dependency that provides the TransactionManager
    to services that need it.
    """
    global _transaction_manager_instance
    if _transaction_manager_instance is None:
        _transaction_manager_instance = TransactionManager()
    return _transaction_manager_instance