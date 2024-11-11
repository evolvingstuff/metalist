from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class DBNote(Base):
    __tablename__ = "notes"
    
    id = Column(String, primary_key=True)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DBTag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True)
    note_id = Column(String, ForeignKey("notes.id"))
    name = Column(String)
