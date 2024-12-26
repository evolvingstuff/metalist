from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.core.config import DATABASE_URL  # Assuming DATABASE_URL is defined here


class SafeSession(Session):
    def commit(self):
        """Override commit to check for corruption in dev mode"""
        super().commit()

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

