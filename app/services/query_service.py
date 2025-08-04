from typing import Optional
from sqlalchemy.orm import Session
from mako.lookup import TemplateLookup
from pathlib import Path
import logging

from .base_service import BaseQueryService
from ..models.linked_list import LinkedListManager
from ..render.note_renderer import build_note_tree
from ..core.config import VERSION

logger = logging.getLogger(__name__)


class NoteQueryService(BaseQueryService):
    """Service for read-only note operations"""
    
    def get_notes_fragment(self, editing_note_id: Optional[str] = None) -> str:
        """Get the HTML fragment for the notes list"""
        # Build the note tree
        notes = build_note_tree(LinkedListManager, self.db, None, editing_note_id)
        
        # Set up template lookup
        template_dir = Path(__file__).parent.parent / "templates"
        lookup = TemplateLookup(directories=[str(template_dir)])
        template = lookup.get_template('notes_list.html')
        
        html = template.render(notes=notes, version=VERSION)
        
        logger.debug(f"Generated notes fragment with editing_note_id={editing_note_id}")
        return html