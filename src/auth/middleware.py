"""
Authentication middleware for FastAPI applications.
Handles token validation, session management, and user context.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.auth.jwt import decode_access_token, decode_refresh_token
from src.auth.models import TokenData
from src.auth.session_manager import get_session_manager, SessionManager
from src.database.db import get_session
from src.database.models import User, Tenant
from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)

# Security scheme for token validation
security = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for request processing."""
    
    def __init__(self, app, exclude_paths: Optional[list] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/auth/login",
            "/auth/register",
            "/auth/oauth",
            "/auth/callback",
            "/auth/refresh",
            "/auth/password-reset",
            "/auth/verify-email"
        ]
    
    async def dispatch(self, request: Request, call_next):
        """Process request through authentication middleware."""
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # Extract token from request
        token = self._extract_token(request)
        
        if not token:
            return Response(
                content='{"detail": "Authentication required"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        try:
            # Validate token and get user context
            user_context = await self._validate_token(token)
            if not user_context:
                return Response(
                    content='{"detail": "Invalid token"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json"
                )
            
            # Add user context to request state
            request.state.user = user_context.get("user")
            request.state.tenant = user_context.get("tenant")
            request.state.token_data = user_context.get("token_data")
            request.state.session = user_context.get("session")
            
            # Update session access time
            if user_context.get("session"):
                session_manager = await get_session_manager()
                await session_manager.update_session_access(user_context["session"].session_id)
            
        except HTTPException as e:
            return Response(
                content=f'{{"detail": "{e.detail}"}}',
                status_code=e.status_code,
                media_type="application/json"
            )
        except Exception as e:
            logger.error(f"Authentication middleware error: {e}")
            return Response(
                content='{"detail": "Authentication error"}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json"
            )
        
        return await call_next(request)
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract token from request headers or cookies."""
        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # Try cookie
        token = request.cookies.get("access_token")
        if token:
            return token
        
        return None
    
    async def _validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate token and return user context."""
        try:
            # Decode token
            token_data = decode_access_token(token)
            
            # Get user from database
            with get_session() as session:
                user = session.query(User).filter(User.user_id == token_data.user_id).first()
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found"
                    )
                
                # Get tenant if specified
                tenant = None
                if token_data.tenant_id:
                    tenant = session.query(Tenant).filter(Tenant.id == token_data.tenant_id).first()
                    if not tenant:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Tenant not found"
                        )
                
                # Check if user is active
                if not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User account is inactive"
                    )
            
            # Get session info if available
            session_info = None
            session_id = self._extract_session_id_from_token(token)
            if session_id:
                session_manager = await get_session_manager()
                session_info = await session_manager.get_session(session_id)
            
            return {
                "user": user,
                "tenant": tenant,
                "token_data": token_data,
                "session": session_info
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    def _extract_session_id_from_token(self, token: str) -> Optional[str]:
        """Extract session ID from token (if embedded)."""
        # This would depend on how you structure your tokens
        # For now, we'll return None as session ID is not embedded
        return None


# FastAPI dependencies for authentication
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """FastAPI dependency to get the current authenticated user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        token_data = decode_access_token(credentials.credentials)
        
        with get_session() as session:
            user = session.query(User).filter(User.user_id == token_data.user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is inactive"
                )
            
            return user
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def get_current_user_with_tenant(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> tuple[User, Optional[Tenant]]:
    """FastAPI dependency to get the current user and their tenant."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        token_data = decode_access_token(credentials.credentials)
        
        with get_session() as session:
            user = session.query(User).filter(User.user_id == token_data.user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is inactive"
                )
            
            tenant = None
            if token_data.tenant_id:
                tenant = session.query(Tenant).filter(Tenant.id == token_data.tenant_id).first()
                if not tenant:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Tenant not found"
                    )
            
            return user, tenant
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """FastAPI dependency to get the current user (optional authentication)."""
    if not credentials:
        return None
    
    try:
        token_data = decode_access_token(credentials.credentials)
        
        with get_session() as session:
            user = session.query(User).filter(User.user_id == token_data.user_id).first()
            if not user or not user.is_active:
                return None
            
            return user
            
    except Exception:
        return None


async def require_tenant_access(
    user: User = Depends(get_current_user),
    tenant: Optional[Tenant] = Depends(get_current_user_with_tenant)
) -> tuple[User, Tenant]:
    """FastAPI dependency that requires tenant access."""
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required"
        )
    
    return user, tenant


async def require_admin_access(
    user: User = Depends(get_current_user)
) -> User:
    """FastAPI dependency that requires admin access."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return user


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for API endpoints."""
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.redis_client = None
    
    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting to requests."""
        # Initialize Redis client if needed
        if not self.redis_client:
            self.redis_client = await get_redis_client()
        
        # Get client identifier (IP address or user ID)
        client_id = self._get_client_id(request)
        
        # Check rate limit
        if await self._is_rate_limited(client_id):
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json"
            )
        
        # Increment request count
        await self._increment_request_count(client_id)
        
        return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from request state (if authenticated)
        if hasattr(request.state, 'user') and request.state.user:
            return f"user:{request.state.user.user_id}"
        
        # Fall back to IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return f"ip:{forwarded_for.split(',')[0].strip()}"
        
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"
    
    async def _is_rate_limited(self, client_id: str) -> bool:
        """Check if client is rate limited."""
        key = f"rate_limit:{client_id}"
        current_count = await self.redis_client.get(key)
        
        if current_count and int(current_count) >= self.requests_per_minute:
            return True
        
        return False
    
    async def _increment_request_count(self, client_id: str) -> None:
        """Increment request count for client."""
        key = f"rate_limit:{client_id}"
        await self.redis_client.incr(key)
        await self.redis_client.expire(key, 60)  # 1 minute window

