from abc import ABC
from sqlalchemy.orm import Session
from threading import Lock
from ..global_state_mod import global_state
from ..models.api_transaction import ApiTransaction
import logging

logger = logging.getLogger(__name__)

# Global lock for transaction management (shared across all services)
transaction_lock = Lock()


class BaseTransactionService(ABC):
    """Base class for services that need transaction tracking for undo/redo"""
    
    def __init__(self, db: Session):
        self.db = db
        self.transaction = None
        self._operation_name = None
    
    def __enter__(self):
        """Context manager entry - sets up transaction tracking"""
        with transaction_lock:
            if global_state["current_transaction"] is not None:
                raise Exception("Transaction already in progress")
            
            self.transaction = ApiTransaction()
            global_state["current_transaction"] = self.transaction
            logger.debug(f"Transaction {self.transaction.uuid} started")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - handles commit/rollback and cleanup"""
        try:
            if exc_type is None:
                # No exception, commit the transaction
                self._commit()
            else:
                # Exception occurred, rollback
                self._rollback()
                logger.error(f"Transaction rolled back due to: {exc_val}")
        finally:
            # Always clean up the global transaction
            with transaction_lock:
                global_state["current_transaction"] = None
            logger.debug(f"Transaction {self.transaction.uuid if self.transaction else 'None'} cleaned up")
    
    def _commit(self):
        """Commit the database transaction and finalize command tracking"""
        try:
            # Commit database changes
            self.db.commit()
            
            # Finalize the transaction for undo/redo
            if self.transaction and self._operation_name:
                # Check if any changes were actually made
                tot = (len(self.transaction.state_before_updated) + 
                      len(self.transaction.state_current_updated) + 
                      len(self.transaction.state_added) + 
                      len(self.transaction.state_deleted))
                
                if tot > 0:
                    self.transaction.finalize_transaction(self._operation_name)
                    command_stack = global_state["command_stack"]
                    logger.info(f'Command stack size: {len(command_stack.stack)}')
                else:
                    logger.warning(f"No changes detected for operation: {self._operation_name}")
                    
        except Exception as e:
            self.db.rollback()
            logger.exception(f"Error during commit: {e}")
            raise
    
    def _rollback(self):
        """Rollback the database transaction"""
        self.db.rollback()
    
    def _set_operation(self, name: str):
        """Set the operation name for command tracking"""
        self._operation_name = name


class BaseQueryService(ABC):
    """Base class for read-only services that don't need transaction tracking"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def __enter__(self):
        """Context manager entry for read operations"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - commit read transaction if needed"""
        if exc_type is None:
            self.db.commit()
        else:
            self.db.rollback()