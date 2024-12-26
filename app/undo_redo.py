import uuid
from sqlalchemy.orm import Session
from .models.database import DBNote


class Command:
    def __init__(self, pre_state, post_state):
        self.uuid = str(uuid.uuid4())
        self.pre_state = pre_state
        self.post_state = post_state

    def undo(self, db: Session):
        # Revert to the pre_state
        self._apply_state(self.pre_state, self.post_state, db)

    def redo(self, db: Session):
        # Reapply the post_state
        self._apply_state(self.post_state, self.pre_state, db)

    def _apply_state(self, target_state, reference_state, db: Session):
        """
        Apply the target_state to the database, using reference_state to determine changes.
        """
        for note_id, target_note in target_state.items():
            reference_note = reference_state.get(note_id)

            if reference_note is None:
                # Note is new in target_state, so create it
                self._create_note_in_db(target_note, db)
            elif target_note != reference_note:
                # Note exists in both states but has changes, so update it
                self._update_note_in_db(target_note, db)

        for note_id in reference_state:
            if note_id not in target_state:
                # Note is missing in target_state, so delete it
                self._delete_note_from_db(reference_state[note_id], db)

    def _create_note_in_db(self, note, db: Session):
        new_note = DBNote(
            id=note.id,
            content=note.content,
            parent_id=note.parent_id,
            prev_id=note.prev_id,
            next_id=note.next_id,
            created_at=note.created_at,
            updated_at=note.updated_at
        )
        db.add(new_note)
        # db.commit()

    def _update_note_in_db(self, note, db: Session):
        existing_note = db.get(DBNote, note.id)
        if existing_note:
            existing_note.content = note.content
            existing_note.parent_id = note.parent_id
            existing_note.prev_id = note.prev_id
            existing_note.next_id = note.next_id
            existing_note.updated_at = note.updated_at
            # db.commit()

    def _delete_note_from_db(self, note, db: Session):
        existing_note = db.get(DBNote, note.id)
        if existing_note:
            db.delete(existing_note)
            # db.commit()

class CommandStack:
    def __init__(self):
        self.stack = []
        self.current_index = -1

    def push(self, command):
        # Remove any commands after the current index
        self.stack = self.stack[:self.current_index + 1]
        self.stack.append(command)
        self.current_index += 1

    def undo(self, db: Session):
        if self.current_index >= 0:
            command = self.stack[self.current_index]
            command.undo(db)
            self.current_index -= 1
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

