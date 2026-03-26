# src/etherion_ai/middleware/versioning.py
"""
API versioning middleware for header-based versioning.
"""

import logging
from typing import Optional, Tuple
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Supported API versions
SUPPORTED_VERSIONS = {
    "v0.5": "0.5.0",
    "v1.0": "1.0.0"
}

# Default version
DEFAULT_VERSION = "v0.5"


def parse_version_header(request: Request) -> Tuple[str, str]:
    """
    Parse the version header from the request.
    
    Args:
        request: Incoming request
        
    Returns:
        Tuple[str, str]: Parsed version and full version string
        
    Raises:
        HTTPException: If version is not supported
    """
    # Get the Accept-Version header
    version_header = request.headers.get("Accept-Version")
    
    # If no version header, use default
    if not version_header:
        logger.info(f"No version header provided, using default version: {DEFAULT_VERSION}")
        return DEFAULT_VERSION, SUPPORTED_VERSIONS[DEFAULT_VERSION]
    
    # Check if version is supported
    if version_header not in SUPPORTED_VERSIONS:
        logger.warning(f"Unsupported version requested: {version_header}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported API version: {version_header}. Supported versions: {', '.join(SUPPORTED_VERSIONS.keys())}"
        )
    
    logger.info(f"API version {version_header} requested")
    return version_header, SUPPORTED_VERSIONS[version_header]


async def versioning_middleware(request: Request, call_next):
    """
    Middleware to handle API versioning.
    
    Args:
        request: Incoming request
        call_next: Next middleware in the chain
        
    Returns:
        Response: Outgoing response
    """
    try:
        # Dev-only: bypass versioning for helper endpoints
        try:
            import os as _os
            _path = request.url.path or ""
            if _os.getenv("DEV_BYPASS_AUTH", "0") == "1" and (_path.startswith("/__dev/") or _path == "/__dev/bypass-token"):
                return await call_next(request)
        except Exception:
            pass
        # Parse version header
        version, full_version = parse_version_header(request)
        
        # Add version information to request state
        request.state.api_version = version
        request.state.api_full_version = full_version
        
        # Process the request and await downstream response
        response = await call_next(request)

        # Add version information to response headers
        response.headers["API-Version"] = version
        response.headers["API-Full-Version"] = full_version

        return response
    except HTTPException as e:
        # Handle versioning errors
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail}
        )
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Error in versioning middleware: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred in versioning middleware"}
        )