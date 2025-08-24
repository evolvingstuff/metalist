from sqlalchemy.orm import Session
import logging

from .base_service import BaseQueryService
from .sync_state import generate_new_uuid, set_server_sync_uuid

logger = logging.getLogger(__name__)


class UndoRedoService(BaseQueryService):
    """Service for undo/redo operations - uses BaseQueryService since these
    operations manage their own transaction state"""
    
    def __init__(self, db: Session, transaction_manager):
        super().__init__(db)
        self.transaction_manager = transaction_manager
    
    def undo(self, client_id: str = None) -> dict:
        """Perform an undo operation"""
        logger.info(f"🔧 UNDO SERVICE: undo() called for client {client_id}")
        undid = self.transaction_manager.undo(self.db, client_id)
        
        if undid:
            set_server_sync_uuid(generate_new_uuid())
            logger.info("Undo operation successful")
            return {"status": "success", "message": "Undo successful"}
        else:
            logger.info("No operations to undo")
            return {"status": "noop", "message": "No actions to undo"}
    
    def redo(self, client_id: str = None) -> dict:
        """Perform a redo operation"""
        redid = self.transaction_manager.redo(self.db, client_id)
        
        if redid:
            set_server_sync_uuid(generate_new_uuid())
            logger.info("Redo operation successful")
            return {"status": "success", "message": "Redo successful"}
        else:
            logger.info("No operations to redo")
            return {"status": "noop", "message": "No actions to redo"}