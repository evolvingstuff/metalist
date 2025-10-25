from app.models.database import SafeSession


def get_db():
    db = SafeSession()
    try:
        yield db
    finally:
        db.close()

