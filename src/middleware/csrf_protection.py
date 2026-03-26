# src/middleware/csrf_protection.py
"""
CSRF Protection Middleware for Etherion Platform

Implements Cross-Site Request Forgery (CSRF) protection using:
- Double Submit Cookie pattern
- Token-based validation
- Secure token generation and validation
- Integration with authentication system
"""

import secrets
import hashlib
import hmac
import time
from typing import Optional, Dict, Any
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# CSRF Configuration
CSRF_TOKEN_LENGTH = 32
CSRF_TOKEN_EXPIRY = 3600  # 1 hour
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_SECURE = True  # Set to True in production with HTTPS
CSRF_COOKIE_HTTPONLY = False  # Must be False for JavaScript access
CSRF_COOKIE_SAMESITE = "strict"

class CSRFProtection:
    """CSRF Protection middleware for FastAPI applications."""
    
    def __init__(self, secret_key: str):
        """
        Initialize CSRF protection.
        
        Args:
            secret_key: Secret key for token signing
        """
        self.secret_key = secret_key.encode('utf-8')
        self.token_cache: Dict[str, Dict[str, Any]] = {}
    
    def generate_csrf_token(self, user_id: str, session_id: str) -> str:
        """
        Generate a CSRF token for a user session.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            
        Returns:
            CSRF token string
        """
        # Generate random token
        random_token = secrets.token_urlsafe(CSRF_TOKEN_LENGTH)
        
        # Create payload
        payload = f"{user_id}:{session_id}:{random_token}:{int(time.time())}"
        
        # Sign the payload
        signature = hmac.new(
            self.secret_key,
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Combine payload and signature
        token = f"{payload}:{signature}"
        
        # Cache the token
        self.token_cache[token] = {
            "user_id": user_id,
            "session_id": session_id,
            "created_at": time.time(),
            "expires_at": time.time() + CSRF_TOKEN_EXPIRY
        }
        
        logger.info(f"Generated CSRF token for user {user_id}")
        return token
    
    def validate_csrf_token(self, token: str, user_id: str, session_id: str) -> bool:
        """
        Validate a CSRF token.
        
        Args:
            token: CSRF token to validate
            user_id: User identifier
            session_id: Session identifier
            
        Returns:
            True if token is valid, False otherwise
        """
        if not token:
            return False
        
        try:
            # Check if token is in cache
            if token not in self.token_cache:
                logger.warning(f"CSRF token not found in cache: {token[:10]}...")
                return False
            
            cached_data = self.token_cache[token]
            
            # Check expiration
            if time.time() > cached_data["expires_at"]:
                logger.warning(f"CSRF token expired: {token[:10]}...")
                del self.token_cache[token]
                return False
            
            # Verify user and session match
            if (cached_data["user_id"] != user_id or 
                cached_data["session_id"] != session_id):
                logger.warning(f"CSRF token user/session mismatch: {token[:10]}...")
                return False
            
            # Verify token signature
            parts = token.split(':')
            if len(parts) != 5:
                logger.warning(f"Invalid CSRF token format: {token[:10]}...")
                return False
            
            payload = ':'.join(parts[:4])
            signature = parts[4]
            
            expected_signature = hmac.new(
                self.secret_key,
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning(f"CSRF token signature mismatch: {token[:10]}...")
                return False
            
            logger.info(f"CSRF token validated successfully for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating CSRF token: {str(e)}")
            return False
    
    def cleanup_expired_tokens(self):
        """Remove expired tokens from cache."""
        current_time = time.time()
        expired_tokens = [
            token for token, data in self.token_cache.items()
            if current_time > data["expires_at"]
        ]
        
        for token in expired_tokens:
            del self.token_cache[token]
        
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired CSRF tokens")
    
    def revoke_user_tokens(self, user_id: str):
        """Revoke all CSRF tokens for a user."""
        user_tokens = [
            token for token, data in self.token_cache.items()
            if data["user_id"] == user_id
        ]
        
        for token in user_tokens:
            del self.token_cache[token]
        
        if user_tokens:
            logger.info(f"Revoked {len(user_tokens)} CSRF tokens for user {user_id}")

# Global CSRF protection instance
csrf_protection: Optional[CSRFProtection] = None

def initialize_csrf_protection(secret_key: str):
    """Initialize global CSRF protection instance."""
    global csrf_protection
    csrf_protection = CSRFProtection(secret_key)
    logger.info("CSRF protection initialized")

def get_csrf_protection() -> CSRFProtection:
    """Get the global CSRF protection instance."""
    if csrf_protection is None:
        raise RuntimeError("CSRF protection not initialized")
    return csrf_protection

async def csrf_protection_middleware(request: Request, call_next):
    """
    CSRF protection middleware for FastAPI.
    
    Validates CSRF tokens for state-changing operations.
    """
    # Skip CSRF validation for safe methods
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        response = await call_next(request)
        return response
    
    # Skip CSRF validation for authentication endpoints (they have their own protection)
    if request.url.path.startswith("/auth/") or request.url.path.startswith("/graphql"):
        response = await call_next(request)
        return response
    
    try:
        # Get CSRF token from header
        csrf_token = request.headers.get(CSRF_HEADER_NAME)
        
        # Get user and session information from request
        user_id = getattr(request.state, 'user_id', None)
        session_id = getattr(request.state, 'session_id', None)
        
        if not user_id or not session_id:
            logger.warning("CSRF validation failed: missing user_id or session_id")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "CSRF validation failed", "message": "Missing authentication"}
            )
        
        # Validate CSRF token
        if not csrf_protection.validate_csrf_token(csrf_token, user_id, session_id):
            logger.warning(f"CSRF validation failed for user {user_id}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "CSRF validation failed", "message": "Invalid or missing CSRF token"}
            )
        
        # Continue with request
        response = await call_next(request)
        return response
        
    except Exception as e:
        logger.error(f"CSRF middleware error: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "CSRF validation error", "message": "Internal server error"}
        )

def set_csrf_cookie(response: Response, token: str):
    """
    Set CSRF token as a cookie in the response.
    
    Args:
        response: FastAPI response object
        token: CSRF token to set
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=CSRF_TOKEN_EXPIRY,
        secure=CSRF_COOKIE_SECURE,
        httponly=CSRF_COOKIE_HTTPONLY,
        samesite=CSRF_COOKIE_SAMESITE,
        path="/"
    )

def get_csrf_token_from_cookie(request: Request) -> Optional[str]:
    """
    Get CSRF token from cookie.
    
    Args:
        request: FastAPI request object
        
    Returns:
        CSRF token if found, None otherwise
    """
    return request.cookies.get(CSRF_COOKIE_NAME)

# Utility functions for GraphQL integration
def generate_csrf_token_for_user(user_id: str, session_id: str) -> str:
    """Generate CSRF token for a user (for use in GraphQL mutations)."""
    return get_csrf_protection().generate_csrf_token(user_id, session_id)

def validate_csrf_token_for_user(token: str, user_id: str, session_id: str) -> bool:
    """Validate CSRF token for a user (for use in GraphQL mutations)."""
    return get_csrf_protection().validate_csrf_token(token, user_id, session_id)

def revoke_csrf_tokens_for_user(user_id: str):
    """Revoke all CSRF tokens for a user (for logout)."""
    get_csrf_protection().revoke_user_tokens(user_id)

# Decorator for GraphQL mutations that require CSRF protection
def require_csrf_token(func):
    """
    Decorator to require CSRF token validation for GraphQL mutations.
    
    Usage:
        @require_csrf_token
        def some_mutation(info, csrf_token: str, ...):
            # Mutation implementation
    """
    def wrapper(*args, **kwargs):
        # Extract GraphQL info and csrf_token
        info = None
        csrf_token = None
        
        for arg in args:
            if hasattr(arg, 'context'):  # GraphQL info object
                info = arg
                break
        
        if 'csrf_token' in kwargs:
            csrf_token = kwargs['csrf_token']
        
        if not info or not csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token required"
            )
        
        # Get user and session from GraphQL context
        user_id = getattr(info.context, 'user_id', None)
        session_id = getattr(info.context, 'session_id', None)
        
        if not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authentication required for CSRF validation"
            )
        
        # Validate CSRF token
        if not validate_csrf_token_for_user(csrf_token, user_id, session_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token"
            )
        
        # Call the original function
        return func(*args, **kwargs)
    
    return wrapper
