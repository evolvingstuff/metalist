"""In-memory snapshot of the note hierarchy.

The store is responsible for eagerly loading the note table at startup and
providing fast, read-only access to decrypted content plus linked-list
metadata that the rest of the application relies on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Dict, Iterable, List, Optional
from types import SimpleNamespace
import time

from app.db import connect_reader
from app.db.notes_sql import fetch_all_for_cache

from app.models.database import SafeSession
from app.services.content_cache import get_cached_content


@dataclass(frozen=True)
class NoteRecord:
    id: str
    parent_id: Optional[str]
    prev_id: Optional[str]
    next_id: Optional[str]
    is_collapsed: bool
    content: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class NoteStore:
    """Thread-safe, read-optimized cache of note metadata."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._note_map: Dict[str, NoteRecord] = {}
        self._children: Dict[Optional[str], List[str]] = {}
        self._loaded = False
        self._timing_enabled = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load_from_db(self, db: SafeSession | None) -> None:
        """Populate the store by reading all notes from the database once.

        When ``db`` is provided, we use its connection so uncommitted writes
        from the active transaction are visible (needed during paste flows).
        """

        with self._lock:
            fetch_start = time.perf_counter()
            if db is not None:
                rows = fetch_all_for_cache(db.connection())
            else:
                with connect_reader("note_store:load") as connection:
                    rows = fetch_all_for_cache(connection)

            if self._timing_enabled:
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
                if plaintext is None:
                    raise RuntimeError(
                        f"Cache missing plaintext for note {note.id}; store hydration failed"
                    )

                note_map[note.id] = NoteRecord(
                    id=note.id,
                    parent_id=note.parent_id,
                    prev_id=note.prev_id,
                    next_id=note.next_id,
                    is_collapsed=bool(getattr(note, "is_collapsed", False)),
                    content=plaintext,
                    created_at=getattr(note, "created_at", None),
                    updated_at=getattr(note, "updated_at", None),
                )

                processed += 1
                if self._timing_enabled and processed % 1000 == 0:
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

            if self._timing_enabled:
                total_elapsed = time.perf_counter() - loop_start
                print(
                    f"[startup] note_store hydration loop processed {processed} notes in {total_elapsed:.2f}s"
                )

    def snapshot(self) -> Dict[str, NoteRecord]:
        """Return a shallow copy of the current note map."""
        with self._lock:
            return dict(self._note_map)

    # Mutation helpers --------------------------------------------------------

    def add_note_from_db(self, note: SimpleNamespace, plaintext: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            self._note_map[note.id] = NoteRecord(
                id=note.id,
                parent_id=note.parent_id,
                prev_id=note.prev_id,
                next_id=note.next_id,
                is_collapsed=bool(getattr(note, "is_collapsed", False)),
                content=plaintext,
                created_at=getattr(note, "created_at", None),
                updated_at=getattr(note, "updated_at", None),
            )
            self._rebuild_indexes_locked()

    def update_note_from_db(self, note: SimpleNamespace, plaintext: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            if note.id not in self._note_map:
                return
            self._note_map[note.id] = NoteRecord(
                id=note.id,
                parent_id=note.parent_id,
                prev_id=note.prev_id,
                next_id=note.next_id,
                is_collapsed=bool(getattr(note, "is_collapsed", False)),
                content=plaintext,
                created_at=getattr(note, "created_at", None),
                updated_at=getattr(note, "updated_at", None),
            )
            self._rebuild_indexes_locked()

    def update_metadata_from_db(self, note: SimpleNamespace) -> None:
        if not self._loaded:
            return
        with self._lock:
            record = self._note_map.get(note.id)
            if not record:
                return
            self._note_map[note.id] = NoteRecord(
                id=note.id,
                parent_id=note.parent_id,
                prev_id=note.prev_id,
                next_id=note.next_id,
                is_collapsed=record.is_collapsed,
                content=record.content,
                created_at=getattr(note, "created_at", record.created_at),
                updated_at=getattr(note, "updated_at", record.updated_at),
            )
            self._rebuild_indexes_locked()

    def bulk_update_metadata(self, notes: Iterable[SimpleNamespace], *, rebuild: bool = True) -> None:
        """Apply pointer metadata for multiple notes without repeated rebuilds."""
        if not self._loaded:
            return

        payload = list(notes)
        if not payload:
            return

        with self._lock:
            for note in payload:
                record = self._note_map.get(note.id)
                if not record:
                    continue

                self._note_map[note.id] = NoteRecord(
                    id=record.id,
                    parent_id=getattr(note, "parent_id", record.parent_id),
                    prev_id=getattr(note, "prev_id", record.prev_id),
                    next_id=getattr(note, "next_id", record.next_id),
                    is_collapsed=record.is_collapsed,
                    content=record.content,
                    created_at=record.created_at,
                    updated_at=getattr(note, "updated_at", record.updated_at),
                )

            if rebuild:
                self._rebuild_indexes_locked()

    def remove_note(self, note_id: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            to_visit = [note_id]
            while to_visit:
                current = to_visit.pop()
                record = self._note_map.pop(current, None)
                if record:
                    to_visit.extend(self._children.get(current, []))
            self._rebuild_indexes_locked()

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
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            self._rebuild_indexes_locked()

    def _rebuild_indexes_locked(self) -> None:
        children: Dict[Optional[str], List[str]] = {}
        for record in self._note_map.values():
            children.setdefault(record.parent_id, []).append(record.id)

        for parent_id, ids in children.items():
            children[parent_id] = self._order_ids(ids)

        self._children = children

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
            return list(self._children.get(parent_id, []))

store = NoteStore()


__all__ = ["NoteStore", "NoteRecord", "store"]
