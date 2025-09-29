from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
import uuid
import logging

from .base_service import BaseTransactionService
from ..models.linked_list import LinkedListManager
from ..models.enums import MovePosition
from ..models.utils import copy_note
from .integrity import count_subtree
from .sync_state import generate_new_uuid, set_server_sync_uuid

logger = logging.getLogger(__name__)


class NoteService(BaseTransactionService):
    """Service for note CRUD operations with transaction tracking"""
    
    def create_note(self, parent_id: Optional[str] = None, first_visible_note_id: Optional[str] = None, search_query: Optional[str] = None) -> dict:
        """Create a new note at the top of the list (or before first visible note)"""
        self._set_operation("create_note_top")
        assert self.client_id, "create_note requires client_id"
        self.expect_note_delta(1)
        
        note_id = str(uuid.uuid4())
        
        if first_visible_note_id:
            # Insert before the first visible note using move operations
            LinkedListManager.create_note_top(self.db, note_id, parent_id)
            LinkedListManager.move_note(
                self.db, note_id, parent_id, first_visible_note_id, MovePosition.BEFORE
            )
        else:
            # Default behavior - create at absolute top
            LinkedListManager.create_note_top(self.db, note_id, parent_id)
        
        # Auto-populate with search terms if creating a root-level note during search
        if search_query and search_query.strip() and not parent_id:
            content = f"<div> </div><div><br></div><div>/* {search_query.strip()} */</div>"
            LinkedListManager.update_note(self.db, note_id, content)
            logger.info(f"Auto-populated note {note_id} with search terms: '{search_query.strip()}'")
        
        logger.info(f"Created note {note_id} with parent {parent_id} before {first_visible_note_id}")
        
        # Generate new UUID and update server state
        new_uuid = generate_new_uuid()
        set_server_sync_uuid(new_uuid)
        
        return {"id": note_id, "status": "created", "updateUUID": new_uuid}
    
    def update_note(self, note_id: str, content: str) -> dict:
        """Update note content"""
        self._set_operation("update_note")
        assert self.client_id, "update_note requires client_id"
        assert isinstance(content, str), "content must be a string"
        self.expect_note_delta(0)
        
        LinkedListManager.update_note(self.db, note_id, content)
        
        logger.info(f"Updated note {note_id}")
        
        # Generate new UUID and update server state
        new_uuid = generate_new_uuid()
        set_server_sync_uuid(new_uuid)
        
        return {"status": "updated", "updateUUID": new_uuid}

    def set_note_collapse(self, note_id: str, collapsed: bool) -> dict:
        """Set the collapsed state of a note"""

        note = LinkedListManager.get_note(self.db, note_id)
        desired_state = bool(collapsed)
        current_state = bool(getattr(note, 'is_collapsed', False))

        if current_state == desired_state:
            logger.info(f"Collapse state for note {note_id} already {desired_state}")
            return {"status": "unchanged", "isCollapsed": current_state}

        self._set_operation("set_note_collapse")
        assert self.client_id, "set_note_collapse requires client_id"
        self.expect_note_delta(0)
        note.is_collapsed = desired_state

        logger.info(f"Set collapse state for note {note_id} to {desired_state}")

        new_uuid = generate_new_uuid()
        set_server_sync_uuid(new_uuid)

        return {"status": "updated", "isCollapsed": desired_state, "updateUUID": new_uuid}

    def delete_note(self, note_id: str) -> dict:
        """Delete a note and all its descendants"""
        self._set_operation("delete_note")
        assert self.client_id, "delete_note requires client_id"
        subtree_total = count_subtree(self.db, note_id)
        self.expect_note_delta(-subtree_total)
        
        
        # Check if deleting would leave list empty (for frontend state management)
        all_notes = LinkedListManager.get_ordered_child_list(self.db, None)
        notes_left = len([n for n in all_notes if n.id != note_id])
        all_deleted = (notes_left == 0)
        
        LinkedListManager.delete_note(self.db, note_id)
        
        logger.info(f"Deleted note {note_id}")
        
        # Generate new UUID and update server state
        new_uuid = generate_new_uuid()
        set_server_sync_uuid(new_uuid)
        
        return {"status": "deleted", "all_deleted": all_deleted, "updateUUID": new_uuid}
    
    def move_note(self, note_id: str, new_parent_id: Optional[str] = None,
                  sibling_id: Optional[str] = None, position: Optional[MovePosition] = None) -> dict:
        """Move a note to a new position"""
        self._set_operation("move_note")
        assert self.client_id, "move_note requires client_id"
        self.expect_note_delta(0)
        
        # Validate parent exists if specified
        if new_parent_id:
            parent = LinkedListManager.get_note(self.db, new_parent_id)
            if not parent:
                raise HTTPException(status_code=404, detail=f"Parent note {new_parent_id} not found")
        
        # Validate sibling exists if specified
        if sibling_id:
            sibling = LinkedListManager.get_note(self.db, sibling_id)
            if not sibling:
                raise HTTPException(status_code=404, detail=f"Sibling note {sibling_id} not found")
        
        LinkedListManager.move_note(
            self.db, note_id, new_parent_id, sibling_id, position
        )
        
        logger.info(f"Moved note {note_id} to parent={new_parent_id}, sibling={sibling_id}, position={position}")
        
        # Generate new UUID and update server state
        new_uuid = generate_new_uuid()
        set_server_sync_uuid(new_uuid)
        
        return {"status": "moved", "updateUUID": new_uuid}
    
    def create_note_with_position(self, new_parent_id: Optional[str] = None,
                                 sibling_id: Optional[str] = None, 
                                 position: Optional[MovePosition] = None) -> dict:
        """Create a new note at a specific position"""
        self._set_operation("create_note_drop")
        assert self.client_id, "create_note_with_position requires client_id"
        self.expect_note_delta(1)
        
        note_id = str(uuid.uuid4())
        LinkedListManager.create_note_drop(
            self.db, note_id, new_parent_id, sibling_id, position
        )
        
        logger.info(f"Created note {note_id} at position")
        return {"id": note_id, "status": "created"}
    
    def create_sibling_note(self, reference_note_id: str, search_query: Optional[str] = None) -> dict:
        """Create a new note as a sibling after the reference note"""
        self._set_operation("create_new_sibling")
        assert self.client_id, "create_sibling_note requires client_id"
        self.expect_note_delta(1)
        
        # Get reference note to find its parent
        reference_note = LinkedListManager.get_note(self.db, reference_note_id)
        if not reference_note:
            raise HTTPException(status_code=404, detail=f"Reference note {reference_note_id} not found")
        
        # Create new note at top level first
        new_note_id = str(uuid.uuid4())
        LinkedListManager.create_note_top(self.db, new_note_id)
        
        # Then move it to be after the reference note
        LinkedListManager.move_note(
            self.db,
            note_id=new_note_id,
            new_parent_id=reference_note.parent_id,
            sibling_id=reference_note_id,
            position=MovePosition.AFTER
        )
        
        # Auto-populate with search terms if creating a root-level note during search
        if search_query and search_query.strip() and not reference_note.parent_id:
            content = f"<div> </div><div><br></div><div>/* {search_query.strip()} */</div>"
            LinkedListManager.update_note(self.db, new_note_id, content)
            logger.info(f"Auto-populated sibling note {new_note_id} with search terms: '{search_query.strip()}'")
        
        logger.info(f"Created sibling note {new_note_id} after {reference_note_id}")
        return {"id": new_note_id, "status": "created"}
    
    def create_child_note(self, parent_note_id: str) -> dict:
        """Create a new note as the first child of the parent note"""
        self._set_operation("create_new_child")
        assert self.client_id, "create_child_note requires client_id"
        self.expect_note_delta(1)
        
        # Validate parent exists
        parent_note = LinkedListManager.get_note(self.db, parent_note_id)
        if not parent_note:
            raise HTTPException(status_code=404, detail=f"Parent note {parent_note_id} not found")
        
        # Create new note as first child
        new_note_id = str(uuid.uuid4())
        LinkedListManager.create_note_top(self.db, new_note_id, parent_id=parent_note_id)
        
        logger.info(f"Created child note {new_note_id} under parent {parent_note_id}")
        return {"id": new_note_id, "status": "created"}
    
    def paste_note_as_sibling(self, source_note_id: str, target_note_id: str) -> dict:
        """Copy a note and paste it as a sibling after the target note"""
        self._set_operation("paste_sibling")
        assert self.client_id, "paste_note_as_sibling requires client_id"
        
        # Validate notes exist
        source_note = LinkedListManager.get_note(self.db, source_note_id)
        if not source_note:
            raise HTTPException(status_code=404, detail=f"Source note {source_note_id} not found")
            
        target_note = LinkedListManager.get_note(self.db, target_note_id)
        if not target_note:
            raise HTTPException(status_code=404, detail=f"Target note {target_note_id} not found")
        
        # Copy the source note tree
        subtree_total = count_subtree(self.db, source_note_id)
        self.expect_note_delta(subtree_total)
        new_note_id = copy_note(self.db, source_note_id, target_note.parent_id)
        
        # Move the copied tree to be after the target
        LinkedListManager.move_note(
            self.db,
            note_id=new_note_id,
            new_parent_id=target_note.parent_id,
            sibling_id=target_note_id,
            position=MovePosition.AFTER
        )
        
        logger.info(f"Pasted note {new_note_id} (copy of {source_note_id}) as sibling of {target_note_id}")
        return {"id": new_note_id, "status": "pasted"}
    
    def paste_note_as_child(self, source_note_id: str, target_note_id: str) -> dict:
        """Copy a note and paste it as the first child of the target note"""
        self._set_operation("paste_child")
        assert self.client_id, "paste_note_as_child requires client_id"
        
        # Validate notes exist
        source_note = LinkedListManager.get_note(self.db, source_note_id)
        if not source_note:
            raise HTTPException(status_code=404, detail=f"Source note {source_note_id} not found")
            
        target_note = LinkedListManager.get_note(self.db, target_note_id)
        if not target_note:
            raise HTTPException(status_code=404, detail=f"Target note {target_note_id} not found")
        
        # Copy the source note tree as child of target
        subtree_total = count_subtree(self.db, source_note_id)
        self.expect_note_delta(subtree_total)
        new_note_id = copy_note(self.db, source_note_id, target_note_id)
        
        logger.info(f"Pasted note {new_note_id} (copy of {source_note_id}) as child of {target_note_id}")
        return {"id": new_note_id, "status": "pasted"}
