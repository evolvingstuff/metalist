from .global_state_mod import global_state
from .models.api_transaction import ApiTransaction
from functools import wraps
from sqlalchemy.orm import Session
from threading import Lock

# Add a lock for transaction management
transaction_lock = Lock()


def db_transaction_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        db: Session = kwargs.get('db')
        try:
            result = func(*args, **kwargs)
            db.commit()  # Commit the transaction
            return result
        except Exception as e:
            db.rollback()  # Rollback in case of error
            raise e
    return wrapper


def api_transaction_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with transaction_lock:
            if global_state["current_transaction"] is not None:
                raise Exception("Transaction already in progress")
            global_state["current_transaction"] = ApiTransaction()
            try:
                #####################################################
                # Execute the wrapped function
                result = func(*args, **kwargs)
                #####################################################
                # print('@@@ notes before updated:')
                # tot = 0
                # for k in global_state["current_transaction"].state_before_updated.keys():
                #     val = global_state["current_transaction"].state_before_updated[k].content[:8]
                #     print(f'\t{k[:8]} content="{val}"')
                #     tot += 1
                # print('@@@ notes current updated:')
                # for k in global_state["current_transaction"].state_current_updated.keys():
                #     val = global_state["current_transaction"].state_current_updated[k].content[:8]
                #     print(f'\t{k[:8]} content="{val}"')
                #     tot += 1
                # print('@@@ notes added:')
                # for k in global_state["current_transaction"].state_added.keys():
                #     val = global_state["current_transaction"].state_added[k].content[:8]
                #     print(f'\t{k[:8]} content="{val}"')
                #     tot += 1
                # print('@@@ notes deleted:')
                # for k in global_state["current_transaction"].state_deleted.keys():
                #     val = global_state["current_transaction"].state_deleted[k].content[:8]
                #     print(f'\t{k[:8]} content="{val}"')
                #     tot += 1
                # assert tot > 0, 'there should always be at least one note to be updated, added, or deleted'

                # # Finalize the transaction
                global_state["current_transaction"].finalize_transaction(func.__name__)
                global_state["current_transaction"] = None
                # command_stack = global_state["command_stack"]
                # print(f'command stack size: {len(command_stack.stack)}')
                return result
            except Exception as e:
                print(f"Exception occurred in function {func.__name__}: {e}")
                raise e
    return wrapper
