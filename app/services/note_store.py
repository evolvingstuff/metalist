"""In-memory snapshot of the note hierarchy.

The store is responsible for eagerly loading the note table at startup and
providing fast, read-only access to decrypted content, ordering metadata, and
pre-rendered variants that future diff-based APIs can consume.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Dict, List, Optional
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.db import connect_reader
from app.db.notes_sql import fetch_all_for_cache

from app.models.database import DBNote
from app.services.content_cache import get_cached_content


@dataclass(frozen=True)
class NoteRenderVariants:
    collapsed_html: str
    expanded_html: str
    edit_html: str
    hash_collapsed: str
    hash_expanded: str
    hash_edit: str


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
    variants: NoteRenderVariants


class NoteStore:
    """Thread-safe, read-optimized cache of note metadata."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._note_map: Dict[str, NoteRecord] = {}
        self._children: Dict[Optional[str], List[str]] = {}
        self._hash_tree: Dict[str, str] = {}
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load_from_db(self, db: Session | None) -> None:
        """Populate the store by reading all notes from the database once.

        When ``db`` is provided, we use its connection so uncommitted writes
        from the active transaction are visible (needed during paste flows).
        """

        with self._lock:
            if db is not None:
                rows = fetch_all_for_cache(db.connection())
            else:
                with connect_reader("note_store:load") as connection:
                    rows = fetch_all_for_cache(connection)

            note_map: Dict[str, NoteRecord] = {}

            for row in rows:
                note = SimpleNamespace(**row)
                plaintext = get_cached_content(note.id)
                if plaintext is None:
                    raise RuntimeError(
                        f"Cache missing plaintext for note {note.id}; store hydration failed"
                    )

                variants = _build_render_variants(note, plaintext)
                note_map[note.id] = NoteRecord(
                    id=note.id,
                    parent_id=note.parent_id,
                    prev_id=note.prev_id,
                    next_id=note.next_id,
                    is_collapsed=bool(getattr(note, "is_collapsed", False)),
                    content=plaintext,
                    created_at=getattr(note, "created_at", None),
                    updated_at=getattr(note, "updated_at", None),
                    variants=variants,
                )

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

    def _compute_hash(
        self,
        note_id: str,
        note_map: Dict[str, NoteRecord],
        children: Dict[Optional[str], List[str]],
        hash_tree: Dict[str, str],
    ) -> str:
        if note_id in hash_tree:
            return hash_tree[note_id]

        record = note_map[note_id]
        child_ids = children.get(note_id, [])
        child_hashes = [self._compute_hash(child_id, note_map, children, hash_tree) for child_id in child_ids]

        sha = hashlib.sha256()
        sha.update(record.variants.hash_expanded.encode("utf-8"))
        for child_hash in child_hashes:
            sha.update(child_hash.encode("utf-8"))

        digest = sha.hexdigest()
        hash_tree[note_id] = digest
        return digest

    # Mutation helpers --------------------------------------------------------

    def add_note_from_db(self, note: DBNote, plaintext: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            variants = _build_render_variants(note, plaintext)
            self._note_map[note.id] = NoteRecord(
                id=note.id,
                parent_id=note.parent_id,
                prev_id=note.prev_id,
                next_id=note.next_id,
                is_collapsed=bool(getattr(note, "is_collapsed", False)),
                content=plaintext,
                created_at=getattr(note, "created_at", None),
                updated_at=getattr(note, "updated_at", None),
                variants=variants,
            )
            self._rebuild_indexes_locked()

    def update_note_from_db(self, note: DBNote, plaintext: str) -> None:
        if not self._loaded:
            return
        with self._lock:
            if note.id not in self._note_map:
                return
            variants = _build_render_variants(note, plaintext)
            self._note_map[note.id] = NoteRecord(
                id=note.id,
                parent_id=note.parent_id,
                prev_id=note.prev_id,
                next_id=note.next_id,
                is_collapsed=bool(getattr(note, "is_collapsed", False)),
                content=plaintext,
                created_at=getattr(note, "created_at", None),
                updated_at=getattr(note, "updated_at", None),
                variants=variants,
            )
            self._rebuild_indexes_locked()

    def update_metadata_from_db(self, note: DBNote) -> None:
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
                variants=record.variants,
            )
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
                variants=record.variants,
            )
            self._rebuild_indexes_locked()

    def _rebuild_indexes_locked(self) -> None:
        children: Dict[Optional[str], List[str]] = {}
        for record in self._note_map.values():
            children.setdefault(record.parent_id, []).append(record.id)

        for parent_id, ids in children.items():
            children[parent_id] = self._order_ids(ids)

        self._children = children

        hash_tree: Dict[str, str] = {}
        for note_id in self._note_map:
            self._compute_hash(note_id, self._note_map, self._children, hash_tree)
        self._hash_tree = hash_tree

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

    def get_hash(self, note_id: str) -> str:
        with self._lock:
            try:
                return self._hash_tree[note_id]
            except KeyError as exc:
                raise KeyError(f"Hash for note {note_id} not computed") from exc


def _build_render_variants(note: DBNote, plaintext: str) -> NoteRenderVariants:
    """Produce render variants and hashes for a single note."""

    from app.render import note_renderer

    class _Temp:
        def __init__(self, base: DBNote, content: str) -> None:
            self.id = base.id
            self.content = content
            self.parent_id = base.parent_id
            self.created_at = base.created_at
            self.updated_at = base.updated_at
            self.is_collapsed = getattr(base, "is_collapsed", False)

    temp = _Temp(note, plaintext)

    expanded_html = note_renderer.render_read_only_mode(temp)
    edit_html = note_renderer.render_editing_mode(temp)
    # For now collapsed representation reuses the read-only view; layout logic lives client-side.
    collapsed_html = expanded_html

    return NoteRenderVariants(
        collapsed_html=collapsed_html,
        expanded_html=expanded_html,
        edit_html=edit_html,
        hash_collapsed=_hash_text(collapsed_html),
        hash_expanded=_hash_text(expanded_html),
        hash_edit=_hash_text(edit_html),
    )


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


store = NoteStore()


__all__ = ["NoteStore", "NoteRecord", "NoteRenderVariants", "store"]
