import uuid
import copy
from sqlalchemy import event
from .database import DBNote
from ..global_state_mod import global_state
from ..undo_redo import Command
from ..core.config import ENABLE_EVENT_LISTENERS

# transaction_lock = Lock()

class ApiTransaction:
    def __init__(self):
        self.uuid = str(uuid.uuid4())
        self.state_before_updated = {}
        self.state_current_updated = {}
        self.state_added = {}
        self.state_deleted = {}
        print(f'@ New transaction created with ID: {self.uuid}')

    def calculate_states(self):
        # TODO asdfasdf
        state_before = {}
        state_after = {}

        # Handle deleted notes
        for note_id, note in self.state_deleted.items():
            if note_id in self.state_before_updated:
                # Note was deleted and existed at the start
                state_before[note_id] = self.state_before_updated[note_id]

        # Handle added notes
        for note_id, note in self.state_added.items():
            if note_id in self.state_current_updated:
                # Note was added and exists in the current state
                state_after[note_id] = self.state_current_updated[note_id]

        # Handle updated notes
        for note_id, note in self.state_before_updated.items():
            if note_id not in self.state_added:
                # Note existed before and was not newly added
                state_before[note_id] = self.state_before_updated[note_id]

        for note_id, note in self.state_current_updated.items():
            if note_id not in self.state_deleted:
                # Note still exists and was not deleted
                state_after[note_id] = self.state_current_updated[note_id]

        return state_before, state_after

    def finalize_transaction(self):
        print(f'@ Finalizing transaction with ID: {self.uuid}')
        state_before, state_after = self.calculate_states()
        # Create a command with before and after states
        command = Command(state_before, state_after)
        # Add the command to the transaction stack
        global_state["command_stack"].push(command)
        print(f"Transaction added to (global) command stack (size = {len(global_state['command_stack'].stack)})")

    def log_attribute_change(self, target, value, oldvalue, initiator):
        if isinstance(target, DBNote):
            # Define the attributes you want to track
            tracked_attributes = {'content', 'parent_id', 'prev_id', 'next_id'}

            # Check if the changed attribute is one of the tracked attributes
            if initiator.key not in tracked_attributes:
                return  # Ignore changes to untracked attributes

            # TODO asdfasdf
            # Filter out changes where oldvalue or value is not a string
            if not isinstance(oldvalue, str) or not isinstance(value, str):
                return  # Ignore these changes

            note_id = target.id
            oldvalue_str = str(oldvalue)[:20] + '...' if oldvalue is not None else 'None'
            assert oldvalue_str != 'LoaderCallableStatus...', 'uh oh'
            value_str = str(value)[:20] + '...' if value is not None else 'None'
            print(f"$$$- Attribute change detected on note {note_id[:8]}: {initiator.key} changed from '{oldvalue_str}' to '{value_str}'")
            if note_id not in self.state_before_updated:
                print(f'\t\tadding {note_id[:8]} to state_before_updated')
                self.state_before_updated[note_id] = copy.deepcopy(target)
            print(f'\t\tadding {note_id[:8]} to state_current_updated')
            self.state_current_updated[note_id] = copy.deepcopy(target)

    def log_note_creation(self, mapper, connection, target):
        if isinstance(target, DBNote):
            assert target.id is not None, 'Target id is None'
            note_id = target.id
            print(f"+++ Note created with ID: {note_id[:8]}...")
            print(f'\t\tadding {note_id[:8]} to state_added')
            if note_id not in self.state_added:
                print(f'\t\tadding {note_id[:8]} to state_added')
                self.state_added[note_id] = copy.deepcopy(target)
            print(f'\t\tadding {note_id[:8]} to state_current_updated')
            self.state_current_updated[note_id] = copy.deepcopy(target)


    def log_note_deletion(self, mapper, connection, target):
        if isinstance(target, DBNote):
            assert target.id is not None, 'Target id is None'
            note_id = target.id
            print(f"--- Note deleted with ID: {note_id[:8]}...")
            print(f'\t\tadding {note_id[:8]} to state_deleted')
            if note_id not in self.state_deleted:
                print(f'\t\tadding {note_id[:8]} to state_deleted')
                self.state_deleted[note_id] = copy.deepcopy(target)
            if note_id not in self.state_before_updated:
                print(f'\t\tadding {note_id[:8]} to state_before_updated')
                self.state_before_updated[note_id] = copy.deepcopy(target)
            print(f'\t\tadding {note_id[:8]} to state_current_updated')
            self.state_current_updated[note_id] = copy.deepcopy(target)
        

# Event handler functions
def log_attribute_change(target, value, oldvalue, initiator):
    transaction = global_state["current_transaction"]
    if transaction:
        transaction.log_attribute_change(target, value, oldvalue, initiator)

def log_note_creation(mapper, connection, target):
    transaction = global_state["current_transaction"]
    if transaction:
        transaction.log_note_creation(mapper, connection, target)

def log_note_deletion(mapper, connection, target):
    transaction = global_state["current_transaction"]
    if transaction:
        transaction.log_note_deletion(mapper, connection, target)

# Register event listeners
if ENABLE_EVENT_LISTENERS:
    event.listen(DBNote.content, 'set', log_attribute_change, retval=False)
    event.listen(DBNote.parent_id, 'set', log_attribute_change, retval=False)
    event.listen(DBNote.prev_id, 'set', log_attribute_change, retval=False)
    event.listen(DBNote.next_id, 'set', log_attribute_change, retval=False)
    event.listen(DBNote, 'before_insert', log_note_creation)
    event.listen(DBNote, 'before_delete', log_note_deletion)
