# src/etherion_ai/exceptions.py
"""
Custom exception classes for the Etherion API.
"""

from typing import Optional, Dict, Any
import uuid


class BaseEtherionException(Exception):
    """
    Base exception class for all Etherion API exceptions.
    """
    def __init__(
        self, 
        message: str, 
        error_code: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.request_id = str(uuid.uuid4())
        super().__init__(self.message)


class ValidationError(BaseEtherionException):
    """
    Exception raised for input validation errors.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            details=details
        )


class AuthenticationError(BaseEtherionException):
    """
    Exception raised for authentication errors.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=401,
            details=details
        )


class AuthorizationError(BaseEtherionException):
    """
    Exception raised for authorization errors.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=403,
            details=details
        )


class NotFoundError(BaseEtherionException):
    """
    Exception raised when a resource is not found.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="NOT_FOUND_ERROR",
            status_code=404,
            details=details
        )


class ConflictError(BaseEtherionException):
    """
    Exception raised when there is a conflict with the current state of the resource.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="CONFLICT_ERROR",
            status_code=409,
            details=details
        )


class RateLimitError(BaseEtherionException):
    """
    Exception raised when rate limiting is exceeded.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_ERROR",
            status_code=429,
            details=details
        )


class InternalServerError(BaseEtherionException):
    """
    Exception raised for internal server errors.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="INTERNAL_SERVER_ERROR",
            status_code=500,
            details=details
        )