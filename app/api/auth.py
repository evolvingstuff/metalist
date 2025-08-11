"""Authentication API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.models.database import get_db
from app.services.auth import AuthService
from app.services.tokens import token_service
from app.utils.encryption import set_encryption_key, clear_encryption_key
from app.services.content_cache import refresh_encrypted_cache


router = APIRouter(prefix="/api/auth", tags=["auth"])


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


class PasswordRemoveRequest(BaseModel):
    current_password: str


def get_client_info(request: Request) -> str:
    """Extract client information from request."""
    user_agent = request.headers.get("user-agent", "Unknown")
    client_host = request.client.host if request.client else "Unknown"
    return f"{user_agent[:100]} - {client_host}"


def verify_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Verify authentication token from header.
    
    Args:
        authorization: Authorization header value
        
    Returns:
        Token if valid, None otherwise
    """
    if not authorization:
        return None
    
    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    token = parts[1]
    
    if token_service.verify_token(token):
        # Refresh token on valid request (sliding window)
        token_service.refresh_token(token)
        return token
    
    return None


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """Require valid authentication token.
    
    Args:
        authorization: Authorization header value
        
    Returns:
        Valid token
        
    Raises:
        HTTPException: If no valid token
    """
    token = verify_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return token


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_req: LoginRequest,
    db: Session = Depends(get_db)
):
    """Login with password and receive authentication token."""
    auth = AuthService(db)
    
    # Check if password is set
    if not auth.has_password():
        raise HTTPException(status_code=400, detail="No password is set. Please set a password first.")
    
    # Verify password
    if not auth.verify_password(login_req.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    # Get settings for salt and encrypted DEK
    settings = auth.get_settings()
    if not settings:
        raise HTTPException(status_code=500, detail="Failed to retrieve settings")
    
    # Derive master key from password
    from app.services.encryption import EncryptionService
    encryption = EncryptionService()
    master_key = encryption.derive_master_key(login_req.password, settings.password_salt)
    
    # Decrypt the DEK
    dek = encryption.decrypt_dek(
        settings.encrypted_dek,
        settings.dek_nonce,
        settings.dek_tag,
        master_key
    )
    
    # Set encryption keys for this session
    set_encryption_key(login_req.password, settings.password_salt)  # TODO: Update this to use DEK
    
    # Refresh cache with decrypted content now that we have the key
    refresh_encrypted_cache(db)
    
    # Create token with master key and DEK for encryption
    client_info = get_client_info(request)
    token = token_service.create_token(client_info, master_key, dek)
    
    return LoginResponse(
        token=token,
        message="Login successful"
    )


@router.post("/logout")
async def logout(token: str = Depends(require_auth)):
    """Logout and revoke the current token."""
    token_service.revoke_token(token)
    clear_encryption_key()
    
    return {"message": "Logout successful"}


@router.get("/status")
async def auth_status(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None)
):
    """Check authentication status and encryption configuration."""
    auth = AuthService(db)
    settings = auth.get_settings()
    
    # Check if token is valid
    token = verify_token(authorization)
    is_authenticated = token is not None
    
    return {
        "authenticated": is_authenticated,
        "has_password": auth.has_password(),
        "encryption_enabled": settings.encryption_enabled if settings else False,
        "encryption_algorithm": settings.encryption_algorithm if settings else None
    }


@router.post("/settings/password/create")
async def create_password(
    password_req: PasswordCreateRequest,
    db: Session = Depends(get_db)
):
    """Set initial password when none exists."""
    auth = AuthService(db)
    
    # Check if password already exists
    if auth.has_password():
        raise HTTPException(status_code=400, detail="Password already exists. Use change endpoint instead.")
    
    # Set the password
    success, message = auth.set_password(password_req.password)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Revoke all existing tokens (shouldn't be any, but just in case)
    token_service.revoke_all_tokens()
    
    return {"message": message}


@router.put("/settings/password/change")
async def change_password(
    password_req: PasswordChangeRequest,
    db: Session = Depends(get_db),
    token: str = Depends(require_auth)
):
    """Change existing password."""
    auth = AuthService(db)
    
    # Change the password
    success, message = auth.change_password(
        password_req.current_password,
        password_req.new_password
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Revoke all tokens (including current one)
    token_service.revoke_all_tokens()
    
    return {"message": message}


@router.delete("/settings/password/remove")
async def remove_password(
    password_req: PasswordRemoveRequest,
    db: Session = Depends(get_db),
    token: str = Depends(require_auth)
):
    """Remove password protection."""
    auth = AuthService(db)
    
    # Remove the password
    success, message = auth.remove_password(password_req.current_password)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Revoke all tokens
    token_service.revoke_all_tokens()
    
    return {"message": message}


@router.get("/sessions")
async def list_sessions(token: str = Depends(require_auth)):
    """List all active sessions."""
    sessions = token_service.list_active_sessions()
    return {"sessions": sessions}