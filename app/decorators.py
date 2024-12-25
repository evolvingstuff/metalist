from functools import wraps
from .global_state import global_state
from .models.api_transaction import ApiTransaction
from .core.config import ENABLE_UNDO_REDO


def api_transaction_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not ENABLE_UNDO_REDO:
            print(f"Undo/redo is disabled, skipping transaction for function: {func.__name__}")
            return func(*args, **kwargs)

        # Start a new transaction
        if global_state["current_transaction"] is not None:
            raise Exception("Transaction already in progress")
        global_state["current_transaction"] = ApiTransaction()
        print(f"@ Starting transaction for function: {func.__name__}")
        try:
            # Execute the wrapped function
            result = func(*args, **kwargs)
            print(f"@ Function {func.__name__} executed successfully")
        except Exception as e:
            print(f"Exception occurred in function {func.__name__}: {e}")
            raise
        finally:
            print('@@@ notes before updated:')
            for k in global_state["current_transaction"].state_before_updated.keys():
                print(f'\t{k[:8]}')
            print('@@@ notes current updated:')
            for k in global_state["current_transaction"].state_current_updated.keys():
                print(f'\t{k[:8]}')
            print('@@@ notes added:')
            for k in global_state["current_transaction"].state_added.keys():
                print(f'\t{k[:8]}')
            print('@@@ notes deleted:')
            for k in global_state["current_transaction"].state_deleted.keys():
                print(f'\t{k[:8]}')
            # Finalize the transaction
            global_state["current_transaction"].finalize_transaction()
            # Clear the transaction after use
            global_state["current_transaction"] = None
            # this is an action so gets rid of prior redos
            command_stack = global_state["command_stack"]
            command_stack.clear_after_current()
            print(f"@ Transaction ended for function: {func.__name__}")
        return result
    return wrapper
