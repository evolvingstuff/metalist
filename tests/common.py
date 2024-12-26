from contextlib import contextmanager
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.database import Base, DBNote
from app.models.linked_list import LinkedListManager, MovePosition
import random
import uuid


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
