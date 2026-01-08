from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import DefaultDict, Dict, List, Optional, Tuple, Set

from app.services.note_store import store as note_store
from app.services.sync import get_all_locks
from app.services.view_state import ViewState

# Windowing constants (tuned later)
ROOT_CHUNK_SIZE = 100
ROOT_BUFFER_THRESHOLD = 25


def _compute_hash(
    content: str,
    tags: str,
    flags: Dict[str, object],
    parent_id: Optional[str],
    prev_id: Optional[str],
    next_id: Optional[str],
) -> str:
    flags_json = json.dumps(flags, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sha = hashlib.sha256()
    sha.update(content.encode("utf-8"))
    sha.update(b"|TAGS|")
    sha.update(tags.encode("utf-8"))
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
    anchor_root_id: Optional[str],
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
        # Find root id by walking parents in store
        current = note_store.get_note(editing_note_id)
        while current.parent_id:
            current = note_store.get_note(current.parent_id)
        editing_root_id = current.id
        index = root_index_map.get(editing_root_id)
        if index is not None:
            window_end = max(window_end, index)
    if seen_root_indices:
        highest_seen_index = max(seen_root_indices)
        while window_end < len(ordered_root_ids) - 1 and window_end - highest_seen_index <= ROOT_BUFFER_THRESHOLD:
            window_end = min(window_end + ROOT_CHUNK_SIZE, len(ordered_root_ids) - 1)
    if anchor_root_id:
        anchor_index = root_index_map.get(anchor_root_id)
        if anchor_index is not None:
            while (
                window_end < len(ordered_root_ids) - 1
                and window_end - anchor_index <= ROOT_BUFFER_THRESHOLD
            ):
                window_end = min(window_end + ROOT_CHUNK_SIZE, len(ordered_root_ids) - 1)
    return window_end


def build_view_state(
    *,
    editing_note_id: Optional[str],
    search: Optional[str],
    client_known_note_ids: Optional[Set[str]] = None,
    client_seen_root_ids: Optional[Set[str]] = None,
    anchor_root_id: Optional[str] = None,
) -> ViewState:
    structure: List[Dict[str, object]] = []
    payloads: Dict[str, Dict[str, object]] = {}
    children_by_parent: DefaultDict[Optional[str], List[str]] = defaultdict(list)
    hash_by_id: Dict[str, str] = {}

    search_term: Optional[str] = None
    if search:
        stripped = search.strip()
        if stripped:
            search_term = stripped.lower()

    allow_cache: Dict[str, bool] = {}

    def _should_include(nid: str) -> bool:
        if search_term is None:
            return True
        if nid in allow_cache:
            return allow_cache[nid]
        rec = note_store.get_note(nid)
        assert isinstance(rec.content, str)
        content = rec.content
        content_match = search_term in content.lower()
        child_match = any(_should_include(child) for child in note_store.get_children(nid))
        editing_match = bool(editing_note_id and nid == editing_note_id)
        result = content_match or child_match or editing_match
        allow_cache[nid] = result
        return result

    # Determine root window
    ordered_root_ids = note_store.get_children(None)
    root_index_map = {rid: idx for idx, rid in enumerate(ordered_root_ids)}
    client_known_note_ids = client_known_note_ids or set()
    seen_root_indices = {
        root_index_map[rid]
        for rid in (client_seen_root_ids or set())
        if rid in root_index_map
    }
    if search_term is not None:
        allowed_root_ids: Optional[Set[str]] = {
            rid for rid in ordered_root_ids if _should_include(rid)
        }
    else:
        window_end = _determine_root_window_end(
            ordered_root_ids,
            root_index_map,
            client_known_note_ids,
            seen_root_indices,
            editing_note_id,
            anchor_root_id,
        )
        allowed_root_ids = set(ordered_root_ids[: window_end + 1]) if window_end >= 0 else set()

    def traverse(parent_id: Optional[str]) -> None:
        ids = note_store.get_children(parent_id)
        # Apply root windowing at the top level
        if parent_id is None and allowed_root_ids is not None:
            ids = [i for i in ids if i in allowed_root_ids]
        for idx, nid in enumerate(ids):
            if not _should_include(nid):
                continue
            children_by_parent[parent_id].append(nid)
            rec = note_store.get_note(nid)
            prev_id = ids[idx - 1] if idx > 0 else None
            next_id = ids[idx + 1] if idx + 1 < len(ids) else None
            flags = {
                "isCollapsed": bool(rec.is_collapsed),
                "isEditing": bool(editing_note_id == rec.id),
                "memoryMode": False,
                "memorySelected": False,
            }
            assert isinstance(rec.content, str)
            assert isinstance(rec.tags, str)
            h = _compute_hash(rec.content, rec.tags, flags, parent_id, prev_id, next_id)
            structure.append({
                "id": rec.id,
                "parentId": parent_id,
                "prevId": prev_id,
                "nextId": next_id,
                "hash": h,
            })
            payloads[rec.id] = {
                "content": rec.content,
                "tags": rec.tags,
                "flags": flags,
                "hash": h,
            }
            hash_by_id[rec.id] = h
            if not flags["isCollapsed"] or flags["isEditing"] or search_term is not None:
                traverse(rec.id)

    traverse(None)
    visible_ids = {entry["id"] for entry in structure}
    locks: Dict[str, str] = {
        note_id: owner for note_id, owner in get_all_locks().items() if note_id in visible_ids
    }
    metadata = {
        "editingNoteId": editing_note_id,
        "search": search,
    }
    return ViewState(
        structure=structure,
        payloads=payloads,
        locks=locks,
        children_by_parent={key: value[:] for key, value in children_by_parent.items()},
        hash_by_id=hash_by_id,
        metadata=metadata,
    )


def build_view_snapshot(
    *,
    editing_note_id: Optional[str],
    search: Optional[str],
    client_known_note_ids: Optional[Set[str]] = None,
    client_seen_root_ids: Optional[Set[str]] = None,
    anchor_root_id: Optional[str] = None,
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, str]]:
    state = build_view_state(
        editing_note_id=editing_note_id,
        search=search,
        client_known_note_ids=client_known_note_ids,
        client_seen_root_ids=client_seen_root_ids,
        anchor_root_id=anchor_root_id,
    )
    return state.structure, state.payloads, state.locks
