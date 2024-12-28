from fastapi import APIRouter
from app.models.database import SafeSession

router = APIRouter(prefix="/api/dev")

@router.post("/use-memory-db")
async def use_memory_db():
    return SafeSession.use_memory_db()

@router.post("/use-file-db") 
async def use_file_db():
    return SafeSession.use_file_db() 