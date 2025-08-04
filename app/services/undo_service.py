from sqlalchemy.orm import Session
import logging

from .base_service import BaseQueryService

logger = logging.getLogger(__name__)


class UndoRedoService(BaseQueryService):
    """Service for undo/redo operations - uses BaseQueryService since these
    operations manage their own transaction state"""
    
    def __init__(self, db: Session, transaction_manager):
        super().__init__(db)
        self.transaction_manager = transaction_manager
    
    def undo(self) -> dict:
        """Perform an undo operation"""
        undid = self.transaction_manager.undo(self.db)
        
        if undid:
            logger.info("Undo operation successful")
            return {"status": "success", "message": "Undo successful"}
        else:
            logger.info("No operations to undo")
            return {"status": "noop", "message": "No actions to undo"}
    
    def redo(self) -> dict:
        """Perform a redo operation"""
        redid = self.transaction_manager.redo(self.db)
        
        if redid:
            logger.info("Redo operation successful")
            return {"status": "success", "message": "Redo successful"}
        else:
            logger.info("No operations to redo")
            return {"status": "noop", "message": "No actions to redo"}