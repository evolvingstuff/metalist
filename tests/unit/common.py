from contextlib import contextmanager
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.database import Base, DBNote
from app.models.linked_list import LinkedListManager
from app.models.enums import MovePosition
import random
import uuid
# from app.global_state_mod import global_state  # Module no longer exists
# from app.decorators import api_transaction_decorator  # Module no longer exists


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@contextmanager
def transaction_scope(db):
    try:
        yield
        db.commit()
    except Exception as e:
        db.rollback()
        raise e


def visualize_tree(db):
    def get_tree_string(parent_id=None, depth=0):
        with transaction_scope(db):
            nodes = LinkedListManager.get_ordered_child_list(db, parent_id)
        if not nodes:
            return ""

        result = ""
        for node in nodes:
            prefix = "  " * depth
            links = f"[prev={node.prev_id}, next={node.next_id}]\t'{node.content[:8]}'..."
            result += f"{prefix}└─ {node.id} {links}\n"
            result += get_tree_string(node.id, depth + 1)
        return result

    print("\nTree structure with links:")
    print(get_tree_string())
    print("─" * 40)
