"""Authentication middleware for API requests."""

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.tokens import token_service
from app.services.auth import AuthService
from app.models.database import get_db
from app.utils.encryption import set_encryption_key


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check authentication on protected routes."""
    
    # Paths that don't require authentication
    PUBLIC_PATHS = [
        "/api/auth/login",
        "/api/auth/status", 
        "/static/",  # CSS/JS files needed for login page
        "/favicon.ico",
        "/",  # Main page (needs to load to show login modal)
    ]
    
    # Note: /api/notes/* paths are NOT in this list - they require auth when password is set
    
    async def dispatch(self, request: Request, call_next):
        """Check authentication for protected routes."""
        path = request.url.path
        
        print(f"Middleware checking path: {path}")
        
        # Skip authentication for public paths
        public_match = None
        for public in self.PUBLIC_PATHS:
            if path.startswith(public):
                public_match = public
                break
                
        if public_match:
            print(f"Path {path} is public (matched '{public_match}'), skipping auth")
            return await call_next(request)
        
        print(f"Path {path} is NOT public, checking auth")
        
        # Check if password is required
        try:
            db = next(get_db())
            auth = AuthService(db)
            
            # Special case: password creation endpoint is only public if no password exists
            if path == "/api/auth/settings/password/create" and not auth.has_password():
                print(f"Password creation allowed - no password set")
                return await call_next(request)
            
            # If no password is set, allow all access
            if not auth.has_password():
                print(f"No password set, allowing {path}")
                return await call_next(request)
            
            print(f"Password is set, checking auth for {path}")
            
            # Password is set, require authentication
            authorization = request.headers.get("authorization")
            
            if not authorization:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"}
                )
            
            # Extract token from "Bearer <token>" format
            parts = authorization.split()
            if len(parts) != 2 or parts[0].lower() != "bearer":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authorization format"}
                )
            
            token = parts[1]
            
            # Verify token
            if not token_service.verify_token(token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"}
                )
            
            # Refresh token (sliding window)
            token_service.refresh_token(token)
            
            # Set encryption key for this request
            encryption_info = token_service.get_encryption_info(token)
            print(f"[Middleware] Got encryption info: {encryption_info is not None}")
            if encryption_info:
                password, salt = encryption_info
                print(f"[Middleware] Setting encryption key for path: {path}")
                set_encryption_key(password, salt)
            else:
                print(f"[Middleware] No encryption info found for token")
            
            # Continue with request
            response = await call_next(request)
            
            # Optionally add refreshed token to response header
            # This allows client to update token if needed
            # response.headers["X-New-Token"] = token
            
            return response
            
        except Exception as e:
            print(f"Auth middleware error: {e}")
            # On error, allow request to continue
            # The individual endpoints will handle auth if needed
            return await call_next(request)