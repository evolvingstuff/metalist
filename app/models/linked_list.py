from typing import List, Optional, Any
from sqlalchemy.orm import Session
from .enums import MovePosition
from .database import DBNote
from ..global_state_mod import global_state

# Import the new specialized classes
from .list_traversal import ListTraversal
from .note_crud import NoteCRUD
from .list_operations import ListOperations
from .undo_redo_operations import UndoRedoOperations


class LinkedListManager:
    """
    Facade class that maintains the original API while delegating to specialized classes.
    This ensures backward compatibility while following the Single Responsibility Principle.
    """

    # Delegate to ListTraversal
    @staticmethod
    def validate_list(db: Session, parent_id: Optional[str] = None) -> bool:
        return ListTraversal.validate_list(db, parent_id)

    @staticmethod
    def get_ordered_child_list(db: Session, parent_id: Optional[str] = None) -> List[Any]:
        return ListTraversal.get_ordered_child_list(db, parent_id)

    @staticmethod
    def _would_create_cycle(db, note_id: str, new_parent_id: str) -> bool:
        return ListTraversal.would_create_cycle(db, note_id, new_parent_id)

    # Delegate to UndoRedoOperations
    @staticmethod
    def undo(db: Session) -> bool:
        return UndoRedoOperations.undo(db)

    @staticmethod
    def redo(db: Session) -> bool:
        return UndoRedoOperations.redo(db)

    # Delegate to NoteCRUD
    @staticmethod
    def create_note_top(db: Session, note_id: str, parent_id: Optional[str] = None) -> None:
        return NoteCRUD.create_note_top(db, note_id, parent_id)

    @staticmethod
    def get_note(db: Session, note_id: str) -> DBNote:
        return NoteCRUD.get_note(db, note_id)

    @staticmethod
    def update_note(db: Session, note_id: str, content: str):
        return NoteCRUD.update_note(db, note_id, content)

    @staticmethod
    def delete_note(db: Session, note_id: str) -> None:
        return NoteCRUD.delete_note(db, note_id)

    @staticmethod
    def create_note_drop(db: Session, note_id: str, new_parent_id: str = None, sibling_id: str = None, position: MovePosition = None):
        return NoteCRUD.create_note_drop(db, note_id, new_parent_id, sibling_id, position)

    # Delegate to ListOperations
    @staticmethod
    def move_note(db: Session, note_id: str, new_parent_id: Optional[str] = None,
                  sibling_id: Optional[str] = None, position: Optional[MovePosition] = None):
        return ListOperations.move_note(db, note_id, new_parent_id, sibling_id, position)