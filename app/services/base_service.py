from abc import ABC
from typing import Optional
import logging

from app.services.integrity import (
    should_run_integrity_checks,
    snapshot_note_count,
    assert_note_count,
    assert_linked_list_integrity,
)
from app.models.database import SafeSession

logger = logging.getLogger(__name__)


class BaseTransactionService(ABC):
    """Base class for services that need transaction tracking for undo/redo"""
    
    def __init__(self, db: SafeSession, transaction_manager, client_id: str = None):
        self.db = db
        self.transaction_manager = transaction_manager
        self.client_id = client_id
        self.transaction = None
        self._operation_name = None
        self._note_count_snapshot: Optional[int] = None
        self._expected_note_delta: Optional[int] = None
    
    def __enter__(self):
        """Context manager entry - sets up transaction tracking"""
        self.transaction = self.transaction_manager.start_transaction(self.db, self.client_id)
        if should_run_integrity_checks():
            self._note_count_snapshot = snapshot_note_count(self.db)
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
            self._note_count_snapshot = None
            self._expected_note_delta = None
    
    def _commit(self):
        """Commit the database transaction and finalize command tracking"""
        # Commit database changes
        self.db.commit()

        if should_run_integrity_checks():
            op_name = self._operation_name or "unspecified_operation"
            assert_note_count(
                self.db,
                self._note_count_snapshot,
                self._expected_note_delta,
                op_name,
            )
            assert_linked_list_integrity(self.db, op_name)
        
        # Finalize the transaction for undo/redo
        if self.transaction and self._operation_name:
            if not self.transaction.finalize_transaction(self._operation_name):
                logger.warning(f"No changes detected for operation: {self._operation_name}")
    
    def _rollback(self):
        """Rollback the database transaction"""
        self.db.rollback()
    
    def _set_operation(self, name: str):
        """Set the operation name for command tracking"""
        self._operation_name = name

    def expect_note_delta(self, delta: Optional[int]) -> None:
        """Record expected change in note count (dev-only integrity checks)."""
        self._expected_note_delta = delta


class BaseQueryService(ABC):
    """Base class for read-only services that don't need transaction tracking"""
    
    def __init__(self, db: SafeSession):
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
