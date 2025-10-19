from fastapi import APIRouter
from ..models.database import SafeSession
from fastapi import HTTPException
from sqlalchemy import delete, inspect
import logging

from app.db import begin_writer, get_engine, metadata, notes_table

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/use-dev-db")
async def use_dev_db():
    try:
        logger.info("Switching to dev DB")
        SafeSession.use_memory_db()
        engine = get_engine()
        
        # Create all tables
        metadata.create_all(bind=engine)
        
        # Clear all data from notes table
        with begin_writer() as connection:
            connection.execute(delete(notes_table))
            logger.info("Cleared all notes from test DB")
        
        # Log schema details
        inspector = inspect(engine)
        for table_name in inspector.get_table_names():
            logger.info(f"Table: {table_name}")
            for column in inspector.get_columns(table_name):
                logger.info(f"  Column: {column['name']} ({column['type']})")
            
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Failed to switch to dev DB")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/use-file-db")
async def use_file_db():
    try:
        logger.info("Switching to file DB")
        SafeSession.use_file_db()
        logger.info("Successfully switched to file DB")
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Failed to switch to file DB")
        raise HTTPException(status_code=500, detail=str(e)) 
