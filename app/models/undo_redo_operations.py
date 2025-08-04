from sqlalchemy.orm import Session
from ..global_state_mod import global_state


class UndoRedoOperations:
    """Handles undo/redo operations"""
    
    @staticmethod
    def undo(db: Session) -> bool:
        command_stack = global_state["command_stack"]
        # TODO refactor this
        if command_stack.current_index >= 0:
            command_stack.undo(db)
            return True
        return False

    @staticmethod
    def redo(db: Session) -> bool:
        command_stack = global_state["command_stack"]
        # TODO refactor this
        if command_stack.current_index < len(command_stack.stack) - 1:
            command_stack.redo(db)
            return True
        return False