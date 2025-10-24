from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["memory2"])


@router.post("/memory")
def memory_endpoint():
    raise HTTPException(status_code=501, detail="Not implemented")
