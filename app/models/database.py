from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from datetime import datetime, timezone
from app.core.config import DATABASE_URL


class SafeSession(Session):
    _engine = create_engine(DATABASE_URL)
    _memory_engine = None
    _current_session = None

    @classmethod
    def use_memory_db(cls):
        if cls._current_session:
            cls._current_session.close()
        print("\n" + "="*50)
        print("""
🧪 SWITCHING TO TEST MODE 🧪
┌──────────────────────────┐
│       DEV DATABASE       │
│  *All Data is Temporary  │
└──────────────────────────┘
        """)
        print("="*50 + "\n")
        cls._memory_engine = create_engine('sqlite:///./notes.dev.db')
        Base.metadata.create_all(cls._memory_engine)
        return {'status': 'ok', 'message': 'Using in-memory database'}

    @classmethod
    def use_file_db(cls):
        if cls._current_session:
            cls._current_session.close()
        print("\n" + "="*50)
        print("""
📝 RETURNING TO PRODUCTION MODE 📝
┌──────────────────────────┐
│      PROD DATABASE       │
│                          │
└──────────────────────────┘
        """)
        print("="*50 + "\n")
        cls._memory_engine = None
        Base.metadata.create_all(cls._engine)
        return {'status': 'ok', 'message': 'Using file database'}

    @classmethod
    def get_engine(cls):
        return cls._memory_engine if cls._memory_engine else cls._engine

    def commit(self):
        """Override commit to check for corruption in dev mode"""
        try:
            super().commit()
        except Exception as e:
            self.rollback()
            raise e


Base = declarative_base()

SessionLocal = sessionmaker(class_=SafeSession, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal(bind=SafeSession.get_engine())
    try:
        yield db
    finally:
        db.close()


class DBNote(Base):
    __tablename__ = "notes"
    
    id = Column(String, primary_key=True)
    content = Column(String)
    
    # Old fields for linked list implementation
    parent_id = Column(String, ForeignKey('notes.id'), nullable=True)
    prev_id = Column(String, ForeignKey('notes.id'), nullable=True)
    next_id = Column(String, ForeignKey('notes.id'), nullable=True)
    
    # New fields for position-based implementation
    position = Column(String, nullable=True)  # Lexicographically ordered position string
    indent = Column(Integer, nullable=True)   # Indentation level, derived from tree structure
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
