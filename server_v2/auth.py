from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from typing import Optional
from pydantic import BaseModel

from app.models.database import SafeSession
from app.api.dependencies import get_db
from app.services.auth import AuthService
from app.services.tokens import token_service
from app.utils.encryption import set_encryption_key, clear_encryption_key
from app.services.content_cache import refresh_encrypted_cache


router = APIRouter(prefix="/auth", tags=["auth2"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    message: str


class PasswordCreateRequest(BaseModel):
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    iterations: Optional[int] = None


class PasswordRemoveRequest(BaseModel):
    current_password: str


def _client_info(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "Unknown")
    client_host = request.client.host if request.client else "Unknown"
    return f"{user_agent[:100]} - {client_host}"


def _verify_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1]
    if token_service.verify_token(token):
        token_service.refresh_token(token)
        return token
    return None


def _require_auth(authorization: Optional[str] = Header(None)) -> str:
    token = _verify_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return token


@router.post("/login", response_model=LoginResponse)
def login(request: Request, payload: LoginRequest, db: SafeSession = Depends(get_db)):
    auth = AuthService(db)
    if not auth.has_password():
        raise HTTPException(status_code=400, detail="No password is set. Please set a password first.")
    if not auth.verify_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    settings = auth.get_settings()
    if not settings:
        raise HTTPException(status_code=500, detail="Failed to retrieve settings")

    from app.services.encryption import EncryptionService

    encryption = EncryptionService()
    master_key = encryption.derive_master_key(payload.password, settings.password_salt)
    dek = encryption.decrypt_dek(
        settings.encrypted_dek,
        settings.dek_nonce,
        settings.dek_tag,
        master_key,
    )

    set_encryption_key(payload.password, settings.password_salt)
    refresh_encrypted_cache(db)

    token = token_service.create_token(_client_info(request), master_key, dek)
    return LoginResponse(token=token, message="Login successful")


@router.post("/logout")
def logout(token: str = Depends(_require_auth)):
    token_service.revoke_token(token)
    clear_encryption_key()
    return {"message": "Logout successful"}


@router.get("/status")
def auth_status(db: SafeSession = Depends(get_db), authorization: Optional[str] = Header(None)):
    auth = AuthService(db)
    settings = auth.get_settings()
    token = _verify_token(authorization)
    return {
        "authenticated": token is not None,
        "has_password": auth.has_password(),
        "encryption_enabled": settings.encryption_enabled if settings else False,
        "encryption_algorithm": settings.encryption_algorithm if settings else None,
    }


@router.post("/settings/password/create")
def create_password(payload: PasswordCreateRequest, db: SafeSession = Depends(get_db)):
    auth = AuthService(db)
    if auth.has_password():
        raise HTTPException(status_code=400, detail="Password already exists. Use change endpoint instead.")
    success, message = auth.set_password(payload.password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    token_service.revoke_all_tokens()
    return {"message": message}


@router.put("/settings/password/change")
def change_password(payload: PasswordChangeRequest, db: SafeSession = Depends(get_db), token: str = Depends(_require_auth)):
    auth = AuthService(db)
    success, message = auth.change_password(
        payload.current_password,
        payload.new_password,
        payload.iterations,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    token_service.revoke_all_tokens()
    return {"message": message}


@router.post("/settings/password/remove")
def remove_password(payload: PasswordRemoveRequest, db: SafeSession = Depends(get_db), token: str = Depends(_require_auth)):
    auth = AuthService(db)
    success, message = auth.remove_password(payload.current_password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    token_service.revoke_all_tokens()
    return {"message": message}


@router.get("/sessions")
def sessions(token: str = Depends(_require_auth)):
    return {"sessions": token_service.list_active_sessions()}
