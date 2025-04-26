from .global_state_mod import global_state
from .models.api_transaction import ApiTransaction
from functools import wraps
from sqlalchemy.orm import Session
from threading import Lock
import time

# Add a lock for transaction management
transaction_lock = Lock()

# Configuration for API response delays (in seconds)
API_DELAY = {
    "ENABLED": False,  # Set to True to enable artificial delays
    "DEFAULT": 1.0,    # Default delay in seconds
    "RANDOM": False,   # Whether to use random delay within MIN/MAX range
    "MIN": 0.5,        # Minimum random delay (if RANDOM is True)
    "MAX": 2.0,        # Maximum random delay (if RANDOM is True)
    # Per-endpoint delays, override DEFAULT (add as needed)
    "ENDPOINTS": {
        "undo": 1.5,
        "redo": 1.5,
        "get_notes_fragment": 1.0
    }
}


def delay_response_decorator(func):
    """Decorator to add configurable delay to API responses for testing loading states"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Skip if delays are disabled
        if not API_DELAY["ENABLED"]:
            return func(*args, **kwargs)
            
        # Determine delay time
        delay = API_DELAY["DEFAULT"]
        
        # Check if this endpoint has a specific delay
        func_name = func.__name__
        if func_name in API_DELAY["ENDPOINTS"]:
            delay = API_DELAY["ENDPOINTS"][func_name]
            
        # Apply random delay if configured
        if API_DELAY["RANDOM"]:
            import random
            delay = random.uniform(API_DELAY["MIN"], API_DELAY["MAX"])
            
        # Log the delay (helpful for debugging)
        print(f"[API Delay] Adding {delay:.2f}s delay to {func_name}...")
        
        # Apply the delay
        time.sleep(delay)
        
        # Execute the original function
        return func(*args, **kwargs)
    
    return wrapper

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
                tot = 0
                for k in global_state["current_transaction"].state_before_updated.keys():
                    val = global_state["current_transaction"].state_before_updated[k].content[:8]
                    # print(f'\t{k[:8]} content="{val}"')
                    tot += 1
                # print('@@@ notes current updated:')
                for k in global_state["current_transaction"].state_current_updated.keys():
                    val = global_state["current_transaction"].state_current_updated[k].content[:8]
                    # print(f'\t{k[:8]} content="{val}"')
                    tot += 1
                # print('@@@ notes added:')
                for k in global_state["current_transaction"].state_added.keys():
                    val = global_state["current_transaction"].state_added[k].content[:8]
                    # print(f'\t{k[:8]} content="{val}"')
                    tot += 1
                # print('@@@ notes deleted:')
                for k in global_state["current_transaction"].state_deleted.keys():
                    val = global_state["current_transaction"].state_deleted[k].content[:8]
                    # print(f'\t{k[:8]} content="{val}"')
                    tot += 1
                assert tot > 0, 'there should always be at least one note to be updated, added, or deleted'

                # Finalize the transaction
                global_state["current_transaction"].finalize_transaction(func.__name__)
                command_stack = global_state["command_stack"]
                print(f'command stack size: {len(command_stack.stack)}')
                return result
            except Exception as e:
                print(f"Exception occurred in function {func.__name__}: {e}")
                raise e
            finally:
                # Always clean up the transaction
                global_state["current_transaction"] = None
    return wrapper
