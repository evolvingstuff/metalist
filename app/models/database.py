from sqlalchemy import Column, String, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Optional

class SafeSession(Session):
    def commit(self):
        """Override commit to check for corruption in dev mode"""
        dev_mode = True  # Could be from config
        
        if dev_mode:
            # Check for corruption in DBNote linked lists
            if LinkedListManager.detect_corruption(self, DBNote, None):
                self.rollback()
                raise ValueError("Linked list corruption detected, rolling back changes")
        
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
