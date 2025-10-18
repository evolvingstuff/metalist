from typing import Optional
from types import SimpleNamespace

from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from .database import DBNote
from .enums import MovePosition
from ..services.note_store import store as note_store


class ListOperations:
    """Handles linked list manipulation operations"""
    
    @staticmethod
    def move_note(db: Session, note_id: str, new_parent_id: Optional[str] = None,
                  sibling_id: Optional[str] = None, position: Optional[MovePosition] = None):
        """Move a note to a new position"""
        try:
            if note_store.loaded:
                _move_note_with_store(db, note_id, new_parent_id, sibling_id, position)
                return

            # Fallback path when store is not available (legacy behavior)
            note = db.get(DBNote, note_id)
            if not note:
                raise ValueError(f"Note {note_id} not found")

            if sibling_id and position is None:
                raise ValueError("Position must be specified when sibling_id is provided")
            if position and not sibling_id:
                raise ValueError("Position cannot be specified without a sibling_id")
            if sibling_id == note_id:
                raise ValueError("Cannot move note relative to itself")
            if new_parent_id == note.parent_id and sibling_id is None:
                raise ValueError("Note is already at this position")

            old_prev_id = note.prev_id
            old_next_id = note.next_id

            def is_descendant(parent_id: str, potential_child_id: str) -> bool:
                current = db.get(DBNote, potential_child_id)
                while current and current.parent_id:
                    if current.parent_id == parent_id:
                        return True
                    current = db.get(DBNote, current.parent_id)
                return False

            if new_parent_id and is_descendant(note_id, new_parent_id):
                raise ValueError("Cannot create circular parent-child relationship")
            if new_parent_id == note_id:
                raise ValueError("Cannot make a note its own parent")

            target_notes = db.query(DBNote).filter(DBNote.parent_id == new_parent_id).all()

            if old_prev_id:
                prev_note = db.get(DBNote, old_prev_id)
                if prev_note:
                    prev_note.next_id = old_next_id
            if old_next_id:
                next_note = db.get(DBNote, old_next_id)
                if next_note:
                    next_note.prev_id = old_prev_id

            note.prev_id = None
            note.next_id = None
            note.parent_id = new_parent_id

            if sibling_id is None:
                existing_head = next((n for n in target_notes if n.prev_id is None), None)
                if existing_head:
                    existing_head.prev_id = note_id
                    note.next_id = existing_head.id
                return

            sibling = db.get(DBNote, sibling_id)
            if not sibling:
                raise ValueError(f"Sibling note {sibling_id} not found")
            if sibling.parent_id != new_parent_id:
                raise ValueError("Sibling must have the same parent")

            if position == MovePosition.BEFORE:
                note.next_id = sibling_id
                note.prev_id = sibling.prev_id
                sibling.prev_id = note_id
                if note.prev_id:
                    prev_note = db.get(DBNote, note.prev_id)
                    if prev_note:
                        prev_note.next_id = note_id
            else:
                note.prev_id = sibling_id
                note.next_id = sibling.next_id
                sibling.next_id = note_id
                if note.next_id:
                    next_note = db.get(DBNote, note.next_id)
                    if next_note:
                        next_note.prev_id = note_id
        except Exception as e:
            print(e)
            raise


def _move_note_with_store(db: Session, note_id: str, new_parent_id: Optional[str],
                          sibling_id: Optional[str], position: Optional[MovePosition]) -> None:
    try:
        record = note_store.get_note(note_id)
    except KeyError:
        note_store.load_from_db(db)
        record = note_store.get_note(note_id)

    if sibling_id and position is None:
        raise ValueError("Position must be specified when sibling_id is provided")
    if position and not sibling_id:
        raise ValueError("Position cannot be specified without a sibling_id")
    if sibling_id == note_id:
        raise ValueError("Cannot move note relative to itself")
    if new_parent_id == note_id:
        raise ValueError("Cannot make a note its own parent")

    if new_parent_id:
        descendants = _collect_descendants_from_store(note_id)[1:]
        if new_parent_id in descendants:
            raise ValueError("Cannot create circular parent-child relationship")

    old_parent = record.parent_id

    def build_order(parent_id: Optional[str]) -> list[str]:
        order = list(note_store.get_children(parent_id))
        return [nid for nid in order if nid != note_id]

    old_order = build_order(old_parent)

    if new_parent_id == old_parent:
        new_order = list(old_order)
    else:
        new_order = build_order(new_parent_id)

    if sibling_id is None:
        new_order.insert(0, note_id)
    else:
        if sibling_id not in new_order:
            raise ValueError(f"Sibling note {sibling_id} not found")
        index = new_order.index(sibling_id)
        if position == MovePosition.BEFORE:
            new_order.insert(index, note_id)
        else:
            new_order.insert(index + 1, note_id)

    if new_parent_id == old_parent:
        _apply_order_with_store(db, new_parent_id, new_order)
    else:
        _apply_order_with_store(db, old_parent, old_order)
        _apply_order_with_store(db, new_parent_id, new_order)


def _apply_order_with_store(db: Session, parent_id: Optional[str], order: list[str]) -> None:
    for index, current_id in enumerate(order):
        prev_id = order[index - 1] if index > 0 else None
        next_id = order[index + 1] if index < len(order) - 1 else None

        values = {
            'prev_id': prev_id,
            'next_id': next_id,
        }

        record = note_store.get_note(current_id)
        if record.parent_id != parent_id:
            values['parent_id'] = parent_id

        db.execute(
            sa_update(DBNote)
            .where(DBNote.id == current_id)
            .values(**values)
        )

        note_store.update_metadata_from_db(
            SimpleNamespace(
                id=record.id,
                parent_id=parent_id,
                prev_id=prev_id,
                next_id=next_id,
                created_at=record.created_at,
                updated_at=record.updated_at,
                is_collapsed=record.is_collapsed,
            )
        )


def _collect_descendants_from_store(root_id: str) -> list[str]:
    stack = [root_id]
    result = []
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(note_store.get_children(current))
    return result
