from .undo_redo import CommandStack
from threading import Lock

# A simple dictionary to hold global state
global_state = {
    "current_transaction": None,
    "command_stack": CommandStack(),
    "lock": Lock()
} 