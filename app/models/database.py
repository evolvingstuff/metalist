from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer, Boolean, LargeBinary
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from datetime import datetime, timezone
from app.core.config import DATABASE_URL
from sqlalchemy.pool import StaticPool


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
│   IN-MEMORY DATABASE     │
│  *All Data is Temporary  │
└──────────────────────────┘
        """)
        print("="*50 + "\n")
        # Use StaticPool and connect_args for thread safety
        cls._memory_engine = create_engine(
            'sqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool
        )
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

    is_collapsed = Column(Boolean, default=False, nullable=False)
    
    # Encryption fields
    encryption_nonce = Column(LargeBinary, nullable=True)  # AES-GCM nonce (per note)
    encryption_tag = Column(LargeBinary, nullable=True)   # AES-GCM authentication tag (per note)
    
    # Old fields for linked list implementation
    parent_id = Column(String, ForeignKey('notes.id'), nullable=True)
    prev_id = Column(String, ForeignKey('notes.id'), nullable=True)
    next_id = Column(String, ForeignKey('notes.id'), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AppSettings(Base):
    __tablename__ = "app_settings"
    
    id = Column(Integer, primary_key=True, default=1)
    
    # Password/encryption settings
    password_hash = Column(String, nullable=True)  # PBKDF2 hash of the master password (null = no password)
    password_salt = Column(LargeBinary, nullable=True)  # Random salt for password hashing
    password_iterations = Column(Integer, nullable=True)  # PBKDF2 iterations used for this hash
    encryption_enabled = Column(Boolean, default=False)  # Whether encryption is active
    encryption_algorithm = Column(String, nullable=True)  # Encryption algorithm (e.g., "AES-256-GCM")
    
    # DEK (Data Encryption Key) fields
    encrypted_dek = Column(LargeBinary, nullable=True)  # DEK encrypted with master key
    dek_nonce = Column(LargeBinary, nullable=True)  # Nonce for DEK encryption
    dek_tag = Column(LargeBinary, nullable=True)  # Authentication tag for DEK encryption
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
