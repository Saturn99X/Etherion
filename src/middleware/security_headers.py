# src/middleware/security_headers.py
"""
Security Headers Middleware for Etherion Platform

Implements comprehensive security headers to protect against:
- Cross-Site Scripting (XSS)
- Clickjacking attacks
- MIME type sniffing
- Protocol downgrade attacks
- Information disclosure
- Content injection attacks
"""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# Security Headers Configuration
SECURITY_HEADERS = {
    # Content Security Policy - Prevents XSS and code injection
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.openai.com https://api.anthropic.com wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "media-src 'self'; "
        "worker-src 'self'; "
        "manifest-src 'self'; "
        "upgrade-insecure-requests"
    ),
    
    # X-Frame-Options - Prevents clickjacking
    "X-Frame-Options": "DENY",
    
    # X-Content-Type-Options - Prevents MIME type sniffing
    "X-Content-Type-Options": "nosniff",
    
    # X-XSS-Protection - Enables XSS filtering (legacy browsers)
    "X-XSS-Protection": "1; mode=block",
    
    # Referrer-Policy - Controls referrer information
    "Referrer-Policy": "strict-origin-when-cross-origin",
    
    # Permissions-Policy - Controls browser features
    "Permissions-Policy": (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "payment=(), "
        "usb=(), "
        "magnetometer=(), "
        "gyroscope=(), "
        "accelerometer=(), "
        "ambient-light-sensor=(), "
        "autoplay=(), "
        "battery=(), "
        "bluetooth=(), "
        "clipboard-read=(), "
        "clipboard-write=(), "
        "display-capture=(), "
        "fullscreen=(self), "
        "gamepad=(), "
        "hid=(), "
        "idle-detection=(), "
        "local-fonts=(), "
        "midi=(), "
        "nfc=(), "
        "notifications=(), "
        "persistent-storage=(), "
        "publickey-credentials-get=(), "
        "screen-wake-lock=(), "
        "serial=(), "
        "speaker-selection=(), "
        "storage-access=(), "
        "sync-xhr=(), "
        "unload=(), "
        "usb=(), "
        "web-share=(), "
        "xr-spatial-tracking=()"
    ),
    
    # Cross-Origin-Embedder-Policy - Controls cross-origin embedding
    "Cross-Origin-Embedder-Policy": "require-corp",
    
    # Cross-Origin-Opener-Policy - Controls cross-origin window access
    "Cross-Origin-Opener-Policy": "same-origin",
    
    # Cross-Origin-Resource-Policy - Controls cross-origin resource access
    "Cross-Origin-Resource-Policy": "same-origin",
    
    # Strict-Transport-Security - Enforces HTTPS (only in production)
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    
    # Cache-Control - Prevents caching of sensitive content
    "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
    
    # Pragma - Legacy cache control
    "Pragma": "no-cache",
    
    # Expires - Legacy cache control
    "Expires": "0",
    
    # X-Permitted-Cross-Domain-Policies - Controls cross-domain policies
    "X-Permitted-Cross-Domain-Policies": "none",
    
    # X-Download-Options - Prevents IE from executing downloads
    "X-Download-Options": "noopen",
    
    # X-DNS-Prefetch-Control - Controls DNS prefetching
    "X-DNS-Prefetch-Control": "off",
    
    # Expect-CT - Certificate Transparency (deprecated but still useful)
    "Expect-CT": "max-age=86400, enforce",
    
    # Feature-Policy - Controls browser features (legacy)
    "Feature-Policy": (
        "geolocation 'none'; "
        "microphone 'none'; "
        "camera 'none'; "
        "payment 'none'; "
        "usb 'none'; "
        "magnetometer 'none'; "
        "gyroscope 'none'; "
        "accelerometer 'none'; "
        "ambient-light-sensor 'none'; "
        "autoplay 'none'; "
        "battery 'none'; "
        "bluetooth 'none'; "
        "clipboard-read 'none'; "
        "clipboard-write 'none'; "
        "display-capture 'none'; "
        "fullscreen 'self'; "
        "gamepad 'none'; "
        "hid 'none'; "
        "idle-detection 'none'; "
        "local-fonts 'none'; "
        "midi 'none'; "
        "nfc 'none'; "
        "notifications 'none'; "
        "persistent-storage 'none'; "
        "publickey-credentials-get 'none'; "
        "screen-wake-lock 'none'; "
        "serial 'none'; "
        "speaker-selection 'none'; "
        "storage-access 'none'; "
        "sync-xhr 'none'; "
        "unload 'none'; "
        "usb 'none'; "
        "web-share 'none'; "
        "xr-spatial-tracking 'none'"
    )
}

# Development-specific headers (less restrictive for development)
DEVELOPMENT_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.openai.com https://api.anthropic.com wss: ws:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "Strict-Transport-Security": "",  # Disabled in development
    "Expect-CT": "",  # Disabled in development
}

def get_security_headers(is_production: bool = True) -> dict:
    """
    Get security headers based on environment.
    
    Args:
        is_production: Whether running in production environment
        
    Returns:
        Dictionary of security headers
    """
    if is_production:
        return SECURITY_HEADERS.copy()
    else:
        # Merge development headers with production headers
        headers = SECURITY_HEADERS.copy()
        headers.update(DEVELOPMENT_HEADERS)
        # Remove empty headers
        headers = {k: v for k, v in headers.items() if v}
        return headers

async def security_headers_middleware(request: Request, call_next):
    """
    Security headers middleware for FastAPI.
    
    Adds comprehensive security headers to all responses.
    """
    try:
        # Determine if we're in production
        is_production = request.url.scheme == "https" or "localhost" not in str(request.url)
        
        # Get appropriate security headers
        security_headers = get_security_headers(is_production)
        
        # Process the request
        response = await call_next(request)
        
        # Add security headers to response
        for header_name, header_value in security_headers.items():
            if header_value:  # Only add non-empty headers
                response.headers[header_name] = header_value
        
        # Add custom security headers based on request
        add_custom_security_headers(request, response)
        
        logger.debug(f"Added security headers to {request.method} {request.url.path}")
        return response
        
    except Exception as e:
        logger.error(f"Security headers middleware error: {str(e)}")
        # Return error response with security headers
        error_response = JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )
        
        # Add security headers to error response
        security_headers = get_security_headers(False)
        for header_name, header_value in security_headers.items():
            if header_value:
                error_response.headers[header_name] = header_value
        
        return error_response

def add_custom_security_headers(request: Request, response: Response):
    """
    Add custom security headers based on request context.
    
    Args:
        request: FastAPI request object
        response: FastAPI response object
    """
    # Add CORS headers for API endpoints
    if request.url.path.startswith("/api/") or request.url.path.startswith("/graphql"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-Token"
        response.headers["Access-Control-Max-Age"] = "86400"
    
    # Add API version header
    if request.url.path.startswith("/api/"):
        response.headers["API-Version"] = "1.0"
    
    # Add request ID for tracking
    request_id = getattr(request.state, 'request_id', None)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    
    # Add server information (minimal)
    response.headers["Server"] = "Etherion/1.0"
    
    # Add timing headers for performance monitoring
    if hasattr(request.state, 'start_time'):
        import time
        duration = time.time() - request.state.start_time
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

def create_csp_header(additional_directives: dict = None) -> str:
    """
    Create a custom Content Security Policy header.
    
    Args:
        additional_directives: Additional CSP directives to include
        
    Returns:
        CSP header value string
    """
    base_csp = SECURITY_HEADERS["Content-Security-Policy"]
    
    if additional_directives:
        for directive, value in additional_directives.items():
            base_csp += f"; {directive} {value}"
    
    return base_csp

def create_hsts_header(max_age: int = 31536000, include_subdomains: bool = True, preload: bool = True) -> str:
    """
    Create a custom Strict-Transport-Security header.
    
    Args:
        max_age: Maximum age in seconds (default: 1 year)
        include_subdomains: Whether to include subdomains
        preload: Whether to include preload directive
        
    Returns:
        HSTS header value string
    """
    hsts = f"max-age={max_age}"
    
    if include_subdomains:
        hsts += "; includeSubDomains"
    
    if preload:
        hsts += "; preload"
    
    return hsts

# Utility functions for specific security scenarios
def add_cors_headers(response: Response, allowed_origins: list = None, allowed_methods: list = None):
    """
    Add CORS headers to response.
    
    Args:
        response: FastAPI response object
        allowed_origins: List of allowed origins (default: ["*"])
        allowed_methods: List of allowed methods (default: ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    """
    if allowed_origins is None:
        allowed_origins = ["*"]
    
    if allowed_methods is None:
        allowed_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    
    response.headers["Access-Control-Allow-Origin"] = ", ".join(allowed_origins)
    response.headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-Token"
    response.headers["Access-Control-Max-Age"] = "86400"

def add_cache_control_headers(response: Response, cache_control: str = "no-store, no-cache, must-revalidate"):
    """
    Add cache control headers to response.
    
    Args:
        response: FastAPI response object
        cache_control: Cache control directive
    """
    response.headers["Cache-Control"] = cache_control
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

def add_security_headers_to_response(response: Response, is_production: bool = True):
    """
    Add all security headers to a response object.
    
    Args:
        response: FastAPI response object
        is_production: Whether running in production
    """
    security_headers = get_security_headers(is_production)
    
    for header_name, header_value in security_headers.items():
        if header_value:
            response.headers[header_name] = header_value
