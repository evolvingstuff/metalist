from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional, Tuple

from server_v2.store import store as note_store


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


def build_view_snapshot(*, editing_note_id: Optional[str], search: Optional[str]) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, str]]:
    structure: List[Dict[str, object]] = []
    payloads: Dict[str, Dict[str, object]] = {}

    def traverse(parent_id: Optional[str]) -> None:
        ids = note_store.children(parent_id)
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
