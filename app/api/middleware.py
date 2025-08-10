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
        "/api/auth/settings/password/create",
        "/api/dev/",  # Dev endpoints
        "/static/",
        "/favicon.ico",
        "/",  # Main page
    ]
    
    async def dispatch(self, request: Request, call_next):
        """Check authentication for protected routes."""
        path = request.url.path
        
        # Skip authentication for public paths
        if any(path.startswith(public) for public in self.PUBLIC_PATHS):
            return await call_next(request)
        
        # Skip for non-API routes (template rendering)
        if not path.startswith("/api/"):
            return await call_next(request)
        
        # Check if password is required
        try:
            db = next(get_db())
            auth = AuthService(db)
            
            # If no password is set, allow access
            if not auth.has_password():
                return await call_next(request)
            
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
            
            # Set encryption key if not already set
            settings = auth.get_settings()
            if settings and settings.encryption_enabled:
                # Note: This requires the password to be stored in token info
                # For now, encryption key must be set at login
                pass
            
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