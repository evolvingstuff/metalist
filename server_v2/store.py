from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Dict, List, Optional, Iterable, Mapping, Set


@dataclass(slots=True)
class NodeRecord:
    id: str
    parent_id: Optional[str]
    prev_id: Optional[str]
    next_id: Optional[str]
    is_collapsed: bool
    content: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._notes: Dict[str, NodeRecord] = {}
        self._links: Dict[Optional[str], Dict[str, Dict[str, Optional[str]]]] = {}
        self._heads: Dict[Optional[str], Optional[str]] = {}
        self._tails: Dict[Optional[str], Optional[str]] = {}
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def hydrate_from_rows(self, rows: Iterable[Mapping[str, object]], *, get_plaintext) -> None:
        with self._lock:
            self._notes.clear()
            self._links.clear()
            self._heads.clear()
            self._tails.clear()

            for row in rows:
                note_id = str(row["id"])  # crash if missing
                plaintext = get_plaintext(note_id, row)
                self._notes[note_id] = NodeRecord(
                    id=note_id,
                    parent_id=row.get("parent_id"),
                    prev_id=row.get("prev_id"),
                    next_id=row.get("next_id"),
                    is_collapsed=bool(row.get("is_collapsed", False)),
                    content=plaintext,
                    created_at=row.get("created_at"),
                    updated_at=row.get("updated_at"),
                )

            children: Dict[Optional[str], List[str]] = {}
            for rec in self._notes.values():
                children.setdefault(rec.parent_id, []).append(rec.id)

            for parent_id, ids in children.items():
                by_id = {i: self._notes[i] for i in ids}
                head = next((r for r in by_id.values() if not r.prev_id or r.prev_id not in by_id), None)
                if not head and ids:
                    head = by_id[ids[0]]
                ordered: List[str] = []
                seen: Set[str] = set()
                cur = head
                while cur and cur.id not in seen:
                    ordered.append(cur.id)
                    seen.add(cur.id)
                    cur = by_id.get(cur.next_id or "")
                for nid in ids:
                    if nid not in seen:
                        ordered.append(nid)

                links: Dict[str, Dict[str, Optional[str]]] = {}
                for idx, nid in enumerate(ordered):
                    prev_id = ordered[idx - 1] if idx > 0 else None
                    next_id = ordered[idx + 1] if idx + 1 < len(ordered) else None
                    links[nid] = {"prev": prev_id, "next": next_id}
                self._links[parent_id] = links
                self._heads[parent_id] = ordered[0] if ordered else None
                self._tails[parent_id] = ordered[-1] if ordered else None

            self._loaded = True

    def get(self, note_id: str) -> NodeRecord:
        rec = self._notes.get(note_id)
        if rec is None:
            raise KeyError(f"Note {note_id} not present in v2 store")
        return rec

    def children(self, parent_id: Optional[str]) -> List[str]:
        head = self._heads.get(parent_id)
        if head is None:
            return []
        links = self._links.get(parent_id) or {}
        ordered: List[str] = []
        cur = head
        visited: Set[str] = set()
        while cur and cur not in visited:
            ordered.append(cur)
            visited.add(cur)
            cur = links.get(cur, {}).get("next")
        return ordered


store = InMemoryStore()


def hydrate_from_prefetched(rows: Iterable[Mapping[str, object]], *, get_plaintext) -> None:
    store.hydrate_from_rows(rows, get_plaintext=get_plaintext)

