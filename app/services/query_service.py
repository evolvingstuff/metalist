from typing import Dict, List, Optional, Tuple
import hashlib
import json

from .base_service import BaseQueryService
from ..models.linked_list import LinkedListManager
from ..render.note_renderer import build_note_tree
from .sync_state import get_all_locks


class NoteQueryService(BaseQueryService):
    """Service for read-only note operations."""

    def build_view_snapshot(
        self,
        editing_note_id: Optional[str] = None,
        search: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, str]]:
        """Produce structure entries and note payloads for differential updates."""

        notes = build_note_tree(LinkedListManager, self.db, None, editing_note_id, search)
        locks = get_all_locks()

        structure: List[Dict[str, object]] = []
        payloads: Dict[str, Dict[str, object]] = {}

        def traverse(nodes: List[dict], parent_id: Optional[str] = None) -> None:
            for index, note in enumerate(nodes):
                note_id = note['id']
                prev_id = nodes[index - 1]['id'] if index > 0 else None
                next_id = nodes[index + 1]['id'] if index + 1 < len(nodes) else None

                content = note.get('content') or ''
                flags = dict(note.get('flags') or {})
                normalized_flags = _normalize_flags(flags)
                hash_value = _compute_note_hash(
                    content=content,
                    flags=normalized_flags,
                    parent_id=parent_id,
                    prev_id=prev_id,
                    next_id=next_id,
                )

                structure.append(
                    {
                        'id': note_id,
                        'parentId': parent_id,
                        'prevId': prev_id,
                        'nextId': next_id,
                        'hash': hash_value,
                    }
                )

                payloads[note_id] = {
                    'content': content,
                    'flags': normalized_flags,
                    'hash': hash_value,
                }

                children = note.get('children') or []
                traverse(children, note_id)

        traverse(notes, None)

        return structure, payloads, locks


def _compute_note_hash(
    content: str,
    flags: Dict[str, object],
    parent_id: Optional[str],
    prev_id: Optional[str],
    next_id: Optional[str],
) -> str:
    """Hash note content, flags, and sibling/parent relationships."""
    flags_json = json.dumps(flags, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    sha = hashlib.sha256()
    sha.update(content.encode('utf-8'))
    sha.update(b'|FLAGS|')
    sha.update(flags_json.encode('utf-8'))
    sha.update(b'|STRUCT|')
    struct_descriptor = [parent_id or '', prev_id or '', next_id or '']
    sha.update('::'.join(struct_descriptor).encode('utf-8'))
    return sha.hexdigest()


def _normalize_flags(flags: Dict[str, object]) -> Dict[str, object]:
    """Ensure expected boolean flags are present for hashing consistency."""
    normalized = dict(flags)
    normalized['isCollapsed'] = bool(flags.get('isCollapsed', False))
    normalized['isEditing'] = bool(flags.get('isEditing', False))
    normalized['memoryMode'] = bool(flags.get('memoryMode', False))
    normalized['memorySelected'] = bool(flags.get('memorySelected', False))
    return normalized
