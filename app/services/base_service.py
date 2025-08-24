from abc import ABC
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class BaseTransactionService(ABC):
    """Base class for services that need transaction tracking for undo/redo"""
    
    def __init__(self, db: Session, transaction_manager, client_id: str = None):
        self.db = db
        self.transaction_manager = transaction_manager
        self.client_id = client_id
        self.transaction = None
        self._operation_name = None
    
    def __enter__(self):
        """Context manager entry - sets up transaction tracking"""
        self.transaction = self.transaction_manager.start_transaction(self.client_id)
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
            # Always clean up the transaction
            self.transaction_manager.end_transaction()
            logger.debug(f"Transaction {self.transaction.uuid if self.transaction else 'None'} cleaned up")
    
    def _commit(self):
        """Commit the database transaction and finalize command tracking"""
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
            else:
                logger.warning(f"No changes detected for operation: {self._operation_name}")
    
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