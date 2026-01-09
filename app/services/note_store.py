"""In-memory snapshot of the note hierarchy.

The store is responsible for eagerly loading the note table at startup and
providing fast, read-only access to decrypted content plus linked-list
metadata that the rest of the application relies on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Dict, Iterable, List, Optional, Sequence, Mapping
from types import SimpleNamespace
import time
import logging

from app.db.session import connect_reader
from app.db.notes_sql import fetch_all_for_cache

from app.models.database import SafeSession
from app.services.content_cache import get_cached_content, get_cached_tags


@dataclass(frozen=True)
class NoteRecord:
    id: str
    parent_id: Optional[str]
    prev_id: Optional[str]
    next_id: Optional[str]
    is_collapsed: bool
    content: str
    tags: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class NoteStore:
    """Thread-safe, read-optimized cache of note metadata."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._lock = RLock()
        self._note_map: Dict[str, NoteRecord] = {}
        self._links: Dict[Optional[str], Dict[str, Dict[str, Optional[str]]]] = {}
        self._heads: Dict[Optional[str], Optional[str]] = {}
        self._tails: Dict[Optional[str], Optional[str]] = {}
        self._loaded = False
        self._timing_enabled = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load_from_db(
        self,
        db: SafeSession | None,
        *,
        prefetched_rows: Optional[Sequence[Mapping[str, object]]] = None,
    ) -> None:
        """Populate the store by reading all notes from the database once.

        When ``db`` is provided, we use its connection so uncommitted writes
        from the active transaction are visible (needed during paste flows).
        """

        with self._lock:
            timing_enabled = self._timing_enabled and db is None

            if prefetched_rows is not None:
                rows = list(prefetched_rows)
                if timing_enabled:
                    print(
                        f"[startup] note_store reused {len(rows)} prefetched rows (no query)"
                    )
            else:
                fetch_start = time.perf_counter()
                if db is not None:
                    rows = list(fetch_all_for_cache(db.connection()))
                else:
                    with connect_reader("note_store:load") as connection:
                        rows = list(fetch_all_for_cache(connection))

                if timing_enabled:
                    fetch_duration = time.perf_counter() - fetch_start
                    print(
                        f"[startup] note_store query returned {len(rows)} rows in {fetch_duration:.2f}s"
                    )

            note_map: Dict[str, NoteRecord] = {}

            loop_start = time.perf_counter()
            processed = 0
            last_checkpoint = loop_start

            for row in rows:
                note = SimpleNamespace(**row)
                plaintext = get_cached_content(note.id)

                tags = get_cached_tags(note.id)

                note_map[note.id] = NoteRecord(
                    id=note.id,
                    parent_id=note.parent_id,
                    prev_id=note.prev_id,
                    next_id=note.next_id,
                    is_collapsed=bool(getattr(note, "is_collapsed", False)),
                    content=plaintext,
                    tags=tags,
                    created_at=getattr(note, "created_at", None),
                    updated_at=getattr(note, "updated_at", None),
                )

                processed += 1
                if timing_enabled and processed % 1000 == 0:
                    now = time.perf_counter()
                    batch_elapsed = now - last_checkpoint
                    total_elapsed = now - loop_start
                    print(
                        f"[startup] note_store hydrated {processed} notes | last 1000 in {batch_elapsed:.2f}s | total {total_elapsed:.2f}s"
                    )
                    last_checkpoint = now

            known_ids = set(note_map.keys())
            for record in note_map.values():
                if record.prev_id and record.prev_id not in known_ids:
                    raise RuntimeError(
                        f"Integrity failure: note {record.id} references prev_id {record.prev_id} that does not exist"
                    )
                if record.next_id and record.next_id not in known_ids:
                    raise RuntimeError(
                        f"Integrity failure: note {record.id} references next_id {record.next_id} that does not exist"
                    )
                if record.parent_id and record.parent_id not in known_ids:
                    raise RuntimeError(
                        f"Integrity failure: note {record.id} references parent_id {record.parent_id} that does not exist"
                    )

            self._note_map = note_map
            self._rebuild_indexes_locked()
            self._loaded = True

            if timing_enabled:
                total_elapsed = time.perf_counter() - loop_start
                print(
                    f"[startup] note_store hydration loop processed {processed} notes in {total_elapsed:.2f}s"
                )

    def snapshot(self) -> Dict[str, NoteRecord]:
        """Return a shallow copy of the current note map."""
        with self._lock:
            return dict(self._note_map)

    # Mutation helpers --------------------------------------------------------

    def add_note_from_db(self, note: SimpleNamespace, plaintext: str, tags: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            record = NoteRecord(
                id=note.id,
                parent_id=note.parent_id,
                prev_id=note.prev_id,
                next_id=note.next_id,
                is_collapsed=bool(getattr(note, "is_collapsed", False)),
                content=plaintext,
                tags=tags,
                created_at=getattr(note, "created_at", None),
                updated_at=getattr(note, "updated_at", None),
            )
            self._note_map[note.id] = record
            self._insert_link(record.parent_id, record.id, record.prev_id, record.next_id)

    def update_note_from_db(self, note: SimpleNamespace, plaintext: str, tags: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            current = self._note_map.get(note.id)
            if not current:
                return
            self._note_map[note.id] = NoteRecord(
                id=note.id,
                parent_id=current.parent_id,
                prev_id=current.prev_id,
                next_id=current.next_id,
                is_collapsed=current.is_collapsed,
                content=plaintext,
                tags=tags,
                created_at=getattr(note, "created_at", current.created_at),
                updated_at=getattr(note, "updated_at", current.updated_at),
            )

    def update_metadata_from_db(self, note: SimpleNamespace, *, rebuild: bool = True) -> None:
        if not self._loaded:
            return
        with self._lock:
            record = self._note_map.get(note.id)
            if not record:
                return
            if rebuild:
                updated = NoteRecord(
                    id=note.id,
                    parent_id=note.parent_id,
                    prev_id=note.prev_id,
                    next_id=note.next_id,
                    is_collapsed=record.is_collapsed,
                    content=record.content,
                    tags=record.tags,
                    created_at=getattr(note, "created_at", record.created_at),
                    updated_at=getattr(note, "updated_at", record.updated_at),
                )
                self._note_map[note.id] = updated
                self._rebuild_indexes_locked()
            else:
                self._remove_link(record.parent_id, record.id)
                updated = NoteRecord(
                    id=note.id,
                    parent_id=note.parent_id,
                    prev_id=note.prev_id,
                    next_id=note.next_id,
                    is_collapsed=record.is_collapsed,
                    content=record.content,
                    tags=record.tags,
                    created_at=getattr(note, "created_at", record.created_at),
                    updated_at=getattr(note, "updated_at", record.updated_at),
                )
                self._note_map[note.id] = updated
                self._insert_link(updated.parent_id, updated.id, updated.prev_id, updated.next_id)

    def bulk_update_metadata(self, notes: Iterable[SimpleNamespace], *, rebuild: bool = True) -> None:
        """Apply pointer metadata for multiple notes without repeated rebuilds."""
        if not self._loaded:
            return

        payload = list(notes)
        if not payload:
            return

        with self._lock:
            updates: List[tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]] = []

            for note in payload:
                record = self._note_map.get(note.id)
                if not record:
                    continue

                updated = NoteRecord(
                    id=record.id,
                    parent_id=getattr(note, "parent_id", record.parent_id),
                    prev_id=getattr(note, "prev_id", record.prev_id),
                    next_id=getattr(note, "next_id", record.next_id),
                    is_collapsed=record.is_collapsed,
                    content=record.content,
                    tags=record.tags,
                    created_at=record.created_at,
                    updated_at=getattr(note, "updated_at", record.updated_at),
                )

                self._note_map[note.id] = updated
                updates.append((
                    note.id,
                    record.parent_id,
                    updated.parent_id,
                    updated.prev_id,
                    updated.next_id,
                ))

            if rebuild:
                self._rebuild_indexes_locked()
            else:
                for note_id, old_parent, new_parent, new_prev, new_next in updates:
                    self._remove_link(old_parent, note_id)
                    self._insert_link(new_parent, note_id, new_prev, new_next)

    def remove_note(self, note_id: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            to_visit: List[str] = [note_id]
            removed: List[tuple[Optional[str], str]] = []

            while to_visit:
                current = to_visit.pop()
                record = self._note_map.pop(current, None)
                if not record:
                    continue

                removed.append((record.parent_id, record.id))

                child_links = self._links.get(current)
                if child_links:
                    to_visit.extend(child_links.keys())
                    self._links.pop(current, None)
                self._heads.pop(current, None)
                self._tails.pop(current, None)

            removed_ids = {node_id for _, node_id in removed}

            for parent_id, node_id in removed:
                if parent_id in removed_ids:
                    continue
                self._remove_link(parent_id, node_id)

    def set_collapsed(self, note_id: str, collapsed: bool) -> None:
        if not self._loaded:
            return
        with self._lock:
            record = self._note_map.get(note_id)
            if not record or record.is_collapsed == collapsed:
                return
            self._note_map[note_id] = NoteRecord(
                id=record.id,
                parent_id=record.parent_id,
                prev_id=record.prev_id,
                next_id=record.next_id,
                is_collapsed=collapsed,
                content=record.content,
                tags=record.tags,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            # Collapsing/expanding a note must not mutate list structure.
            # Rebuilding indexes here can reorder notes if neighbor pointers in
            # `_note_map` are stale (some mutation paths update `_links` without
            # rewriting every affected NoteRecord). That manifests as a newly
            # created "top" note jumping to the bottom after a collapse action.

    def _rebuild_indexes_locked(self) -> None:
        links: Dict[Optional[str], Dict[str, Dict[str, Optional[str]]]] = {}
        heads: Dict[Optional[str], Optional[str]] = {}
        tails: Dict[Optional[str], Optional[str]] = {}

        children: Dict[Optional[str], List[str]] = {}
        for record in self._note_map.values():
            children.setdefault(record.parent_id, []).append(record.id)

        for parent_id, ids in children.items():
            ordered = self._order_ids(ids)
            if not ordered:
                continue
            parent_links: Dict[str, Dict[str, Optional[str]]] = {}
            for index, note_id in enumerate(ordered):
                if index > 0:
                    prev_id = ordered[index - 1]
                else:
                    prev_id = None
                if index + 1 < len(ordered):
                    next_id = ordered[index + 1]
                else:
                    next_id = None
                parent_links[note_id] = {'prev': prev_id, 'next': next_id}
            links[parent_id] = parent_links
            heads[parent_id] = ordered[0]
            tails[parent_id] = ordered[-1]

        self._links = links
        self._heads = heads
        self._tails = tails

    def _ensure_parent_structures(self, parent_id: Optional[str]) -> Dict[str, Dict[str, Optional[str]]]:
        if parent_id not in self._links:
            self._links[parent_id] = {}
            self._heads[parent_id] = None
            self._tails[parent_id] = None
        return self._links[parent_id]

    def _update_record_links_locked(
        self,
        note_id: str,
        *,
        parent_id: Optional[str],
        prev_id: Optional[str],
        next_id: Optional[str],
    ) -> None:
        record = self._note_map.get(note_id)
        if not record:
            return

        if record.parent_id == parent_id and record.prev_id == prev_id and record.next_id == next_id:
            return

        self._note_map[note_id] = NoteRecord(
            id=record.id,
            parent_id=parent_id,
            prev_id=prev_id,
            next_id=next_id,
            is_collapsed=record.is_collapsed,
            content=record.content,
            tags=record.tags,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _assert_links_consistent_locked(self, parent_id: Optional[str], note_ids: Iterable[Optional[str]]) -> None:
        links = self._links.get(parent_id) or {}
        head = self._heads.get(parent_id)
        tail = self._tails.get(parent_id)

        for note_id in note_ids:
            if not note_id:
                continue

            link = links[note_id]
            if link is None:
                continue

            record = self._note_map.get(note_id)
            if record is None:
                raise RuntimeError(f"Integrity failure: {note_id} present in links but missing from note_map")

            expected_prev = link['prev']
            expected_next = link['next']

            if record.parent_id != parent_id:
                raise RuntimeError(
                    "Integrity failure: parent mismatch for "
                    f"{note_id}: record.parent_id={record.parent_id} links.parent_id={parent_id}"
                )
            if record.prev_id != expected_prev or record.next_id != expected_next:
                raise RuntimeError(
                    "Integrity failure: link mismatch for "
                    f"{note_id}: record prev/next={record.prev_id}/{record.next_id} "
                    f"links prev/next={expected_prev}/{expected_next}"
                )

            if expected_prev is None and head != note_id:
                raise RuntimeError(
                    f"Integrity failure: head mismatch for parent {parent_id}: expected head={note_id} actual head={head}"
                )
            if expected_next is None and tail != note_id:
                raise RuntimeError(
                    f"Integrity failure: tail mismatch for parent {parent_id}: expected tail={note_id} actual tail={tail}"
                )

            if expected_prev is not None:
                prev_link = links[expected_prev]
                if prev_link is None or prev_link.get('next') != note_id:
                    raise RuntimeError(
                        "Integrity failure: prev/next mismatch: "
                        f"prev={expected_prev} links.next={None if prev_link is None else prev_link.get('next')} expected {note_id}"
                    )
                prev_record = self._note_map.get(expected_prev)
                if prev_record is None or prev_record.next_id != note_id:
                    raise RuntimeError(
                        "Integrity failure: prev record mismatch: "
                        f"prev={expected_prev} record.next_id={None if prev_record is None else prev_record.next_id} expected {note_id}"
                    )

            if expected_next is not None:
                next_link = links[expected_next]
                if next_link is None or next_link.get('prev') != note_id:
                    raise RuntimeError(
                        "Integrity failure: next/prev mismatch: "
                        f"next={expected_next} links.prev={None if next_link is None else next_link.get('prev')} expected {note_id}"
                    )
                next_record = self._note_map.get(expected_next)
                if next_record is None or next_record.prev_id != note_id:
                    raise RuntimeError(
                        "Integrity failure: next record mismatch: "
                        f"next={expected_next} record.prev_id={None if next_record is None else next_record.prev_id} expected {note_id}"
                    )

    @staticmethod
    def _get_or_create_link(links: Dict[str, Dict[str, Optional[str]]], node_id: str) -> Dict[str, Optional[str]]:
        link = links[node_id]
        if link is None:
            link = {'prev': None, 'next': None}
            links[node_id] = link
        else:
            link.setdefault('prev', None)
            link.setdefault('next', None)
        return link

    def _insert_link(
        self,
        parent_id: Optional[str],
        note_id: str,
        prev_id: Optional[str],
        next_id: Optional[str],
    ) -> None:
        links = self._ensure_parent_structures(parent_id)

        if prev_id not in links:
            prev_id = None
        if next_id not in links:
            next_id = None

        if prev_id is None and next_id is None:
            prev_id = self._tails.get(parent_id)
            next_id = None

        if prev_id is not None:
            prev_link = self._get_or_create_link(links, prev_id)
            if next_id is None:
                next_id = prev_link.get('next')
            else:
                next_id = next_id
        if next_id is not None:
            next_link = self._get_or_create_link(links, next_id)
            if prev_id is None:
                prev_id = next_link.get('prev')
            else:
                prev_id = prev_id

        links[note_id] = {'prev': prev_id, 'next': next_id}

        if prev_id is not None:
            links[prev_id]['next'] = note_id
        else:
            self._heads[parent_id] = note_id

        if next_id is not None:
            links[next_id]['prev'] = note_id
        else:
            self._tails[parent_id] = note_id

        self._update_record_links_locked(note_id, parent_id=parent_id, prev_id=prev_id, next_id=next_id)
        if prev_id is not None:
            prev_link = links[prev_id]
            if not prev_link or prev_link.get('next') != note_id:
                raise RuntimeError(f"Integrity failure: insert did not update prev link for {prev_id}")
            self._update_record_links_locked(prev_id, parent_id=parent_id, prev_id=prev_link.get('prev'), next_id=note_id)
        if next_id is not None:
            next_link = links[next_id]
            if not next_link or next_link.get('prev') != note_id:
                raise RuntimeError(f"Integrity failure: insert did not update next link for {next_id}")
            self._update_record_links_locked(next_id, parent_id=parent_id, prev_id=note_id, next_id=next_link.get('next'))

        self._assert_links_consistent_locked(parent_id, [note_id, prev_id, next_id])

    def _remove_link(self, parent_id: Optional[str], note_id: str) -> None:
        links = self._links.get(parent_id)
        if not links:
            return

        link = links.pop(note_id, None)
        if not link:
            return

        prev_id = link['prev']
        next_id = link['next']

        if prev_id is not None and prev_id in links:
            links[prev_id]['next'] = next_id
        else:
            self._heads[parent_id] = next_id

        if next_id is not None and next_id in links:
            links[next_id]['prev'] = prev_id
        else:
            self._tails[parent_id] = prev_id

        if prev_id is not None:
            prev_link = links[prev_id]
            if prev_link is None:
                raise RuntimeError(f"Integrity failure: prev node {prev_id} missing during remove of {note_id}")
            self._update_record_links_locked(prev_id, parent_id=parent_id, prev_id=prev_link.get('prev'), next_id=next_id)
        if next_id is not None:
            next_link = links[next_id]
            if next_link is None:
                raise RuntimeError(f"Integrity failure: next node {next_id} missing during remove of {note_id}")
            self._update_record_links_locked(next_id, parent_id=parent_id, prev_id=prev_id, next_id=next_link.get('next'))

        self._assert_links_consistent_locked(parent_id, [prev_id, next_id, self._heads.get(parent_id), self._tails.get(parent_id)])

        if not links:
            self._links.pop(parent_id, None)
            self._heads.pop(parent_id, None)
            self._tails.pop(parent_id, None)

    def _order_ids(self, ids: List[str]) -> List[str]:
        if not ids:
            return []

        bucket = {note_id: self._note_map[note_id] for note_id in ids if note_id in self._note_map}
        if not bucket:
            return []

        head_candidates = [
            record for record in bucket.values()
            if not record.prev_id or record.prev_id not in bucket
        ]
        if not head_candidates:
            head_candidates = [min(bucket.values(), key=lambda rec: rec.id)]

        head = head_candidates[0]
        ordered: List[str] = []
        seen: set[str] = set()
        current = head

        while current and current.id not in seen:
            ordered.append(current.id)
            seen.add(current.id)
            next_id = current.next_id
            current = bucket.get(next_id)

        for note_id in ids:
            if note_id not in seen:
                ordered.append(note_id)

        return ordered

    # Accessors -----------------------------------------------------------------

    def get_note(self, note_id: str) -> NoteRecord:
        with self._lock:
            record = self._note_map.get(note_id)

        if record is None:
            raise KeyError(f"Note {note_id} not present in NoteStore")

        return record

    def get_children(self, parent_id: Optional[str]) -> List[str]:
        with self._lock:
            head = self._heads.get(parent_id)
            if head is None:
                return []
            links = self._links.get(parent_id)
            if not links:
                return []
            ordered: List[str] = []
            current = head
            visited = set()
            while current and current not in visited:
                ordered.append(current)
                visited.add(current)
                link = links[current]
                if link is None:
                    raise RuntimeError(
                        "Integrity failure: child list contains node missing from links: "
                        f"parent_id={parent_id} note_id={current}"
                    )
                current = link['next']
            return ordered

    # Debug helpers -----------------------------------------------------------

    def debug_validate_links(self, *note_ids: Optional[str]) -> None:
        if not note_ids:
            return

        with self._lock:
            for note_id in note_ids:
                if not note_id:
                    continue
                record = self._note_map.get(note_id)
                if not record:
                    continue

                if record.prev_id:
                    prev = self._note_map.get(record.prev_id)
                    if not prev:
                        raise RuntimeError(
                            f"Integrity failure: note {note_id} prev_id {record.prev_id} missing"
                        )
                    elif prev.next_id != record.id:
                        raise RuntimeError(
                            "Integrity failure: prev/next mismatch: "
                            f"prev {record.prev_id} next={prev.next_id} expected {record.id}"
                        )

                if record.next_id:
                    nxt = self._note_map.get(record.next_id)
                    if not nxt:
                        raise RuntimeError(
                            f"Integrity failure: note {note_id} next_id {record.next_id} missing"
                        )
                    elif nxt.prev_id != record.id:
                        raise RuntimeError(
                            "Integrity failure: next/prev mismatch: "
                            f"next {record.next_id} prev={nxt.prev_id} expected {record.id}"
                        )

                if record.parent_id is not None:
                    children = self.get_children(record.parent_id)
                    if record.id not in children:
                        raise RuntimeError(
                            "Integrity failure: parent/child mismatch: "
                            f"note {note_id} parent {record.parent_id} missing from children list"
                        )

store = NoteStore()


__all__ = ["NoteStore", "NoteRecord", "store"]
