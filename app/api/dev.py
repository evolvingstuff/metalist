from fastapi import APIRouter
import logging

from ..models.database import SafeSession
from app.db.session import begin_writer
from app.db.schema import initialize_schema, NOTES_TABLE

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/use-dev-db")
async def use_dev_db():
    logger.info("Switching to dev DB")
    SafeSession.use_memory_db()

    with begin_writer() as connection:
        initialize_schema(connection.raw_connection)
        connection.execute(f"DELETE FROM {NOTES_TABLE}", ())
        logger.info("Cleared all notes from test DB")

    return {"status": "ok"}


@router.post("/use-file-db")
async def use_file_db():
    logger.info("Switching to file DB")
    SafeSession.use_file_db()
    return {"status": "ok"}
