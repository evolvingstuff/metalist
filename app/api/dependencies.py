from app.models.database import SafeSession

def get_db():
    db = SafeSession(bind=SafeSession.get_engine())
    try:
        yield db
    finally:
        db.close()
