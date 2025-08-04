from sqlalchemy.orm import Session
import logging

from .base_service import BaseQueryService
from ..models.linked_list import LinkedListManager

logger = logging.getLogger(__name__)


class UndoRedoService(BaseQueryService):
    """Service for undo/redo operations - uses BaseQueryService since these
    operations manage their own transaction state"""
    
    def undo(self) -> dict:
        """Perform an undo operation"""
        undid = LinkedListManager.undo(self.db)
        
        if undid:
            logger.info("Undo operation successful")
            return {"status": "success", "message": "Undo successful"}
        else:
            logger.info("No operations to undo")
            return {"status": "noop", "message": "No actions to undo"}
    
    def redo(self) -> dict:
        """Perform a redo operation"""
        redid = LinkedListManager.redo(self.db)
        
        if redid:
            logger.info("Redo operation successful")
            return {"status": "success", "message": "Redo successful"}
        else:
            logger.info("No operations to redo")
            return {"status": "noop", "message": "No actions to redo"}