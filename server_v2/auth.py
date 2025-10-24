from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api2/auth", tags=["auth2"])


@router.get("/status")
def auth_status():
    return {
        "authenticated": False,
        "has_password": False,
        "encryption_enabled": False,
        "encryption_algorithm": None,
    }


@router.post("/login")
def login():
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/logout")
def logout():
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/sessions")
def sessions():
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/settings/password/create")
def create_password():
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/settings/password/change")
def change_password():
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/settings/password/remove")
def remove_password():
    raise HTTPException(status_code=501, detail="Not implemented")

