from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from app.services.note_store import store as note_store
from app.utils.text_utils import strip_html


SORT_MODE_NORMAL = "normal"
SORT_MODE_CREATED = "created"
SORT_MODE_UPDATED = "updated"
SORT_MODE_ALPHABETICAL = "alphabetical"
SORT_MODES = frozenset({SORT_MODE_NORMAL, SORT_MODE_CREATED, SORT_MODE_UPDATED, SORT_MODE_ALPHABETICAL})
TIMESTAMP_SORT_MODES = frozenset({SORT_MODE_CREATED, SORT_MODE_UPDATED})


def normalize_sort_mode(sort_mode: object) -> str:
    if not isinstance(sort_mode, str):
        raise TypeError(f"sort_mode must be a string, got {type(sort_mode)}")
    normalized = sort_mode.strip().lower()
    if normalized not in SORT_MODES:
        raise ValueError(f"Unsupported sort mode: {sort_mode!r}")
    return normalized


def is_root_reorder_locked(sort_mode: object) -> bool:
    return normalize_sort_mode(sort_mode) != SORT_MODE_NORMAL


def is_timestamp_sort_mode(sort_mode: object) -> bool:
    return normalize_sort_mode(sort_mode) in TIMESTAMP_SORT_MODES


def _get_note_timestamp(note_id: str, sort_mode: str) -> datetime:
    record = note_store.get_note(note_id)
    if sort_mode == SORT_MODE_CREATED:
        timestamp = record.created_at
        field_name = "created_at"
    elif sort_mode == SORT_MODE_UPDATED:
        timestamp = record.updated_at
        field_name = "updated_at"
    else:
        raise ValueError(f"Timestamp lookup unsupported for sort mode {sort_mode!r}")

    if not isinstance(timestamp, datetime):
        raise RuntimeError(
            f"Root note {note_id} is missing required {field_name} for sort mode {sort_mode}"
        )
    return timestamp


def _get_root_subtree_timestamp(root_id: str, sort_mode: str) -> datetime:
    stack = [root_id]
    newest_timestamp: Optional[datetime] = None

    while stack:
        note_id = stack.pop()
        timestamp = _get_note_timestamp(note_id, sort_mode)
        if newest_timestamp is None or timestamp > newest_timestamp:
            newest_timestamp = timestamp
        children = note_store.get_children(note_id)
        if children:
            stack.extend(children)

    if newest_timestamp is None:
        raise RuntimeError(f"Root subtree {root_id} is missing timestamps for sort mode {sort_mode!r}")
    return newest_timestamp


def _get_root_content_sort_key(note_id: str) -> tuple[str, str, int]:
    record = note_store.get_note(note_id)
    if not isinstance(record.content, str):
        raise RuntimeError(f"Root note {note_id} is missing string content for alphabetical sort")
    text_content = strip_html(record.content).strip()
    return text_content.casefold(), text_content, len(text_content)


def get_root_sort_timestamps(sort_mode: object) -> Dict[str, datetime]:
    normalized = normalize_sort_mode(sort_mode)
    canonical_root_ids = note_store.get_children(None)
    if normalized not in TIMESTAMP_SORT_MODES:
        return {}

    root_timestamps: Dict[str, datetime] = {}
    for root_id in canonical_root_ids:
        root_timestamps[root_id] = _get_root_subtree_timestamp(root_id, normalized)
    return root_timestamps


def get_root_ids_for_sort_mode(
    sort_mode: object,
    *,
    root_timestamps: Dict[str, datetime],
) -> List[str]:
    normalized = normalize_sort_mode(sort_mode)
    canonical_root_ids = note_store.get_children(None)
    if normalized == SORT_MODE_NORMAL:
        return canonical_root_ids
    if normalized == SORT_MODE_ALPHABETICAL:
        decorated_alpha = []
        for canonical_index, root_id in enumerate(canonical_root_ids):
            content_key = _get_root_content_sort_key(root_id)
            decorated_alpha.append((root_id, content_key, canonical_index))
        decorated_alpha.sort(key=lambda item: (item[1], item[2]))
        return [root_id for root_id, _, _ in decorated_alpha]

    decorated = []
    for canonical_index, root_id in enumerate(canonical_root_ids):
        if root_id not in root_timestamps:
            raise RuntimeError(f"Missing root sort timestamp for {root_id}")
        timestamp = root_timestamps[root_id]
        decorated.append((root_id, timestamp, canonical_index))

    decorated.sort(key=lambda item: (-item[1].timestamp(), item[2]))
    return [root_id for root_id, _, _ in decorated]


def build_root_sort_buckets(
    root_ids: List[str],
    sort_mode: object,
    *,
    root_timestamps: Dict[str, datetime],
) -> Dict[str, Dict[str, str]]:
    normalized = normalize_sort_mode(sort_mode)
    if normalized not in TIMESTAMP_SORT_MODES:
        return {}

    buckets: Dict[str, Dict[str, str]] = {}
    for root_id in root_ids:
        if root_id not in root_timestamps:
            raise RuntimeError(f"Missing root sort timestamp for {root_id}")
        timestamp = root_timestamps[root_id].astimezone()
        buckets[root_id] = {
            "key": timestamp.strftime("%Y-%m-%d"),
            "label": timestamp.strftime("%Y/%m/%d - %A"),
        }
    return buckets
