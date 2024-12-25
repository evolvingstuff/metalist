from .undo_redo import CommandStack

# A simple dictionary to hold global state
global_state = {
    "current_transaction": None,
    "command_stack": CommandStack()
} 