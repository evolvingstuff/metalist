from typing import Dict, List, Optional, Tuple
from mako.lookup import TemplateLookup
from pathlib import Path
import logging
import hashlib
import json

from .base_service import BaseQueryService  
from ..models.linked_list import LinkedListManager
from ..render.note_renderer import build_note_tree
from ..core.config import VERSION
from .sync_state import get_all_locks

logger = logging.getLogger(__name__)


class NoteQueryService(BaseQueryService):
    """Service for read-only note operations"""
    
    def render_notes_view(self, editing_note_id: Optional[str] = None, search: Optional[str] = None, client_id: Optional[str] = None) -> str:
        """Render the HTML view for the notes list"""
        # Build the note tree with search filtering
        notes = build_note_tree(LinkedListManager, self.db, None, editing_note_id, search)
        
        # Get current note locks
        note_locks = get_all_locks()
        
        # Set up template lookup
        template_dir = Path(__file__).parent.parent / "templates"
        lookup = TemplateLookup(directories=[str(template_dir)])
        template = lookup.get_template('notes_list.html')
        
        html = template.render(notes=notes, version=VERSION, note_locks=note_locks, current_client_id=client_id, search_query=search)
        
        logger.debug(f"Rendered notes view with editing_note_id={editing_note_id}, search={search}, client_id={client_id}, locks={note_locks}")
        return html

    def build_view_snapshot(
        self,
        editing_note_id: Optional[str] = None,
        search: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Tuple[List[Tuple[str, Optional[str], Optional[str], Optional[str]]], Dict[str, Dict[str, object]], Dict[str, str]]:
        """Produce structure entries and note payloads for differential updates."""

        notes = build_note_tree(LinkedListManager, self.db, None, editing_note_id, search)
        locks = get_all_locks()

        structure: List[Tuple[str, Optional[str], Optional[str], Optional[str]]] = []
        payloads: Dict[str, Dict[str, object]] = {}

        def traverse(nodes: List[dict], parent_id: Optional[str] = None) -> None:
            for index, note in enumerate(nodes):
                note_id = note['id']
                prev_id = nodes[index - 1]['id'] if index > 0 else None
                next_id = nodes[index + 1]['id'] if index + 1 < len(nodes) else None

                structure.append((note_id, parent_id, prev_id, next_id))

                content = note.get('content') or ''
                flags = dict(note.get('flags') or {})
                hash_value = _compute_note_hash(content, flags)

                payloads[note_id] = {
                    'content': content,
                    'flags': flags,
                    'hash': hash_value,
                }

                children = note.get('children') or []
                traverse(children, note_id)

        traverse(notes, None)

        return structure, payloads, locks


def _compute_note_hash(content: str, flags: Dict[str, object]) -> str:
    """Hash note content together with its flag state to detect UI-impacting changes."""
    flags_json = json.dumps(flags, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    sha = hashlib.sha256()
    sha.update(content.encode('utf-8'))
    sha.update(b'|FLAGS|')
    sha.update(flags_json.encode('utf-8'))
    return sha.hexdigest()
