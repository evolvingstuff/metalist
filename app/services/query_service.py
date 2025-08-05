from typing import Optional
from sqlalchemy.orm import Session
from mako.lookup import TemplateLookup
from pathlib import Path
import logging

from .base_service import BaseQueryService  
from ..models.linked_list import LinkedListManager
from ..render.note_renderer import build_note_tree
from ..core.config import VERSION
from .sync_state import get_all_locks

logger = logging.getLogger(__name__)


class NoteQueryService(BaseQueryService):
    """Service for read-only note operations"""
    
    def get_notes_fragment(self, editing_note_id: Optional[str] = None, search: Optional[str] = None, client_id: Optional[str] = None) -> str:
        """Get the HTML fragment for the notes list"""
        # Build the note tree with search filtering
        notes = build_note_tree(LinkedListManager, self.db, None, editing_note_id, search)
        
        # Get current note locks
        note_locks = get_all_locks()
        
        # Set up template lookup
        template_dir = Path(__file__).parent.parent / "templates"
        lookup = TemplateLookup(directories=[str(template_dir)])
        template = lookup.get_template('notes_list.html')
        
        html = template.render(notes=notes, version=VERSION, note_locks=note_locks, current_client_id=client_id)
        
        logger.debug(f"Generated notes fragment with editing_note_id={editing_note_id}, search={search}, client_id={client_id}, locks={note_locks}")
        return html