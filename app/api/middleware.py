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
    ]
    
    # Paths to suppress verbose logging for (frequent polling endpoints)
    QUIET_PATHS = [
        "/api/notes/check-updates",
        "/api/notes/acquire-lock",
        "/api/notes/release-lock"
    ]
    
    # Background/automated paths that should NOT refresh tokens (not user activity)
    NO_TOKEN_REFRESH_PATHS = [
        "/api/notes/check-updates",
        "/api/notes/acquire-lock",
        "/api/notes/release-lock",
        "/api/auth/status"  # ConnectivityMonitor pings this every 2 seconds
    ]
    
    # Note: /api/notes/* paths are NOT in this list - they require auth when password is set
    
    async def dispatch(self, request: Request, call_next):
        """Check authentication for protected routes."""
        path = request.url.path
        
        # Check if this is a quiet path (suppress verbose logging)
        is_quiet = any(path.startswith(quiet) for quiet in self.QUIET_PATHS)
        
        if not is_quiet:
            print(f"Middleware checking path: {path}")
        
        # Skip authentication for public paths
        public_match = None
        
        # Handle exact root path match
        if path == "/":
            public_match = "/ (root)"
        else:
            # Check other public paths with startswith
            for public in self.PUBLIC_PATHS:
                if path.startswith(public):
                    public_match = public
                    break
                
        if public_match:
            if not is_quiet:
                print(f"Path {path} is public (matched '{public_match}'), skipping auth")
            return await call_next(request)
        
        if not is_quiet:
            print(f"Path {path} is NOT public, checking auth")
        
        # Check if password is required
        try:
            db = next(get_db())
            try:
                auth = AuthService(db)
                
                # Special case: password creation endpoint is only public if no password exists
                if path == "/api/auth/settings/password/create" and not auth.has_password():
                    if not is_quiet:
                        print(f"Password creation allowed - no password set")
                    return await call_next(request)
                
                # If no password is set, allow all access
                if not auth.has_password():
                    if not is_quiet:
                        print(f"No password set, allowing {path}")
                    return await call_next(request)
            finally:
                db.close()  # Always close the database connection
            
            if not is_quiet:
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
            
            # Refresh token (sliding window) - but not for background/automated requests
            should_refresh_token = not any(path.startswith(bg_path) for bg_path in self.NO_TOKEN_REFRESH_PATHS)
            if should_refresh_token:
                token_service.refresh_token(token)
            elif not is_quiet:
                print(f"[Middleware] Skipping token refresh for background path: {path}")
            
            # Set encryption key for this request
            encryption_info = token_service.get_encryption_info(token)
            if not is_quiet:
                print(f"[Middleware] Got encryption info: {encryption_info is not None}")
            if encryption_info:
                password, salt = encryption_info
                if not is_quiet:
                    print(f"[Middleware] Setting encryption key for path: {path}")
                set_encryption_key(password, salt)
            else:
                if not is_quiet:
                    print(f"[Middleware] No encryption info found for token")
            
            # Continue with request
            response = await call_next(request)
            
            # Optionally add refreshed token to response header
            # This allows client to update token if needed
            # response.headers["X-New-Token"] = token
            
            return response
            
        except Exception as e:
            if not is_quiet:
                print(f"Auth middleware error: {e}")
            # On error, allow request to continue
            # The individual endpoints will handle auth if needed
            return await call_next(request)