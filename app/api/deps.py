from app.models.database import SafeSession
from app.db.session import get_request_session


def get_db():
    request_session = get_request_session()
    if request_session is not None:
        yield request_session
        return

    db = SafeSession()
    try:
        yield db
    finally:
        db.close()
