from typing import Optional
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.db.notes_sql import fetch_children_ordered, fetch_note, update_links
from app.models.database import SafeSession
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
            if sibling_id and position is None:
                raise ValueError("Position must be specified when sibling_id is provided")
            if position and not sibling_id:
                raise ValueError("Position cannot be specified without a sibling_id")
            if sibling_id == note_id:
                raise ValueError("Cannot move note relative to itself")

            with SafeSession.allow_reads("list_ops:move_note:target"):
                note_row = fetch_note(db.connection(), note_id)
            if not note_row:
                raise ValueError(f"Note {note_id} not found")

            note = SimpleNamespace(**note_row)
            if new_parent_id == note.parent_id and sibling_id is None:
                raise ValueError("Note is already at this position")

            old_prev_id = note.prev_id
            old_next_id = note.next_id

            def is_descendant(parent_id: str, potential_child_id: str) -> bool:
                with SafeSession.allow_reads("list_ops:is_descendant"):
                    current_row = fetch_note(db.connection(), potential_child_id)
                current = SimpleNamespace(**current_row) if current_row else None
                while current and current.parent_id:
                    if current.parent_id == parent_id:
                        return True
                    with SafeSession.allow_reads("list_ops:is_descendant:up"):
                        row = fetch_note(db.connection(), current.parent_id)
                    current = SimpleNamespace(**row) if row else None
                return False

            if new_parent_id and is_descendant(note_id, new_parent_id):
                raise ValueError("Cannot create circular parent-child relationship")
            if new_parent_id == note_id:
                raise ValueError("Cannot make a note its own parent")

            with SafeSession.allow_reads("list_ops:target_notes"):
                target_rows = fetch_children_ordered(db.connection(), new_parent_id)
            target_notes = [SimpleNamespace(**row) for row in target_rows]

            if old_prev_id:
                update_links(db.connection(), old_prev_id, next_id=old_next_id)
            if old_next_id:
                update_links(db.connection(), old_next_id, prev_id=old_prev_id)

            update_links(db.connection(), note_id, parent_id=new_parent_id, prev_id=None, next_id=None)

            if sibling_id is None:
                existing_head = next((n for n in target_notes if n.prev_id is None), None)
                if existing_head:
                    update_links(db.connection(), existing_head.id, prev_id=note_id)
                    update_links(db.connection(), note_id, next_id=existing_head.id)
                return

            with SafeSession.allow_reads("list_ops:sibling"):
                sibling_row = fetch_note(db.connection(), sibling_id)
            if not sibling_row:
                raise ValueError(f"Sibling note {sibling_id} not found")
            sibling = SimpleNamespace(**sibling_row)
            if sibling.parent_id != new_parent_id:
                raise ValueError("Sibling must have the same parent")

            if position == MovePosition.BEFORE:
                update_links(db.connection(), note_id, prev_id=sibling.prev_id, next_id=sibling_id)
                update_links(db.connection(), sibling_id, prev_id=note_id)
                if sibling.prev_id:
                    update_links(db.connection(), sibling.prev_id, next_id=note_id)
            else:
                update_links(db.connection(), note_id, prev_id=sibling_id, next_id=sibling.next_id)
                update_links(db.connection(), sibling_id, next_id=note_id)
                if sibling.next_id:
                    update_links(db.connection(), sibling.next_id, prev_id=note_id)
        except Exception as e:
            print(e)
            raise


def _move_note_with_store(db: Session, note_id: str, new_parent_id: Optional[str],
                          sibling_id: Optional[str], position: Optional[MovePosition]) -> None:
    try:
        record = note_store.get_note(note_id)
    except KeyError:
        with SafeSession.allow_reads("list_ops:reload_store"):
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

        record = note_store.get_note(current_id)

        update_links(
            db.connection(),
            current_id,
            parent_id=parent_id,
            prev_id=prev_id,
            next_id=next_id,
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
