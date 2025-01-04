from typing import List, Optional, Any
from sqlalchemy.orm import Session
from .enums import MovePosition
from .database import DBNote
from ..global_state_mod import global_state
from .position import Position


class LinkedListManager:
    """Position-based implementation of the note manager.
    Uses fractional indexing for ordering and integer indentation for hierarchy.
    Parent-child relationships are inferred from position and indent level."""

    @staticmethod
    def get_parent(db: Session, note: DBNote) -> Optional[DBNote]:
        """Find the parent of a note based on position and indent level"""
        if note.indent == 0:
            return None
        
        # Parent must be the last note that:
        # 1. Has indent level = note's indent - 1
        # 2. Comes before this note's position
        return db.query(DBNote).filter(
            DBNote.indent == note.indent - 1,
            DBNote.position < note.position
        ).order_by(DBNote.position.desc()).first()

    @staticmethod
    def get_children(db: Session, note: DBNote) -> List[DBNote]:
        """Find all direct children of a note based on position and indent level"""
        # Find the next note at the same indent level OR LOWER
        next_bound = db.query(DBNote).filter(
            DBNote.indent <= note.indent,
            DBNote.position > note.position
        ).order_by(DBNote.position).first()

        # Children are all notes that:
        # 1. Have indent level = parent's indent + 1
        # 2. Come after parent's position
        # 3. Come before next bounding note's position (if any)
        query = db.query(DBNote).filter(
            DBNote.indent == note.indent + 1,
            DBNote.position > note.position
        )
        
        if next_bound:
            query = query.filter(DBNote.position < next_bound.position)
            
        return query.order_by(DBNote.position).all()

    @staticmethod
    def validate_list(db: Session, root_level: bool = True) -> bool:
        """Validate the position-based structure"""
        db.expire_all()
        notes = db.query(DBNote).order_by(DBNote.position).all()
        
        if not notes:
            return True

        for note in notes:
            db.refresh(note)

        # Verify positions are strictly increasing
        for i in range(len(notes) - 1):
            if notes[i].position >= notes[i + 1].position:
                return False

        # Verify indent levels are valid
        for note in notes:
            # Root notes must have indent 0
            if note.indent == 0:
                continue
                
            # Find parent based on position and indent
            parent = LinkedListManager.get_parent(db, note)
            if not parent:
                return False
            
            # Parent must have indent level exactly one less
            if parent.indent != note.indent - 1:
                return False

        return True

    @staticmethod
    def get_ordered_child_list(db: Session, parent_note: Optional[DBNote] = None) -> List[Any]:
        """Get an ordered list of child notes"""
        if parent_note is None:
            # Return root level notes (indent = 0)
            return db.query(DBNote).filter(
                DBNote.indent == 0
            ).order_by(DBNote.position).all()
        
        return LinkedListManager.get_children(db, parent_note)

    @staticmethod
    def create_note_top(db: Session, note_id: str, parent_note: Optional[DBNote] = None) -> None:
        """Create a new note and insert it at the top of its level"""
        try:
            if note_id is None:
                raise ValueError("Note ID must be specified")

            # Calculate indent level
            indent_level = 0 if parent_note is None else parent_note.indent + 1

            # Find insertion position
            if parent_note:
                # Insert as first child - position between parent and its next sibling
                next_sibling = db.query(DBNote).filter(
                    DBNote.indent == parent_note.indent,
                    DBNote.position > parent_note.position
                ).order_by(DBNote.position).first()
                
                position_str = Position.get_position_between(
                    parent_note.position,
                    next_sibling.position if next_sibling else None
                )
            else:
                # Insert at root level
                first_root = db.query(DBNote).filter(
                    DBNote.indent == 0
                ).order_by(DBNote.position).first()
                
                position_str = Position.get_position_between(
                    None,
                    first_root.position if first_root else None
                )

            # Create new note
            db_note = DBNote(
                id=note_id,
                content="",
                position=position_str,
                indent=indent_level
            )
            db.add(db_note)
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
        db_note = LinkedListManager.get_note(db, note_id)
        db_note.content = content

    @staticmethod
    def delete_note(db: Session, note_id: str) -> None:
        """Delete a note and ALL its descendants"""
        try:
            note = db.get(DBNote, note_id)
            if not note:
                raise ValueError(f"Note {note_id} not found")

            # Find all descendants based on position and indent
            next_sibling = db.query(DBNote).filter(
                DBNote.indent == note.indent,
                DBNote.position > note.position
            ).order_by(DBNote.position).first()

            # Delete all notes that:
            # 1. Come after this note
            # 2. Have higher indent level
            # 3. Come before next sibling (if any)
            descendants_query = db.query(DBNote).filter(
                DBNote.position > note.position,
                DBNote.indent > note.indent
            )
            
            if next_sibling:
                descendants_query = descendants_query.filter(
                    DBNote.position < next_sibling.position
                )

            # Delete descendants first
            for descendant in descendants_query.all():
                db.delete(descendant)

            # Delete the original note
            db.delete(note)
            db.flush()
            
        except Exception as e:
            print(e)
            raise

    @staticmethod
    def create_note_drop(db: Session, note_id: str, target_note: Optional[DBNote] = None, 
                        sibling_id: Optional[str] = None, position: Optional[MovePosition] = None):
        # First create the note at root level
        LinkedListManager.create_note_top(db, note_id)
        
        # Then move it to the desired location
        LinkedListManager.move_note(
            db=db,
            note_id=note_id,
            target_note=target_note,
            sibling_id=sibling_id,
            position=position
        )

    @staticmethod
    def move_note(db: Session, note_id: str, target_note: Optional[DBNote] = None,
                  sibling_id: Optional[str] = None, position: Optional[MovePosition] = None):
        """Move a note to a new position"""
        try:
            print(f"DEBUG: Moving note {note_id} to target_note={target_note}, sibling_id={sibling_id}, position={position}")
            
            note = db.get(DBNote, note_id)
            if not note:
                raise ValueError(f"Note {note_id} not found")

            # Validate position parameters
            if sibling_id and position is None:
                raise ValueError("Position must be specified when sibling_id is provided")
            if position and not sibling_id:
                raise ValueError("Position cannot be specified without a sibling_id")

            # Prevent moving a note to itself
            if sibling_id == note_id:
                raise ValueError("Cannot move note relative to itself")

            # Calculate new indent level
            new_indent = 0 if target_note is None else target_note.indent + 1

            # Calculate new position
            if sibling_id is None:
                if target_note:
                    # Moving as first child of target
                    next_sibling = db.query(DBNote).filter(
                        DBNote.indent == target_note.indent,
                        DBNote.position > target_note.position
                    ).order_by(DBNote.position).first()
                    
                    new_position = Position.get_position_between(
                        target_note.position,
                        next_sibling.position if next_sibling else None
                    )
                else:
                    # Moving to root level
                    first_root = db.query(DBNote).filter(
                        DBNote.indent == 0
                    ).order_by(DBNote.position).first()
                    
                    new_position = Position.get_position_between(
                        None,
                        first_root.position if first_root else None
                    )
            else:
                # Moving relative to a sibling
                sibling = db.get(DBNote, sibling_id)
                if not sibling:
                    raise ValueError(f"Sibling note {sibling_id} not found")

                if position == MovePosition.BEFORE:
                    prev_note = db.query(DBNote).filter(
                        DBNote.indent == sibling.indent,
                        DBNote.position < sibling.position
                    ).order_by(DBNote.position.desc()).first()

                    new_position = Position.get_position_between(
                        prev_note.position if prev_note else None,
                        sibling.position
                    )
                else:  # Position.AFTER
                    next_note = db.query(DBNote).filter(
                        DBNote.indent == sibling.indent,
                        DBNote.position > sibling.position
                    ).order_by(DBNote.position).first()

                    new_position = Position.get_position_between(
                        sibling.position,
                        next_note.position if next_note else None
                    )

            # Prevent circular relationships
            if new_indent > note.indent:
                # Check if we're trying to move a note under one of its descendants
                descendants_query = db.query(DBNote).filter(
                    DBNote.position > note.position,
                    DBNote.indent > note.indent
                )
                
                next_sibling = db.query(DBNote).filter(
                    DBNote.indent == note.indent,
                    DBNote.position > note.position
                ).order_by(DBNote.position).first()
                
                if next_sibling:
                    descendants_query = descendants_query.filter(
                        DBNote.position < next_sibling.position
                    )
                
                if target_note and target_note.id in [d.id for d in descendants_query.all()]:
                    raise ValueError("Cannot create circular relationship")

            # Update the note
            note.position = new_position
            note.indent = new_indent
            db.flush()

        except Exception as e:
            print(e)
            raise

    @staticmethod
    def undo(db: Session) -> None:
        command_stack = global_state["command_stack"]
        if command_stack.current_index >= 0:
            command_stack.undo(db)
            return True
        return False

    @staticmethod
    def redo(db: Session) -> None:
        command_stack = global_state["command_stack"]
        if command_stack.current_index < len(command_stack.stack) - 1:
            command_stack.redo(db)
            return True
        return False 