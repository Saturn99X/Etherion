"""
Security integration module that ties together all security components.
Provides a unified interface for security features across the application.
"""

import hashlib
import logging
from typing import Optional, Dict, Any
import os
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

from src.auth.jwt import decode_access_token
from src.middleware.rate_limiter import (
    rate_limit_middleware,
    graphql_rate_limit_middleware,
    check_rate_limit
)
from src.middleware.authorization import (
    authorization_middleware,
    get_authorization_context,
    AuthorizationContext,
    Role
)
from src.middleware.csrf_protection import (
    csrf_protection_middleware,
    initialize_csrf_protection,
    get_csrf_protection
)
from src.middleware.security_headers import (
    security_headers_middleware,
    add_security_headers_to_response
)
from src.core.security.audit_logger import (
    log_authentication_success,
    log_authentication_failure,
    log_authorization_failure,
    log_security_violation,
    log_rate_limit_exceeded,
    log_input_validation_failure,
    log_data_access
)

logger = logging.getLogger(__name__)


class SecurityManager:
    """
    Centralized security manager that coordinates all security features.
    """
    
    def __init__(self):
        self.rate_limiting_enabled = True
        self.authorization_enabled = True
        self.audit_logging_enabled = True
        self.csrf_protection_enabled = True
        self.security_headers_enabled = True
    
    async def process_request(self, request: Request, call_next):
        """
        Process incoming request through all security layers.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware in chain
            
        Returns:
            Response: Processed response
        """
        try:
            path = request.url.path or ""
            bearer_authenticated = False

            # Hydrate request state from Authorization header if not already populated
            auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
            has_bearer_header = bool(auth_header and auth_header.lower().startswith("bearer "))
            if has_bearer_header:
                token = auth_header.split(" ", 1)[1].strip()
                if token:
                    try:
                        token_data = decode_access_token(token)
                        bearer_authenticated = True
                        if not getattr(request.state, "user_id", None) and token_data.user_id:
                            request.state.user_id = token_data.user_id
                        if not getattr(request.state, "tenant_id", None) and token_data.tenant_id is not None:
                            request.state.tenant_id = token_data.tenant_id
                        if not getattr(request.state, "session_id", None):
                            request.state.session_id = hashlib.sha256(token.encode()).hexdigest()
                    except Exception:
                        # Authorization middleware will handle invalid tokens later.
                        pass

            # 1) CSRF protection (pre-call) for state-changing operations
            if self.csrf_protection_enabled and request.method not in ("GET", "HEAD", "OPTIONS"):
                # Skip CSRF for auth, GraphQL, and webhook endpoints (webhooks use provider signatures)
                # Also skip CSRF for any request that presents a Bearer token header (even if invalid),
                # which mitigates CSRF by requiring an Authorization header.
                if not (path.startswith("/auth/") or path.startswith("/api/tui/auth/") or path.startswith("/graphql") or path.startswith("/webhook/") or has_bearer_header):
                    try:
                        from src.middleware.csrf_protection import get_csrf_protection, CSRF_HEADER_NAME
                        csrf = get_csrf_protection()
                        csrf_token = request.headers.get(CSRF_HEADER_NAME)
                        user_id = getattr(request.state, "user_id", None)
                        session_id = getattr(request.state, "session_id", None)
                        if not user_id or not session_id or not csrf.validate_csrf_token(csrf_token, user_id, session_id):
                            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
                    except HTTPException:
                        raise
                    except Exception:
                        # On unexpected CSRF validation errors, fail closed
                        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CSRF validation error")

            # 2) Rate limiting (pre-call)
            endpoint_type = None
            if self.rate_limiting_enabled:
                try:
                    from src.middleware.rate_limiter import check_rate_limit, get_graphql_operation_type
                    if path.startswith("/auth/") or path.startswith("/login") or path.startswith("/oauth"):
                        endpoint_type = "auth_endpoints"
                    elif path.startswith("/graphql"):
                        try:
                            body = await request.body()
                            endpoint_type = get_graphql_operation_type(body.decode())
                        except Exception:
                            endpoint_type = "graphql_queries"
                    else:
                        endpoint_type = "default"
                    await check_rate_limit(request, endpoint_type)
                except HTTPException as e:
                    if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                        if self.audit_logging_enabled:
                            await self._log_rate_limit_exceeded(request, e)
                        return JSONResponse(status_code=e.status_code, content=e.detail, headers=e.headers)
                    raise
                except Exception:
                    # If rate limiter backend fails, allow request to proceed
                    endpoint_type = endpoint_type or "default"

            # 3) Authorization (pre-call) for protected endpoints
            if self.authorization_enabled:
                public_endpoints = ["/health", "/docs", "/openapi.json", "/auth/login", "/auth/oauth", "/oauth", "/webhook/", "/api/tui/auth/"]
                is_public = (path == "/") or any(path.startswith(ep) for ep in public_endpoints)
                # Dev-only: allow LES helper endpoints without Authorization header
                try:
                    if os.getenv("DEV_BYPASS_AUTH", "0") == "1":
                        if path.startswith("/__dev/") or path == "/__dev/bypass-token":
                            is_public = True
                except Exception:
                    pass
                if not is_public and not path.startswith("/graphql"):
                    auth_header = request.headers.get("authorization")
                    if not auth_header or not auth_header.lower().startswith("bearer "):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authorization header required",
                            headers={"WWW-Authenticate": "Bearer"},
                        )

            # 4) Proceed downstream once
            response = await call_next(request)

            # 5) Security headers (post-call)
            if self.security_headers_enabled:
                try:
                    from src.middleware.security_headers import add_security_headers_to_response
                    is_production = request.url.scheme == "https" or "localhost" not in str(request.url)
                    add_security_headers_to_response(response, is_production=is_production)
                except Exception:
                    # Do not fail the request for header injection errors
                    pass

            # 6) Add informational rate-limit headers (post-call)
            if self.rate_limiting_enabled:
                try:
                    from src.middleware.rate_limiter import RATE_LIMIT_CONFIG
                    et = endpoint_type or "default"
                    config = RATE_LIMIT_CONFIG.get(et, RATE_LIMIT_CONFIG["default"])
                    response.headers["X-RateLimit-Limit-Minute"] = str(config["requests_per_minute"])
                    response.headers["X-RateLimit-Limit-Hour"] = str(config["requests_per_hour"])
                    response.headers.setdefault("X-RateLimit-Limit", str(config["requests_per_minute"]))
                except Exception:
                    pass

            return response

        except HTTPException as e:
            if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                # Log rate limit exceeded
                if self.audit_logging_enabled:
                    await self._log_rate_limit_exceeded(request, e)
                return JSONResponse(
                    status_code=e.status_code,
                    content=e.detail,
                    headers=getattr(e, "headers", None) or {}
                )
            raise
    
    async def _log_rate_limit_exceeded(self, request: Request, exception: HTTPException):
        """Log rate limit exceeded event."""
        try:
            client_ip = self._get_client_ip(request)
            user_agent = request.headers.get("user-agent", "unknown")
            
            await log_rate_limit_exceeded(
                ip_address=client_ip,
                user_agent=user_agent,
                endpoint=request.url.path,
                method=request.method,
                limit_type="requests",
                limit_value=100,  # Would be extracted from exception
                current_count=101,  # Would be extracted from exception
                details={"exception": str(exception.detail)}
            )
        except Exception as e:
            logger.error(f"Failed to log rate limit exceeded: {str(e)}")
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded IP (from load balancer/proxy)
        if "x-forwarded-for" in request.headers:
            return request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            return request.headers["x-real-ip"]
        else:
            return request.client.host if request.client else "unknown"
    
    async def validate_authentication(self, request: Request) -> Optional[AuthorizationContext]:
        """
        Validate authentication and return authorization context.
        
        Args:
            request: FastAPI request object
            
        Returns:
            AuthorizationContext: If authentication is valid
            None: If authentication is not required or failed
        """
        if not self.authorization_enabled:
            return None
        
        try:
            # Skip authentication for public endpoints
            public_endpoints = ["/health", "/docs", "/openapi.json", "/auth/login", "/auth/oauth", "/oauth"]
            if any(request.url.path.startswith(endpoint) for endpoint in public_endpoints):
                return None
            
            # For GraphQL, authentication is handled in resolvers
            if request.url.path.startswith("/graphql"):
                return None
            
            # Check for authorization header
            auth_header = request.headers.get("authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authorization header required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Extract token from authorization header
            token = auth_header.split(" ")[1] if len(auth_header.split(" ")) > 1 else None
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization header format",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Proper token validation and authorization context
            from src.auth.jwt import decode_access_token
            from src.database.db import get_session
            from src.database.models import User, Tenant
            token_data = decode_access_token(token)
            if not token_data or not token_data.user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Use unscoped session for auth lookup
            with get_session(None) as session:
                user = session.query(User).filter(User.user_id == token_data.user_id).first()
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                tenant = session.query(Tenant).filter(Tenant.id == user.tenant_id).first()
                if not tenant:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Tenant not found",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            # Build authorization context (default role USER; RBAC can be extended)
            return AuthorizationContext(user=user, tenant=tenant, role=Role.USER)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication validation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication validation failed"
            )
    
    async def log_security_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        Log security events through the audit system.
        
        Args:
            event_type: Type of security event
            user_id: User ID (if available)
            tenant_id: Tenant ID (if available)
            ip_address: Client IP address
            user_agent: Client user agent
            endpoint: API endpoint
            method: HTTP method
            details: Additional event details
            success: Whether the event was successful
            error_message: Error message (if applicable)
        """
        if not self.audit_logging_enabled:
            return
        
        try:
            if event_type == "authentication_success":
                await log_authentication_success(
                    user_id=user_id or "unknown",
                    tenant_id=tenant_id or "unknown",
                    ip_address=ip_address or "unknown",
                    user_agent=user_agent or "unknown",
                    details=details or {}
                )
            elif event_type == "authentication_failure":
                await log_authentication_failure(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    ip_address=ip_address or "unknown",
                    user_agent=user_agent or "unknown",
                    reason=error_message or "Authentication failed",
                    details=details or {}
                )
            elif event_type == "authorization_failure":
                await log_authorization_failure(
                    user_id=user_id or "unknown",
                    tenant_id=tenant_id or "unknown",
                    ip_address=ip_address or "unknown",
                    user_agent=user_agent or "unknown",
                    endpoint=endpoint or "unknown",
                    method=method or "unknown",
                    reason=error_message or "Authorization failed",
                    details=details or {}
                )
            elif event_type == "security_violation":
                await log_security_violation(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    ip_address=ip_address or "unknown",
                    user_agent=user_agent or "unknown",
                    endpoint=endpoint or "unknown",
                    method=method or "unknown",
                    violation_type=details.get("violation_type", "unknown") if details else "unknown",
                    details=details or {}
                )
            elif event_type == "data_access":
                await log_data_access(
                    user_id=user_id or "unknown",
                    tenant_id=tenant_id or "unknown",
                    ip_address=ip_address or "unknown",
                    user_agent=user_agent or "unknown",
                    endpoint=endpoint or "unknown",
                    method=method or "unknown",
                    data_type=details.get("data_type", "unknown") if details else "unknown",
                    operation=details.get("operation", "unknown") if details else "unknown",
                    details=details or {}
                )
            elif event_type == "input_validation_failure":
                await log_input_validation_failure(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    ip_address=ip_address or "unknown",
                    user_agent=user_agent or "unknown",
                    endpoint=endpoint or "unknown",
                    method=method or "unknown",
                    validation_errors=details.get("validation_errors", []) if details else [],
                    input_data=details.get("input_data", {}) if details else {}
                )
            else:
                logger.warning(f"Unknown security event type: {event_type}")
                
        except Exception as e:
            logger.error(f"Failed to log security event {event_type}: {str(e)}")
    
    def configure_security(
        self,
        rate_limiting: bool = True,
        authorization: bool = True,
        audit_logging: bool = True,
        csrf_protection: bool = True,
        security_headers: bool = True
    ):
        """
        Configure security features.
        
        Args:
            rate_limiting: Enable/disable rate limiting
            authorization: Enable/disable authorization
            audit_logging: Enable/disable audit logging
            csrf_protection: Enable/disable CSRF protection
            security_headers: Enable/disable security headers
        """
        self.rate_limiting_enabled = rate_limiting
        self.authorization_enabled = authorization
        self.audit_logging_enabled = audit_logging
        self.csrf_protection_enabled = csrf_protection
        self.security_headers_enabled = security_headers
        
        logger.info(f"Security configuration updated: rate_limiting={rate_limiting}, "
                   f"authorization={authorization}, audit_logging={audit_logging}, "
                   f"csrf_protection={csrf_protection}, security_headers={security_headers}")


# Global security manager instance
security_manager = SecurityManager()


def initialize_security_system(secret_key: str):
    """
    Initialize all security components.
    
    Args:
        secret_key: Secret key for CSRF protection and other security features
    """
    try:
        # Initialize CSRF protection
        initialize_csrf_protection(secret_key)
        
        logger.info("Security system initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize security system: {str(e)}")
        raise


# Convenience functions for common security operations
async def secure_request_handler(request: Request, call_next):
    """
    Secure request handler that applies all security layers.
    
    Args:
        request: FastAPI request object
        call_next: Next middleware in chain
        
    Returns:
        Response: Processed response
    """
    return await security_manager.process_request(request, call_next)


async def log_authentication_event(
    success: bool,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    request: Optional[Request] = None,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None
):
    """
    Log authentication events.
    
    Args:
        success: Whether authentication was successful
        user_id: User ID
        tenant_id: Tenant ID
        request: FastAPI request object
        details: Additional details
        error_message: Error message (if authentication failed)
    """
    ip_address = None
    user_agent = None
    
    if request:
        ip_address = security_manager._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
    
    event_type = "authentication_success" if success else "authentication_failure"
    
    await security_manager.log_security_event(
        event_type=event_type,
        user_id=user_id,
        tenant_id=tenant_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        success=success,
        error_message=error_message
    )


async def log_authorization_event(
    success: bool,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    request: Optional[Request] = None,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None
):
    """
    Log authorization events.
    
    Args:
        success: Whether authorization was successful
        user_id: User ID
        tenant_id: Tenant ID
        request: FastAPI request object
        endpoint: API endpoint
        method: HTTP method
        details: Additional details
        error_message: Error message (if authorization failed)
    """
    ip_address = None
    user_agent = None
    
    if request:
        ip_address = security_manager._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        if not endpoint:
            endpoint = request.url.path
        if not method:
            method = request.method
    
    event_type = "authorization_success" if success else "authorization_failure"
    
    await security_manager.log_security_event(
        event_type=event_type,
        user_id=user_id,
        tenant_id=tenant_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        details=details,
        success=success,
        error_message=error_message
    )


async def log_security_violation_event(
    violation_type: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    request: Optional[Request] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    Log security violation events.
    
    Args:
        violation_type: Type of security violation
        user_id: User ID
        tenant_id: Tenant ID
        request: FastAPI request object
        details: Additional details
    """
    ip_address = None
    user_agent = None
    endpoint = None
    method = None
    
    if request:
        ip_address = security_manager._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        endpoint = request.url.path
        method = request.method
    
    violation_details = details or {}
    violation_details["violation_type"] = violation_type
    
    await security_manager.log_security_event(
        event_type="security_violation",
        user_id=user_id,
        tenant_id=tenant_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        details=violation_details,
        success=False,
        error_message=f"Security violation: {violation_type}"
    )
