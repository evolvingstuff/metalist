from typing import Optional
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class TransactionManager:
    """
    Manages transaction state and undo/redo functionality.
    
    This class replaces the global state dictionary with proper dependency injection.
    It maintains the same singleton behavior - only one transaction can be active
    at a time across the entire application.
    
    The undo/redo stack is owned by a single client at a time. When a different
    client performs an operation, the stack is cleared and ownership transfers.
    """
    
    def __init__(self):
        # Snapshot-based undo subsystem removed; keep minimal transaction shell
        self.current_transaction = None
        self.command_stack_size = 0
        self.lock = Lock()
        self.last_search_query: Optional[str] = None
        self.active_client_id: Optional[str] = None
    
    def start_transaction(self, db, client_id: Optional[str]):
        """
        Start a new transaction.
        
        Args:
            client_id: The ID of the client starting the transaction
        
        Raises:
            Exception: If a transaction is already in progress
            
        Returns:
            ApiTransaction: The newly created transaction
        """
        with self.lock:
            if self.current_transaction is not None:
                raise Exception("Transaction already in progress")
            # Return a lightweight token object
            self.current_transaction = object()
            logger.debug(f"Transaction started for client {client_id}")
            return self.current_transaction
    
    def end_transaction(self):
        """End the current transaction and clean up."""
        with self.lock:
            self.current_transaction = None
    
    def get_current_transaction(self):
        """Get the currently active transaction, if any."""
        return self.current_transaction
    
    def check_context_change(self, current_search_query: Optional[str]):
        """
        Check if the search context has changed and clear undo stack if so.
        
        Args:
            current_search_query: The current search query from the request
        """
        # Normalize empty strings to None for consistent comparison
        if current_search_query:
            normalized_current = current_search_query.strip()
        else:
            normalized_current = None
        if normalized_current:
            normalized_current = normalized_current
        else:
            normalized_current = None
        
        if self.last_search_query:
            normalized_last = self.last_search_query.strip()
        else:
            normalized_last = None
        if normalized_last:
            normalized_last = normalized_last
        else:
            normalized_last = None
        
        if normalized_current != normalized_last:
            if self.command_stack_size:
                logger.info(f"Search context changed ('{normalized_last}' → '{normalized_current}'), clearing undo stack (was {self.command_stack_size} commands)")
                self.command_stack_size = 0
            else:
                logger.debug(f"Search context changed ('{normalized_last}' → '{normalized_current}'), undo stack was already empty")
            
            self.last_search_query = current_search_query
        else:
            logger.debug(f"Search context unchanged: '{normalized_current}'")

    def check_client_ownership(self, client_id: str):
        """
        Check if the client owns the undo stack. If not, clear the stack and transfer ownership.
        
        Args:
            client_id: The ID of the client performing an operation
        """
        if self.active_client_id != client_id:
            if self.command_stack_size:
                logger.info(f"🔧 UNDO STACK: Client ownership changed from {self.active_client_id} to {client_id}, clearing stack (was {self.command_stack_size} commands)")
                self.command_stack_size = 0
            else:
                logger.info(f"🔧 UNDO STACK: Client ownership set to {client_id} (stack was empty)")
            
            self.active_client_id = client_id

    def add_command_to_stack(self, command, client_id: str):
        """Add a command to the undo/redo stack."""
        self.check_client_ownership(client_id)
        self.command_stack_size += 1
        logger.info(f"🔧 UNDO STACK: Command added to stack for client {client_id} (size={self.command_stack_size})")
    
    def undo(self, db, client_id: Optional[str]) -> bool:
        """Perform an undo operation."""
        logger.info(f"🔧 UNDO STACK: Undo requested by client {client_id} (size = {len(self.command_stack.stack)}, index = {self.command_stack.current_index}, owner = {self.active_client_id})")
        
        # Check if client owns the stack or if no ownership is set
        if self.active_client_id and client_id and self.active_client_id != client_id:
            logger.info(f"🔧 UNDO STACK: Undo denied - client {client_id} does not own stack (owned by {self.active_client_id})")
            return False
            
        logger.info(f"🔧 UNDO STACK: No operations to undo (snapshot-based engine removed)")
        return False
    
    def redo(self, db, client_id: Optional[str]) -> bool:
        """Perform a redo operation."""
        logger.info(f"🔧 UNDO STACK: Redo requested by client {client_id} (size = {len(self.command_stack.stack)}, index = {self.command_stack.current_index}, owner = {self.active_client_id})")
        
        # Check if client owns the stack or if no ownership is set
        if self.active_client_id and client_id and self.active_client_id != client_id:
            logger.info(f"🔧 UNDO STACK: Redo denied - client {client_id} does not own stack (owned by {self.active_client_id})")
            return False
            
        logger.info(f"🔧 UNDO STACK: No operations to redo (snapshot-based engine removed)")
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
