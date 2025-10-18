from typing import Optional, Iterable
from types import SimpleNamespace
from datetime import datetime, timezone

from sqlalchemy import update as sa_update, delete as sa_delete
from sqlalchemy.orm import Session

from .database import DBNote
from .enums import MovePosition
from ..utils.encryption import encrypt
from ..services.note_store import store as note_store


class NoteCRUD:
    """Handles CRUD operations for notes"""
    
    @staticmethod
    def create_note_top(db: Session, note_id: str, parent_id: Optional[str] = None) -> None:
        """Create a new note and insert it as the new head of the linked list"""
        try:
            if note_id is None:
                raise ValueError("Note ID must be specified")

            next_id = None
            if note_store.loaded:
                siblings = note_store.get_children(parent_id)
                next_id = siblings[0] if siblings else None
            else:
                first_note = db.query(DBNote).filter(
                    DBNote.prev_id.is_(None),
                    DBNote.parent_id == parent_id
                ).first()
                next_id = first_note.id if first_note else None

            plaintext = ""
            ciphertext, nonce, tag = encrypt(plaintext)
            db_note = DBNote(
                id=note_id,
                content=ciphertext,
                encryption_nonce=nonce,
                encryption_tag=tag,
                parent_id=parent_id,
                prev_id=None,
                next_id=next_id,
            )
            db.add(db_note)
            db.flush()

            from ..services.content_cache import cache_note
            cache_note(note_id, plaintext)

            if next_id:
                db.execute(
                    sa_update(DBNote)
                    .where(DBNote.id == next_id)
                    .values(prev_id=note_id)
                )

            if note_store.loaded:
                note_store.add_note_from_db(db_note, plaintext)
                if next_id:
                    sibling_record = note_store.get_note(next_id)
                    note_store.update_metadata_from_db(
                        SimpleNamespace(
                            id=next_id,
                            parent_id=sibling_record.parent_id,
                            prev_id=note_id,
                            next_id=sibling_record.next_id,
                            created_at=sibling_record.created_at,
                            updated_at=sibling_record.updated_at,
                            is_collapsed=sibling_record.is_collapsed,
                        )
                    )
        except Exception as e:
            print(e)
            raise

    @staticmethod
    def get_note(db: Session, note_id: str) -> DBNote:
        if note_store.loaded:
            try:
                record = note_store.get_note(note_id)
            except KeyError as exc:
                raise ValueError(f"Note with id {note_id} not found") from exc

            return SimpleNamespace(
                id=record.id,
                content=record.content,
                parent_id=record.parent_id,
                prev_id=record.prev_id,
                next_id=record.next_id,
                is_collapsed=record.is_collapsed,
                created_at=record.created_at,
                updated_at=record.updated_at,
                encryption_nonce=None,
                encryption_tag=None,
            )

        db_note = db.query(DBNote).filter(DBNote.id == note_id).first()
        if not db_note:
            raise ValueError(f"Note with id {note_id} not found")
        return db_note

    @staticmethod
    def update_note(db: Session, note_id: str, content: str):
        from ..services.content_cache import cache_note

        record = None
        if note_store.loaded:
            record = note_store.get_note(note_id)
        else:
            record = NoteCRUD.get_note(db, note_id)

        ciphertext, nonce, tag = encrypt(content)
        timestamp = datetime.now(timezone.utc)

        db.execute(
            sa_update(DBNote)
            .where(DBNote.id == note_id)
            .values(
                content=ciphertext,
                encryption_nonce=nonce,
                encryption_tag=tag,
                updated_at=timestamp,
            )
        )

        cache_note(note_id, content)

        if note_store.loaded:
            note_store.update_note_from_db(
                SimpleNamespace(
                    id=record.id,
                    parent_id=record.parent_id,
                    prev_id=record.prev_id,
                    next_id=record.next_id,
                    is_collapsed=record.is_collapsed,
                    created_at=record.created_at,
                    updated_at=timestamp,
                ),
                content,
            )

    @staticmethod
    def delete_note(db: Session, note_id: str) -> None:
        """Delete a note and ALL its descendants, updating surrounding links"""
        try:
            from ..services.content_cache import remove_cached_note

            if note_store.loaded:
                try:
                    record = note_store.get_note(note_id)
                except KeyError as exc:
                    raise ValueError(f"Note {note_id} not found") from exc

                ids_to_delete = _collect_descendants_from_store(note_id)

                if record.prev_id:
                    db.execute(
                        sa_update(DBNote)
                        .where(DBNote.id == record.prev_id)
                        .values(next_id=record.next_id)
                    )
                    prev_record = note_store.get_note(record.prev_id)
                    note_store.update_metadata_from_db(
                        SimpleNamespace(
                            id=prev_record.id,
                            parent_id=prev_record.parent_id,
                            prev_id=prev_record.prev_id,
                            next_id=record.next_id,
                            created_at=prev_record.created_at,
                            updated_at=prev_record.updated_at,
                            is_collapsed=prev_record.is_collapsed,
                        )
                    )

                if record.next_id:
                    db.execute(
                        sa_update(DBNote)
                        .where(DBNote.id == record.next_id)
                        .values(prev_id=record.prev_id)
                    )
                    next_record = note_store.get_note(record.next_id)
                    note_store.update_metadata_from_db(
                        SimpleNamespace(
                            id=next_record.id,
                            parent_id=next_record.parent_id,
                            prev_id=record.prev_id,
                            next_id=next_record.next_id,
                            created_at=next_record.created_at,
                            updated_at=next_record.updated_at,
                            is_collapsed=next_record.is_collapsed,
                        )
                    )

                db.execute(
                    sa_delete(DBNote).where(DBNote.id.in_(ids_to_delete))
                )

                for to_remove in ids_to_delete:
                    remove_cached_note(to_remove)

                note_store.remove_note(note_id)
                return

            note = db.get(DBNote, note_id)
            if not note:
                raise ValueError(f"Note {note_id} not found")

            def get_all_descendant_ids(parent_id: str) -> set[str]:
                descendants = set()
                children = db.query(DBNote).filter(DBNote.parent_id == parent_id).all()
                for child in children:
                    descendants.add(child.id)
                    descendants.update(get_all_descendant_ids(child.id))
                return descendants

            descendant_ids = get_all_descendant_ids(note_id)
            for descendant_id in descendant_ids:
                descendant = db.get(DBNote, descendant_id)
                db.delete(descendant)
                remove_cached_note(descendant_id)

            if note.prev_id:
                prev_note = db.get(DBNote, note.prev_id)
                prev_note.next_id = note.next_id
            if note.next_id:
                next_note = db.get(DBNote, note.next_id)
                next_note.prev_id = note.prev_id

            db.delete(note)
            remove_cached_note(note_id)
        except Exception as e:
            print(e)
            raise

    @staticmethod
    def create_note_drop(db: Session, note_id: str, new_parent_id: str = None, sibling_id: str = None, position: MovePosition = None):
        # First create the note at root level
        NoteCRUD.create_note_top(db, note_id)

        # TODO: possible to fail at next step but original update still made...
        
        # Then move it to the desired location (either under a parent or relative to siblings)
        # Import here to avoid circular dependency
        from .list_operations import ListOperations
        ListOperations.move_note(
            db=db,
            note_id=note_id,
            new_parent_id=new_parent_id,
            sibling_id=sibling_id,
            position=position
        )


def _collect_descendants_from_store(root_id: str) -> list[str]:
    stack = [root_id]
    result = []
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(note_store.get_children(current))
    return result
