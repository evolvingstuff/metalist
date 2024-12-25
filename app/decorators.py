from functools import wraps
from .global_state import global_state
from .models.api_transaction import ApiTransaction


def api_transaction_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Start a new transaction
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
            print('\tTODO... infer before / after')
            # Finalize the transaction
            global_state["current_transaction"].finalize_transaction()
            # Clear the transaction after use
            global_state["current_transaction"] = None
            print(f"@ Transaction ended for function: {func.__name__}")
        return result
    return wrapper
