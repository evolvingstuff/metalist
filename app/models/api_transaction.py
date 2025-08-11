import uuid
import copy
from typing import TYPE_CHECKING
from sqlalchemy import event
from .database import DBNote
from ..undo_redo import Command

# Avoid circular import
if TYPE_CHECKING:
    from ..services.transaction_manager import TransactionManager

_updating_state = False
tracked_attributes = {'content', 'parent_id', 'prev_id', 'next_id'}


class ApiTransaction:
    def __init__(self, transaction_manager: 'TransactionManager'):
        self.uuid = str(uuid.uuid4())
        self.transaction_manager = transaction_manager
        self.state_before_updated = {}
        self.state_current_updated = {}
        self.state_added = {}
        self.state_deleted = {}
        self._updating_state = False
        print(f'@ New transaction created with ID: {self.uuid}')

    def calculate_states(self):

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

    def finalize_transaction(self, action: str):
        print(f'@ Finalizing transaction with ID: {self.uuid}')
        state_before, state_after = self.calculate_states()
        # Create a command with before and after states
        command = Command(state_before, state_after, action)
        # Add the command to the transaction stack via the transaction manager
        self.transaction_manager.add_command_to_stack(command)

    def log_attribute_set(self, target, value, oldvalue, initiator):
        if self._updating_state:
            return
        if isinstance(target, DBNote):
            # Check if the changed attribute is one of the tracked attributes
            if initiator.key not in tracked_attributes:
                return  # Ignore changes to untracked attributes

            if str(oldvalue) == 'LoaderCallableStatus.NO_VALUE':
                return

            note_id = target.id
            oldvalue_str = str(oldvalue) if oldvalue is not None else ''
            value_str = str(value) if value is not None else ''
            print(f"$$$- Attribute change detected on note {note_id[:8]}: {initiator.key} changed from '{oldvalue_str}' to '{value_str}'")
            if note_id not in self.state_before_updated:
                print(f'\t\tadding {note_id[:8]} to state_before_updated')
                self.state_before_updated[note_id] = copy.deepcopy(target)
            print(f'\t\tadding {note_id[:8]} to state_current_updated')
            self.state_current_updated[note_id] = copy.deepcopy(target)

            ############################################################
            # Temporarily remove the effects of the event listener
            # This is a bit of a hack, but otherwise when we update the value
            # we trigger the event listener again, which causes an infinite loop...
            # ... and we do not like infinite loops :(
            self._updating_state = True
            setattr(self.state_current_updated[note_id], initiator.key, value)
            self._updating_state = False
            ############################################################

    def log_note_after_insert(self, mapper, connection, target):
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

    def log_note_before_delete(self, mapper, connection, target):
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
def log_attribute_set(target, value, oldvalue, initiator):
    # Import here to avoid circular dependency
    from ..services.transaction_manager import get_transaction_manager
    transaction_manager = get_transaction_manager()
    transaction = transaction_manager.get_current_transaction()
    if transaction:
        transaction.log_attribute_set(target, value, oldvalue, initiator)


# Cache event handlers
def cache_note_on_content_update(target, value, oldvalue, initiator):
    """Update cache when note content is modified"""
    if isinstance(target, DBNote) and initiator.key == 'content':
        # Import here to avoid circular dependency
        from ..services.content_cache import cache_note
        from ..utils.encryption import decrypt
        
        try:
            # Use separate encryption fields for decryption
            decrypted_content = decrypt(value, target.encryption_nonce, target.encryption_tag)
            cache_note(target.id, decrypted_content)
        except Exception as e:
            # FAIL FAST AND LOUD - NO SILENT FAILURES
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"🚨 FATAL: Failed to update cache for note {target.id}: {e}")
            logger.error(f"🚨 Cache system integrity compromised!")
            logger.error(f"🚨 CRASHING IMMEDIATELY")
            raise RuntimeError(f"Cache update failed for note {target.id}: {e}") from e


def log_note_after_insert(mapper, connection, target):
    # Import here to avoid circular dependency
    from ..services.transaction_manager import get_transaction_manager
    transaction_manager = get_transaction_manager()
    transaction = transaction_manager.get_current_transaction()
    if transaction:
        transaction.log_note_after_insert(mapper, connection, target)


def cache_note_after_insert(mapper, connection, target):
    """Add new note to cache after database insert"""
    if isinstance(target, DBNote) and target.content:
        # Import here to avoid circular dependency
        from ..services.content_cache import cache_note
        from ..utils.encryption import decrypt
        
        try:
            # Use separate encryption fields for decryption
            decrypted_content = decrypt(target.content, target.encryption_nonce, target.encryption_tag)
            cache_note(target.id, decrypted_content)
        except Exception as e:
            # FAIL FAST AND LOUD - NO SILENT FAILURES
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"🚨 FATAL: Failed to cache new note {target.id}: {e}")
            logger.error(f"🚨 Cache system integrity compromised!")
            logger.error(f"🚨 CRASHING IMMEDIATELY")
            raise RuntimeError(f"Cache creation failed for new note {target.id}: {e}") from e


 # another hack!
def log_note_before_delete(mapper, connection, target):
    # Import here to avoid circular dependency
    from ..services.transaction_manager import get_transaction_manager
    transaction_manager = get_transaction_manager()
    transaction = transaction_manager.get_current_transaction()
    if transaction:
        transaction.log_note_before_delete(mapper, connection, target)


def cache_note_before_delete(mapper, connection, target):
    """Remove note from cache before database delete"""
    if isinstance(target, DBNote):
        # Import here to avoid circular dependency
        from ..services.content_cache import remove_cached_note
        
        try:
            remove_cached_note(target.id)
        except Exception as e:
            # FAIL FAST AND LOUD - NO SILENT FAILURES
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"🚨 FATAL: Failed to remove cached note {target.id}: {e}")
            logger.error(f"🚨 Cache system integrity compromised!")
            logger.error(f"🚨 CRASHING IMMEDIATELY")
            raise RuntimeError(f"Cache removal failed for note {target.id}: {e}") from e


# Register event listeners
event.listen(DBNote.content, 'set', log_attribute_set, retval=False)
event.listen(DBNote.parent_id, 'set', log_attribute_set, retval=False)
event.listen(DBNote.prev_id, 'set', log_attribute_set, retval=False)
event.listen(DBNote.next_id, 'set', log_attribute_set, retval=False)
event.listen(DBNote, 'after_insert', log_note_after_insert)
event.listen(DBNote, 'before_delete', log_note_before_delete)

# Register cache event listeners
event.listen(DBNote.content, 'set', cache_note_on_content_update, retval=False)
event.listen(DBNote, 'after_insert', cache_note_after_insert)
event.listen(DBNote, 'before_delete', cache_note_before_delete)
