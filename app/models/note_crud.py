from typing import Optional
from sqlalchemy.orm import Session
from .database import DBNote
from .enums import MovePosition
from ..utils.encryption import encrypt


class NoteCRUD:
    """Handles CRUD operations for notes"""
    
    @staticmethod
    def create_note_top(db: Session, note_id: str, parent_id: Optional[str] = None) -> None:
        """Create a new note and insert it as the new head of the linked list"""
        try:
            if note_id is None:
                raise ValueError("Note ID must be specified")

            # Get the first note at this level to determine position
            first_note = db.query(DBNote).filter(
                DBNote.prev_id == None, 
                DBNote.parent_id == parent_id
            ).first()

            # Create new note with both linked list and position fields
            db_note = DBNote(
                id=note_id,
                content=encrypt(""),  # Encrypt empty content
                parent_id=parent_id
            )
            db.add(db_note)

            # Update linked list pointers if there's an existing head
            if first_note and first_note.id != note_id:
                first_note.prev_id = note_id
                db_note.next_id = first_note.id

            db.flush()
        except Exception as e:
            print(e)
            raise

    @staticmethod
    def get_note(db: Session, note_id: str) -> DBNote:
        db_note = db.query(DBNote).filter(DBNote.id == note_id).first()
        if not db_note:
            raise ValueError(f"Note with id {note_id} not found")
        return db_note

    @staticmethod
    def update_note(db: Session, note_id: str, content: str):
        db_note = NoteCRUD.get_note(db, note_id)
        db_note.content = encrypt(content)  # Encrypt content before saving

    @staticmethod
    def delete_note(db: Session, note_id: str) -> None:
        """Delete a note and ALL its descendants, updating surrounding links"""
        try:
            note = db.get(DBNote, note_id)
            if not note:
                raise ValueError(f"Note {note_id} not found")

            def get_all_descendant_ids(parent_id: str) -> set[str]:
                """Recursively get IDs of all descendants"""
                descendants = set()
                children = db.query(DBNote).filter(DBNote.parent_id == parent_id).all()
                for child in children:
                    descendants.add(child.id)
                    descendants.update(get_all_descendant_ids(child.id))
                return descendants

            # Delete all descendants first
            descendant_ids = get_all_descendant_ids(note_id)
            for descendant_id in descendant_ids:
                descendant = db.get(DBNote, descendant_id)
                db.delete(descendant)

            # Update links of surrounding notes at the original note's level
            if note.prev_id:
                prev_note = db.get(DBNote, note.prev_id)
                prev_note.next_id = note.next_id
            if note.next_id:
                next_note = db.get(DBNote, note.next_id)
                next_note.prev_id = note.prev_id

            # Delete the original note
            db.delete(note)
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