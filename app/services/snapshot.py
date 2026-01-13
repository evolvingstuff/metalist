from __future__ import annotations

import hashlib
import json
from collections import defaultdict
import time
from typing import DefaultDict, Dict, List, Optional, Tuple, Set

from loguru import logger

from app.services.content_formatting import format_note_content_for_view
from app.services.note_store import store as note_store
from app.services.search_index import search_index
from app.services.search_query import parse_search_query
from app.services.sync import get_all_locks
from app.services.view_state import ViewState

# Windowing constants (tuned later)
ROOT_CHUNK_SIZE = 50
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
        if note_id not in root_index_map:
            continue
        window_end = max(window_end, root_index_map[note_id])
    if editing_note_id:
        # Expand to include the root containing the editing node
        # Find root id by walking parents in store
        current = note_store.get_note(editing_note_id)
        while current.parent_id:
            current = note_store.get_note(current.parent_id)
        editing_root_id = current.id
        if editing_root_id in root_index_map:
            window_end = max(window_end, root_index_map[editing_root_id])
    if seen_root_indices:
        highest_seen_index = max(seen_root_indices)
        while window_end < len(ordered_root_ids) - 1 and window_end - highest_seen_index <= ROOT_BUFFER_THRESHOLD:
            window_end = min(window_end + ROOT_CHUNK_SIZE, len(ordered_root_ids) - 1)
    if anchor_root_id:
        if anchor_root_id in root_index_map:
            anchor_index = root_index_map[anchor_root_id]
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
    client_known_note_ids: Optional[Set[str]],
    client_seen_root_ids: Optional[Set[str]],
    anchor_root_id: Optional[str],
) -> ViewState:
    t0 = time.perf_counter()
    structure: List[Dict[str, object]] = []
    payloads: Dict[str, Dict[str, object]] = {}
    children_by_parent: DefaultDict[Optional[str], List[str]] = defaultdict(list)
    hash_by_id: Dict[str, str] = {}

    search_active = False
    allowed_note_ids: Optional[Set[str]] = None
    search_root_ids_ordered: Optional[List[str]] = None
    search_root_count_total = 0

    force_uncollapsed_ids: Set[str] = set()

    if search is not None:
        if not isinstance(search, str):
            raise TypeError(f"search must be a string or null, got {type(search)}")
        parsed = parse_search_query(search)
        has_terms = False
        if len(parsed.required_tags) > 0:
            has_terms = True
        if len(parsed.forbidden_tags) > 0:
            has_terms = True
        if len(parsed.required_text) > 0:
            has_terms = True
        if len(parsed.forbidden_text) > 0:
            has_terms = True

        if has_terms:
            search_active = True
            positively_matched_note_ids = set(search_index.query_note_ids(search))
            search_allowed_note_ids = set(positively_matched_note_ids)

            def _include_ancestors(note_ids: Set[str], *, starting_ids: Set[str]) -> None:
                to_visit = list(starting_ids)
                while to_visit:
                    current_id = to_visit.pop()
                    if not note_store.has_note(current_id):
                        continue
                    parent_id = note_store.get_note(current_id).parent_id
                    if parent_id is None:
                        continue
                    if parent_id in note_ids:
                        continue
                    note_ids.add(parent_id)
                    to_visit.append(parent_id)

            def _include_descendants(note_ids: Set[str], *, starting_ids: Set[str]) -> None:
                to_visit = list(starting_ids)
                while to_visit:
                    current_id = to_visit.pop()
                    if not note_store.has_note(current_id):
                        continue
                    for child_id in note_store.get_children(current_id):
                        if child_id in note_ids:
                            continue
                        note_ids.add(child_id)
                        to_visit.append(child_id)

            excluded_note_ids: Set[str] = set()

            def _quote_text_term_for_query(phrase: str) -> str:
                if not isinstance(phrase, str):
                    raise TypeError(f"search phrase must be a string, got {type(phrase)}")

                if '"' not in phrase:
                    escaped = phrase.replace('\\', '\\\\')
                    return f'"{escaped}"'

                if "'" not in phrase:
                    escaped = phrase.replace('\\', '\\\\').replace("'", "\\'")
                    return f"'{escaped}'"

                escaped = phrase.replace('\\', '\\\\').replace('\"', '\\"')
                return f'"{escaped}"'

            for tag in parsed.forbidden_tags:
                excluded_note_ids.update(search_index.query_note_ids(tag))

            for phrase in parsed.forbidden_text:
                excluded_note_ids.update(search_index.query_note_ids(_quote_text_term_for_query(phrase)))

            _include_ancestors(search_allowed_note_ids, starting_ids=set(search_allowed_note_ids))
            _include_descendants(search_allowed_note_ids, starting_ids=set(positively_matched_note_ids))
            if excluded_note_ids:
                search_allowed_note_ids.difference_update(excluded_note_ids)

            ordered_root_ids = note_store.get_children(None)
            search_root_ids_ordered_for_count = [
                root_id for root_id in ordered_root_ids if root_id in search_allowed_note_ids
            ]
            search_root_count_total = len(search_root_ids_ordered_for_count)

            allowed_note_ids = set(search_allowed_note_ids)
            if editing_note_id:
                allowed_note_ids.add(editing_note_id)
                _include_ancestors(allowed_note_ids, starting_ids={editing_note_id})

            search_root_ids_ordered = [
                root_id for root_id in ordered_root_ids if root_id in allowed_note_ids
            ]

    # Determine root window
    ordered_root_ids = note_store.get_children(None)
    root_count_total = len(ordered_root_ids)
    if client_known_note_ids is None:
        client_known_note_ids = set()

    if editing_note_id is not None and note_store.has_note(editing_note_id):
        current = note_store.get_note(editing_note_id)
        while current.parent_id:
            force_uncollapsed_ids.add(current.parent_id)
            current = note_store.get_note(current.parent_id)

    if search_active:
        if search_root_ids_ordered is None:
            search_roots = []
        else:
            search_roots = search_root_ids_ordered
        root_index_map = {rid: idx for idx, rid in enumerate(search_roots)}
        seen_root_indices = {
            root_index_map[rid]
            for rid in (client_seen_root_ids if client_seen_root_ids is not None else set())
            if rid in root_index_map
        }

        window_end = _determine_root_window_end(
            search_roots,
            root_index_map,
            client_known_note_ids,
            seen_root_indices,
            editing_note_id,
            anchor_root_id,
        )
        if window_end >= 0:
            allowed_root_ids = set(search_roots[: window_end + 1])
        else:
            allowed_root_ids = set()
    else:
        root_index_map = {rid: idx for idx, rid in enumerate(ordered_root_ids)}
        seen_root_indices = {
            root_index_map[rid]
            for rid in (client_seen_root_ids if client_seen_root_ids is not None else set())
            if rid in root_index_map
        }
        window_end = _determine_root_window_end(
            ordered_root_ids,
            root_index_map,
            client_known_note_ids,
            seen_root_indices,
            editing_note_id,
            anchor_root_id,
        )
        if window_end >= 0:
            allowed_root_ids = set(ordered_root_ids[: window_end + 1])
        else:
            allowed_root_ids = set()

    def traverse(parent_id: Optional[str]) -> None:
        ids = note_store.get_children(parent_id)

        if parent_id is None:
            ids = [note_id for note_id in ids if note_id in allowed_root_ids]

        for idx, nid in enumerate(ids):
            is_search_redacted = (
                search_active
                and allowed_note_ids is not None
                and parent_id is not None
                and nid not in allowed_note_ids
            )
            children_by_parent[parent_id].append(nid)
            rec = note_store.get_note(nid)
            if idx > 0:
                prev_id = ids[idx - 1]
            else:
                prev_id = None
            if idx + 1 < len(ids):
                next_id = ids[idx + 1]
            else:
                next_id = None
            flags = {
                "isCollapsed": bool(rec.is_collapsed),
                "isEditing": bool(editing_note_id == rec.id),
                "memoryMode": False,
                "memorySelected": False,
                "searchRedacted": bool(is_search_redacted),
            }

            # If a descendant is being edited, force ancestors open so the editing note remains visible.
            if rec.id in force_uncollapsed_ids:
                flags["isCollapsed"] = False
            assert isinstance(rec.content, str)
            assert isinstance(rec.tags, str)

            is_editing = bool(flags["isEditing"])
            rendered_content = rec.content
            if not is_editing:
                rendered_content = format_note_content_for_view(
                    content_html=rec.content,
                    tags=rec.tags,
                )

            h = _compute_hash(rendered_content, rec.tags, flags, parent_id, prev_id, next_id)
            structure.append({
                "id": rec.id,
                "parentId": parent_id,
                "prevId": prev_id,
                "nextId": next_id,
                "hash": h,
            })
            payloads[rec.id] = {
                "content": rendered_content,
                "tags": rec.tags,
                "flags": flags,
                "hash": h,
            }
            hash_by_id[rec.id] = h
            if search_active:
                traverse(rec.id)
            elif rec.id in force_uncollapsed_ids:
                traverse(rec.id)
            elif not flags["isCollapsed"] or flags["isEditing"]:
                traverse(rec.id)

    traverse(None)
    visible_ids = {entry["id"] for entry in structure}
    locks: Dict[str, str] = {
        note_id: owner for note_id, owner in get_all_locks().items() if note_id in visible_ids
    }
    metadata = {
        "editingNoteId": editing_note_id,
        "search": search,
        "rootCountTotal": root_count_total,
        "searchRootCountTotal": search_root_count_total,
    }

    if search_active:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.bind(
            metrics={
                "elapsed_ms": elapsed_ms,
                "structure_count": len(structure),
                "payload_count": len(payloads),
                "root_count": len(children_by_parent[None]) if None in children_by_parent else 0,
            },
            query=search,
        ).info("notes.view_state.finish")

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
    client_known_note_ids: Optional[Set[str]],
    client_seen_root_ids: Optional[Set[str]],
    anchor_root_id: Optional[str],
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, str]]:
    state = build_view_state(
        editing_note_id=editing_note_id,
        search=search,
        client_known_note_ids=client_known_note_ids,
        client_seen_root_ids=client_seen_root_ids,
        anchor_root_id=anchor_root_id,
    )
    return state.structure, state.payloads, state.locks
