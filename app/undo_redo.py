import uuid
from dataclasses import dataclass
from typing import Dict, Iterable

from sqlalchemy.orm import Session

from app.db.notes_sql import (
    delete_notes,
    fetch_all_for_cache,
    insert_note,
    update_links,
    update_note_content,
)
from app.services import content_cache
from app.services.note_store import store as note_store
from app.utils.encryption import encrypt


@dataclass
class SnapshotRecord:
    id: str
    content: str
    parent_id: str | None
    prev_id: str | None
    next_id: str | None
    is_collapsed: bool
    created_at: object
    updated_at: object


def _state_differs(a: SnapshotRecord, b: SnapshotRecord) -> bool:
    return (
        a.content != b.content
        or a.parent_id != b.parent_id
        or a.prev_id != b.prev_id
        or a.next_id != b.next_id
        or a.is_collapsed != b.is_collapsed
    )


def _depth(note_id: str, state: Dict[str, SnapshotRecord]) -> int:
    depth = 0
    current = state.get(note_id)
    visited = set()
    while current and current.parent_id and current.parent_id not in visited:
        visited.add(current.parent_id)
        depth += 1
        current = state.get(current.parent_id)
    return depth


def _sorted_records(records: Iterable[SnapshotRecord], reference_state: Dict[str, SnapshotRecord]):
    combined = {record.id: record for record in records}

    def compute_depth(record: SnapshotRecord) -> int:
        depth = 0
        parent_id = record.parent_id
        visited = set()
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            if parent_id in combined:
                parent = combined[parent_id]
            else:
                parent = reference_state.get(parent_id)
            if not parent:
                break
            depth += 1
            parent_id = parent.parent_id
        return depth

    return sorted(records, key=compute_depth)


class Command:
    def __init__(self, pre_state: dict, post_state: dict, func_name: str):
        self.uuid = str(uuid.uuid4())
        self.pre_state = pre_state
        self.post_state = post_state
        self.func_name = func_name

    def __repr__(self):
        prestates = ', '.join(
            f"{k[:8]} content=\"{self.pre_state[k].content[:8]}\""
            for k in self.pre_state
        )
        poststates = ', '.join(
            f"{k[:8]} content=\"{self.post_state[k].content[:8]}\""
            for k in self.post_state
        )
        return (
            "Command:\n"
            f"\tpre_state:\n\t\t{prestates}\n"
            f"\tpost_state:\n\t\t{poststates}\n"
        )

    def undo(self, db: Session):
        # Revert to the pre_state
        self._apply_state(self.pre_state, self.post_state, db)

    def redo(self, db: Session):
        # Reapply the post_state
        self._apply_state(self.post_state, self.pre_state, db)

    def _apply_state(self, target_state, reference_state, db: Session):
        """Apply the target_state to the database."""

        for note in _sorted_records(target_state.values(), reference_state):
            reference_note = reference_state.get(note.id)
            if reference_note is None:
                self._create_note(note, db)
            elif _state_differs(reference_note, note):
                self._update_note(note, db)

        obsolete_ids = sorted(
            reference_state.keys() - target_state.keys(),
            key=lambda nid: _depth(nid, reference_state),
            reverse=True,
        )
        if obsolete_ids:
            delete_notes(db.connection(), obsolete_ids)
            for note_id in obsolete_ids:
                content_cache.remove_cached_note(note_id)

        note_store.load_from_db(db)

    def _create_note(self, note: SnapshotRecord, db: Session):
        ciphertext, nonce, tag = encrypt(note.content)
        insert_note(
            db.connection(),
            note_id=note.id,
            content=ciphertext,
            encryption_nonce=nonce,
            encryption_tag=tag,
            parent_id=note.parent_id,
            prev_id=note.prev_id,
            next_id=note.next_id,
            is_collapsed=note.is_collapsed,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )
        content_cache.cache_note(note.id, note.content)

    def _update_note(self, note: SnapshotRecord, db: Session):
        ciphertext, nonce, tag = encrypt(note.content)
        update_note_content(
            db.connection(),
            note.id,
            content=ciphertext,
            encryption_nonce=nonce,
            encryption_tag=tag,
            updated_at=note.updated_at,
        )
        update_links(
            db.connection(),
            note.id,
            parent_id=note.parent_id,
            prev_id=note.prev_id,
            next_id=note.next_id,
            is_collapsed=note.is_collapsed,
            updated_at=note.updated_at,
        )
        content_cache.cache_note(note.id, note.content)

class CommandStack:
    def __init__(self):
        self.stack = []
        self.current_index = -1

    def __repr__(self):
        result = "CommandStack:\n"
        result += "\tstack:\n"
        for command in self.stack:
            result += f"\t\t{command}\n"
        result += f"\tcurrent_index: {self.current_index}"
        return result

    def push(self, command):
        # Remove any commands after the current index
        self.stack = self.stack[:self.current_index + 1]
        self.stack.append(command)
        self.current_index += 1

    def undo(self, db: Session):
        if self.current_index >= 0:
            command = self.stack[self.current_index]
            print(f"🔧 COMMAND STACK: Undoing command at index {self.current_index}")
            command.undo(db)
            self.current_index -= 1
            print(f"🔧 COMMAND STACK: After undo, current_index = {self.current_index}")
        else:
            print("No command to undo")

    def redo(self, db: Session):
        if self.current_index < len(self.stack) - 1:
            self.current_index += 1
            command = self.stack[self.current_index]
            command.redo(db)
        else:
            print("No command to redo")

    def clear_all(self):
        self.stack = []
        self.current_index = -1

    def clear_after_current(self):
        """Clear commands after the current pointer."""
        if self.current_index < len(self.stack) - 1:
            self.stack = self.stack[:self.current_index + 1]
        else:
            print("No command to clear after current")
