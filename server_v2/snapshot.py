from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional, Tuple, Set

from server_v2.store import store as note_store

# Windowing constants (tuned later)
ROOT_CHUNK_SIZE = 100
ROOT_BUFFER_THRESHOLD = 25


def _compute_hash(content: str, flags: Dict[str, object], parent_id: Optional[str], prev_id: Optional[str], next_id: Optional[str]) -> str:
    flags_json = json.dumps(flags, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sha = hashlib.sha256()
    sha.update((content or "").encode("utf-8"))
    sha.update(b"|FLAGS|")
    sha.update(flags_json.encode("utf-8"))
    sha.update(b"|STRUCT|")
    parts = [parent_id or "", prev_id or "", next_id or ""]
    sha.update("::".join(parts).encode("utf-8"))
    return sha.hexdigest()


def _determine_root_window_end(
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
        # Expand to include the root containing the editing node
        try:
            # Find root id by walking parents in store
            current = note_store.get(editing_note_id)
            while current.parent_id:
                current = note_store.get(current.parent_id)
            editing_root_id = current.id
            index = root_index_map.get(editing_root_id)
            if index is not None:
                window_end = max(window_end, index)
        except Exception:
            pass
    if seen_root_indices:
        highest_seen_index = max(seen_root_indices)
        while window_end < len(ordered_root_ids) - 1 and window_end - highest_seen_index <= ROOT_BUFFER_THRESHOLD:
            window_end = min(window_end + ROOT_CHUNK_SIZE, len(ordered_root_ids) - 1)
    return window_end


def build_view_snapshot(
    *,
    editing_note_id: Optional[str],
    search: Optional[str],
    client_known_note_ids: Optional[Set[str]] = None,
    client_seen_root_ids: Optional[Set[str]] = None,
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, str]]:
    structure: List[Dict[str, object]] = []
    payloads: Dict[str, Dict[str, object]] = {}

    # Determine root window
    ordered_root_ids = note_store.children(None)
    root_index_map = {rid: idx for idx, rid in enumerate(ordered_root_ids)}
    client_known_note_ids = client_known_note_ids or set()
    seen_root_indices = {
        root_index_map[rid]
        for rid in (client_seen_root_ids or set())
        if rid in root_index_map
    }
    window_end = _determine_root_window_end(
        ordered_root_ids, root_index_map, client_known_note_ids, seen_root_indices, editing_note_id
    )
    allowed_root_ids: Optional[Set[str]] = set(ordered_root_ids[: window_end + 1]) if window_end >= 0 else set()

    def traverse(parent_id: Optional[str]) -> None:
        ids = note_store.children(parent_id)
        # Apply root windowing at the top level
        if parent_id is None and allowed_root_ids is not None:
            ids = [i for i in ids if i in allowed_root_ids]
        for idx, nid in enumerate(ids):
            rec = note_store.get(nid)
            prev_id = ids[idx - 1] if idx > 0 else None
            next_id = ids[idx + 1] if idx + 1 < len(ids) else None
            flags = {
                "isCollapsed": bool(rec.is_collapsed),
                "isEditing": bool(editing_note_id == rec.id),
                "memoryMode": False,
                "memorySelected": False,
            }
            h = _compute_hash(rec.content or "", flags, parent_id, prev_id, next_id)
            structure.append({
                "id": rec.id,
                "parentId": parent_id,
                "prevId": prev_id,
                "nextId": next_id,
                "hash": h,
            })
            payloads[rec.id] = {
                "content": rec.content or "",
                "flags": flags,
                "hash": h,
            }
            if not flags["isCollapsed"] or flags["isEditing"]:
                traverse(rec.id)

    traverse(None)
    locks: Dict[str, str] = {}
    return structure, payloads, locks
