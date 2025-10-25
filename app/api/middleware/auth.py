"""Authentication middleware for API requests."""

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.tokens import token_service
from app.services.auth_service import AuthService
from app.services.maintenance_mode import maintenance_service
from app.models.database import SafeSession
from app.utils.encryption import set_encryption_key
from app.core.config import API_PREFIX, V1_API_PREFIX


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check authentication on protected routes."""
    
    # Paths that don't require authentication
    PUBLIC_PATHS = [
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/auth/status",
        "/static/",  # CSS/JS files needed for login page
        "/favicon.ico",
    ]
    
    # Paths to suppress verbose logging for (frequent polling endpoints)
    QUIET_PATHS = [
        f"{API_PREFIX}/notes/check-updates",
        f"{API_PREFIX}/notes/acquire-lock",
        f"{API_PREFIX}/notes/release-lock",
        f"{API_PREFIX}/auth/status",
    ]
    
    # Background/automated paths that should NOT refresh tokens (not user activity)
    NO_TOKEN_REFRESH_PATHS = [
        f"{API_PREFIX}/notes/check-updates",
        f"{API_PREFIX}/notes/acquire-lock",
        f"{API_PREFIX}/notes/release-lock",
        f"{API_PREFIX}/auth/status",  # ConnectivityMonitor pings this every 2 seconds
    ]
    
    # Note: /api/notes/* paths are NOT in this list - they require auth when password is set
    
    async def dispatch(self, request: Request, call_next):
        """Check authentication for protected routes."""
        path = request.url.path

        # Block any v1 API usage with an explicit 410 Gone (no DB access)
        if path.startswith('/api') and not (path.startswith(API_PREFIX) or path == API_PREFIX):
            ref = request.headers.get('referer', '-')
            ua = request.headers.get('user-agent', '-')
            print(f"V1 API call blocked: path={path} referer={ref} ua={ua}")
            raise RuntimeError(f"V1 API disabled: {path}")
        
        # Check if maintenance mode is active first
        if maintenance_service.is_active():
            # Allow access to maintenance page itself
            if path == "/maintenance":
                return await call_next(request)
            
            # Redirect all other requests to maintenance page
            return RedirectResponse(url="/maintenance", status_code=302)
        
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
        
        # Check if password is required (v1 disabled; only v2 status is public)
        try:
            db = SafeSession()
            try:
                auth = AuthService(db)

                # Special case: password creation endpoint is only public if no password exists
                if path in {"/api/auth/settings/password/create", f"{API_PREFIX}/auth/settings/password/create"} and not auth.has_password():
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
        except Exception as e:
            # Fail fast for internal errors
            raise

        token = authorization.split()[1] if authorization and authorization.lower().startswith("bearer ") else None
        if token:
            # Refresh token on user-initiated paths only
            if not any(path.startswith(p) for p in self.NO_TOKEN_REFRESH_PATHS):
                token_service.refresh_token(token)
        
        return await call_next(request)

