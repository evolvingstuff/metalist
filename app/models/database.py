from sqlalchemy import Column, String, DateTime, ForeignKey, create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from sqlalchemy.orm.attributes import NO_VALUE


class SafeSession(Session):
    def commit(self):
        """Override commit to check for corruption in dev mode"""
        # dev_mode = True  # Could be from config
        #
        # if dev_mode:
        #     # Check for corruption in DBNote linked lists
        #     if LinkedListManager.detect_corruption(self, DBNote, None):
        #         self.rollback()
        #         raise ValueError("Linked list corruption detected, rolling back changes")
        
        super().commit()

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=SafeSession)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class DBNote(Base):
    __tablename__ = "notes"
    
    id = Column(String, primary_key=True)
    content = Column(String)
    parent_id = Column(String, ForeignKey('notes.id'), nullable=True)
    prev_id = Column(String, ForeignKey('notes.id'), nullable=True)
    next_id = Column(String, ForeignKey('notes.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def log_attribute_change(target, value, oldvalue, initiator):
    """Log attribute changes on a note."""
    if isinstance(target, DBNote):
        # Ignore changes from NO_VALUE to a real value
        if oldvalue is NO_VALUE:
            return

        oldvalue_str = oldvalue[:8] + '...' if oldvalue is not None else 'None'
        value_str = value[:8] + '...' if value is not None else 'None'

        print(f"$$$ Attribute change detected on note {target.id[:8]}: {initiator.key} changed from '{oldvalue_str}' to '{value_str}'")
def log_note_creation(mapper, connection, target):
    """Log when a note is created."""
    if isinstance(target, DBNote):
        print(f"+++ Note created with ID: {target.id[:8]}..., content: '{target.content[:8]}...'")

def log_note_deletion(mapper, connection, target):
    """Log when a note is deleted."""
    if isinstance(target, DBNote):
        print(f"--- Note deleted with ID: {target.id[:8]}..., content: '{target.content[:8]}...'")

# Register attribute change listeners for each attribute of interest
event.listen(DBNote.content, 'set', log_attribute_change, retval=False)
event.listen(DBNote.parent_id, 'set', log_attribute_change, retval=False)
event.listen(DBNote.prev_id, 'set', log_attribute_change, retval=False)
event.listen(DBNote.next_id, 'set', log_attribute_change, retval=False)

# Register event listeners for note creation and deletion
event.listen(DBNote, 'before_insert', log_note_creation)
event.listen(DBNote, 'before_delete', log_note_deletion)

