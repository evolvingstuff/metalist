from typing import Dict, List, Optional, Set, Tuple
import hashlib
import json

from .base_service import BaseQueryService
from ..models.linked_list import LinkedListManager
from ..render.note_renderer import build_note_tree
from .sync_state import get_all_locks
from .note_store import store as note_store

ROOT_CHUNK_SIZE = 50
ROOT_BUFFER_THRESHOLD = 25


class NoteQueryService(BaseQueryService):
    """Service for read-only note operations."""

    def build_view_snapshot(
        self,
        editing_note_id: Optional[str] = None,
        search: Optional[str] = None,
        client_id: Optional[str] = None,
        client_known_note_ids: Optional[Set[str]] = None,
        client_seen_root_ids: Set[str] = frozenset(),
    ) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, str]]:
        """Produce structure entries and note payloads for differential updates."""

        client_known_note_ids = client_known_note_ids or set()
        client_seen_root_ids = set(client_seen_root_ids)

        search_active = bool(search and search.strip())

        notes: List[Dict[str, object]] = []
        if note_store.loaded:
            ordered_root_ids = note_store.get_children(None)
        else:
            notes = build_note_tree(LinkedListManager, self.db, None, editing_note_id, search)
            ordered_root_ids = [note['id'] for note in notes]

        root_index_map = {note_id: index for index, note_id in enumerate(ordered_root_ids)}

        seen_root_indices = {
            root_index_map[root_id]
            for root_id in client_seen_root_ids
            if root_id in root_index_map
        }

        window_end_index = self._determine_root_window_end(
            ordered_root_ids,
            root_index_map,
            client_known_note_ids,
            seen_root_indices,
            editing_note_id,
        )

        limit_roots: Optional[Set[str]] = None
        if not search_active:
            limit_roots = set(ordered_root_ids[: window_end_index + 1]) if window_end_index >= 0 else set()

        if note_store.loaded:
            notes = build_note_tree(
                LinkedListManager,
                self.db,
                None,
                editing_note_id,
                search,
                allowed_root_ids=limit_roots,
            )
        elif limit_roots is not None:
            notes = [note for note in notes if note['id'] in limit_roots]

        locks = get_all_locks()

        structure: List[Dict[str, object]] = []
        payloads: Dict[str, Dict[str, object]] = {}
        visited_note_ids: Set[str] = set()

        def traverse(nodes: List[dict], parent_id: Optional[str] = None) -> None:
            for index, note in enumerate(nodes):
                if parent_id is None and limit_roots is not None and note['id'] not in limit_roots:
                    continue
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
                visited_note_ids.add(note_id)

                children = note.get('children') or []
                should_include_children = (
                    not normalized_flags.get('isCollapsed', False)
                    or normalized_flags.get('isEditing', False)
                )
                if should_include_children:
                    traverse(children, note_id)

        traverse(notes, None)

        if visited_note_ids:
            locks = {note_id: owner for note_id, owner in locks.items() if note_id in visited_note_ids}
        else:
            locks = {}

        return structure, payloads, locks

    def _determine_root_window_end(
        self,
        ordered_root_ids: List[str],
        root_index_map: Dict[str, int],
        client_known_note_ids: Set[str],
        seen_root_indices: Set[int],
        editing_note_id: Optional[str],
    ) -> int:
        if not ordered_root_ids:
            return -1

        window_end = min(len(ordered_root_ids) - 1, ROOT_CHUNK_SIZE - 1)

        for note_id in client_known_note_ids:
            index = root_index_map.get(note_id)
            if index is not None:
                window_end = max(window_end, index)

        if editing_note_id:
            editing_root_id = _find_root_id(editing_note_id)
            if editing_root_id:
                index = root_index_map.get(editing_root_id)
                if index is not None:
                    window_end = max(window_end, index)

        highest_seen_index = max(seen_root_indices) if seen_root_indices else None

        if highest_seen_index is not None:
            while window_end < len(ordered_root_ids) - 1 and window_end - highest_seen_index <= ROOT_BUFFER_THRESHOLD:
                window_end = min(window_end + ROOT_CHUNK_SIZE, len(ordered_root_ids) - 1)

        return window_end


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


def _find_root_id(note_id: str) -> Optional[str]:
    try:
        record = note_store.get_note(note_id)
    except KeyError:
        return None

    current = record
    while current.parent_id:
        try:
            current = note_store.get_note(current.parent_id)
        except KeyError:
            return None
    return current.id
