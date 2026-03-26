# src/etherion_ai/middleware/error_handler.py
"""
Error handling middleware for consistent error responses.
"""

import logging
import uuid
import traceback
from typing import Any, Dict
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from strawberry.exceptions import StrawberryGraphQLError

from src.etherion_ai.exceptions import BaseEtherionException
from src.etherion_ai.utils.logging_utils import log_error

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def format_error_response(
    message: str,
    error_code: str,
    status_code: int,
    request_id: str,
    details: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Format a consistent error response.
    
    Args:
        message: Error message
        error_code: Error code
        status_code: HTTP status code
        request_id: Unique request identifier
        details: Additional error details
        
    Returns:
        Dict: Formatted error response
    """
    response = {
        "error": {
            "message": message,
            "code": error_code,
            "status": status_code,
            "request_id": request_id
        }
    }
    
    if details:
        response["error"]["details"] = details
        
    return response


async def error_handling_middleware(request: Request, call_next):
    """
    Middleware to handle errors and format consistent responses.
    
    Args:
        request: Incoming request
        call_next: Next middleware in the chain
        
    Returns:
        Response: Formatted response
    """
    try:
        response = await call_next(request)
        return response
    except BaseEtherionException as e:
        # Log the error with context
        log_error(
            request_id=e.request_id,
            error=e,
            context={
                "error_code": e.error_code,
                "status_code": e.status_code,
                "details": e.details
            }
        )
        
        # Return formatted error response
        return JSONResponse(
            status_code=e.status_code,
            content=format_error_response(
                message=e.message,
                error_code=e.error_code,
                status_code=e.status_code,
                request_id=e.request_id,
                details=e.details
            )
        )
    except HTTPException as e:
        # Handle FastAPI HTTP exceptions
        request_id = str(uuid.uuid4())
        
        # Log the error
        log_error(
            request_id=request_id,
            error=e,
            context={
                "error_code": "HTTP_ERROR",
                "status_code": e.status_code,
            }
        )
        
        # Return formatted error response
        return JSONResponse(
            status_code=e.status_code,
            content=format_error_response(
                message=e.detail,
                error_code="HTTP_ERROR",
                status_code=e.status_code,
                request_id=request_id
            )
        )
    except Exception as e:
        # Handle unexpected errors
        request_id = str(uuid.uuid4())
        
        # Log the error with traceback
        log_error(
            request_id=request_id,
            error=e,
            context={
                "error_code": "UNEXPECTED_ERROR",
                "status_code": 500,
                "traceback": traceback.format_exc()
            }
        )
        
        # Return generic error response
        return JSONResponse(
            status_code=500,
            content=format_error_response(
                message="An unexpected error occurred. Please try again later.",
                error_code="UNEXPECTED_ERROR",
                status_code=500,
                request_id=request_id
            )
        )


def format_graphql_error(error: StrawberryGraphQLError) -> Dict[str, Any]:
    """
    Format GraphQL errors with consistent structure.
    
    Args:
        error: Strawberry GraphQL error
        
    Returns:
        Dict: Formatted error
    """
    # Extract original exception if it exists
    original_error = error.original_error
    
    # Generate request ID
    request_id = str(uuid.uuid4())
    
    if isinstance(original_error, BaseEtherionException):
        # Log the error
        log_error(
            request_id=original_error.request_id,
            error=original_error,
            context={
                "error_code": original_error.error_code,
                "status_code": original_error.status_code,
                "details": original_error.details
            }
        )
        
        # Return formatted error
        return {
            "message": original_error.message,
            "code": original_error.error_code,
            "request_id": original_error.request_id,
            "details": original_error.details
        }
    elif isinstance(original_error, HTTPException):
        # Log the error
        log_error(
            request_id=request_id,
            error=original_error,
            context={
                "error_code": "HTTP_ERROR",
                "status_code": original_error.status_code,
            }
        )
        
        # Return formatted error
        return {
            "message": original_error.detail,
            "code": "HTTP_ERROR",
            "request_id": request_id
        }
    else:
        # Handle unexpected GraphQL errors
        log_error(
            request_id=request_id,
            error=original_error if original_error else error,
            context={
                "error_code": "UNEXPECTED_GRAPHQL_ERROR",
                "status_code": 500,
                "traceback": traceback.format_exc() if original_error else None
            }
        )
        
        # Return generic error
        return {
            "message": "An unexpected error occurred during GraphQL execution.",
            "code": "UNEXPECTED_GRAPHQL_ERROR",
            "request_id": request_id
        }