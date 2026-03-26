"""
Enhanced Base MCP Tool for Production-Ready Integrations.

This module provides a robust foundation for all MCP tools with:
- Comprehensive credential management (OAuth 2.0, API keys, tokens)
- Advanced rate limiting and quota management
- Exponential backoff with jitter for retries
- Circuit breaker pattern for fault tolerance
- Request/response validation and sanitization
- Structured logging and error handling
- Multi-tenant isolation
- Token refresh automation
- Webhook signature verification

Author: Etherion AI Platform Team
Date: October 1, 2025
Version: 2.0.0
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from pydantic import BaseModel, Field, validator

from src.utils.secrets_manager import TenantSecretsManager
import os
from src.utils.input_sanitization import InputSanitizer
from src.core.redis import get_redis_client, is_job_cancelled

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================


class AuthType(str, Enum):
    """Supported authentication types."""

    OAUTH2_AUTHORIZATION_CODE = "oauth2_auth_code"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_creds"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    JWT_TOKEN = "jwt_token"
    CUSTOM = "custom"


class HttpMethod(str, Enum):
    """HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ErrorSeverity(str, Enum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# EXCEPTIONS
# ============================================================================


class MCPToolError(Exception):
    """Base exception for MCP tool errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.severity = severity
        self.retry_after = retry_after
        self.details = details or {}
        super().__init__(self.message)


class InvalidCredentialsError(MCPToolError):
    """Raised when credentials are invalid or expired."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code="INVALID_CREDENTIALS",
            severity=ErrorSeverity.HIGH,
            details=details,
        )


class RateLimitError(MCPToolError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: int = 60,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            error_code="RATE_LIMIT_EXCEEDED",
            severity=ErrorSeverity.MEDIUM,
            retry_after=retry_after,
            details=details,
        )


class TimeoutError(MCPToolError):
    """Raised when request times out."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code="REQUEST_TIMEOUT",
            severity=ErrorSeverity.MEDIUM,
            details=details,
        )


class NetworkError(MCPToolError):
    """Raised for network-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code="NETWORK_ERROR",
            severity=ErrorSeverity.HIGH,
            details=details,
        )


class ValidationError(MCPToolError):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
            severity=ErrorSeverity.LOW,
            details=details,
        )


class QuotaExceededError(MCPToolError):
    """Raised when quota is exceeded."""

    def __init__(
        self,
        message: str,
        quota_reset: Optional[datetime] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            error_code="QUOTA_EXCEEDED",
            severity=ErrorSeverity.HIGH,
            details=details or {},
        )
        self.quota_reset = quota_reset


class CircuitBreakerOpenError(MCPToolError):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code="CIRCUIT_BREAKER_OPEN",
            severity=ErrorSeverity.HIGH,
            details=details,
        )


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_second: float = 10.0
    requests_per_minute: float = 600.0
    requests_per_hour: float = 36000.0
    burst_size: int = 20

    # Per-endpoint overrides
    endpoint_limits: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class RetryConfig:
    """Retry configuration."""

    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_status_codes: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 60.0  # seconds
    half_open_max_calls: int = 1
    # Backward-compat options sometimes passed by tools
    recovery_timeout: Optional[float] = None
    expected_exception_types: Optional[tuple] = None

    def __post_init__(self):
        # Map recovery_timeout -> timeout if provided by older tools
        if self.recovery_timeout is not None:
            try:
                self.timeout = float(self.recovery_timeout)
            except Exception:
                pass


@dataclass
class MCPToolResult:
    """Result from MCP tool execution."""

    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "data": self.data,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "metadata": self.metadata,
        }


# ============================================================================
# RATE LIMITER
# ============================================================================


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter with burst support.

    Implements the token bucket algorithm for smooth rate limiting
    with burst capacity.
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.burst_size
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

        # Per-endpoint buckets
        self.endpoint_buckets: Dict[str, Dict[str, Any]] = {}

    async def acquire(self, endpoint: Optional[str] = None, tokens: int = 1) -> bool:
        """
        Acquire tokens from the bucket.

        Args:
            endpoint: Optional endpoint for per-endpoint limits
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False otherwise
        """
        async with self.lock:
            now = time.monotonic()

            # Get rate for this endpoint or use default
            rate = self.config.requests_per_second
            if endpoint and endpoint in self.config.endpoint_limits:
                rate = self.config.endpoint_limits[endpoint].get("per_second", rate)

            # Refill tokens
            elapsed = now - self.last_update
            self.tokens = min(self.config.burst_size, self.tokens + elapsed * rate)
            self.last_update = now

            # Try to acquire tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    async def wait_for_token(
        self, endpoint: Optional[str] = None, timeout: float = 30.0
    ) -> None:
        """
        Wait until a token is available.

        Args:
            endpoint: Optional endpoint for per-endpoint limits
            timeout: Maximum time to wait

        Raises:
            TimeoutError: If timeout is exceeded
        """
        start_time = time.monotonic()

        while True:
            if await self.acquire(endpoint=endpoint):
                return

            # Check timeout
            if time.monotonic() - start_time > timeout:
                raise TimeoutError(
                    f"Rate limiter timeout after {timeout}s",
                    details={"endpoint": endpoint},
                )

            # Sleep briefly before retrying
            await asyncio.sleep(0.1)


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail immediately
    - HALF_OPEN: Testing if service recovered
    """

    class State(Enum):
        CLOSED = "closed"
        OPEN = "open"
        HALF_OPEN = "half_open"

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = self.State.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        async with self.lock:
            # Check if circuit should transition from OPEN to HALF_OPEN
            if self.state == self.State.OPEN:
                if self.last_failure_time:
                    elapsed = time.monotonic() - self.last_failure_time
                    if elapsed >= self.config.timeout:
                        logger.info("Circuit breaker transitioning to HALF_OPEN")
                        self.state = self.State.HALF_OPEN
                        self.success_count = 0
                    else:
                        raise CircuitBreakerOpenError(
                            f"Circuit breaker is OPEN, retry after {self.config.timeout - elapsed:.1f}s"
                        )

            # Limit calls in HALF_OPEN state
            if self.state == self.State.HALF_OPEN:
                if self.success_count >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        "Circuit breaker is HALF_OPEN and max calls reached"
                    )

        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self.lock:
            self.failure_count = 0

            if self.state == self.State.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    logger.info("Circuit breaker transitioning to CLOSED")
                    self.state = self.State.CLOSED
                    self.success_count = 0

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            if self.state == self.State.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    logger.warning("Circuit breaker transitioning to OPEN")
                    self.state = self.State.OPEN
            elif self.state == self.State.HALF_OPEN:
                logger.warning("Circuit breaker transitioning back to OPEN")
                self.state = self.State.OPEN


# ============================================================================
# ENHANCED BASE MCP TOOL
# ============================================================================


class EnhancedMCPTool(ABC):
    """
    Enhanced base class for all MCP tools with production-ready features.

    Features:
    - Multiple authentication methods
    - Rate limiting with burst support
    - Exponential backoff with jitter
    - Circuit breaker pattern
    - Automatic token refresh
    - Request/response validation
    - Structured logging
    - Multi-tenant isolation
    - Webhook verification
    - Comprehensive error handling
    """

    def __init__(
        self,
        name: str,
        description: str,
        auth_type: AuthType = AuthType.API_KEY,
        base_url: Optional[str] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize enhanced MCP tool.

        Args:
            name: Tool name
            description: Tool description
            auth_type: Authentication type
            base_url: API base URL
            rate_limit_config: Rate limit configuration
            retry_config: Retry configuration
            circuit_breaker_config: Circuit breaker configuration
            timeout: Request timeout in seconds
        """
        self.name = name
        self.description = description
        self.auth_type = auth_type
        self.base_url = base_url
        self.timeout = timeout

        # Initialize configurations
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()

        # Initialize components
        self.rate_limiter = TokenBucketRateLimiter(self.rate_limit_config)
        self.circuit_breaker = CircuitBreaker(self.circuit_breaker_config)
        self.secrets_manager = TenantSecretsManager()
        # Instance logger for tools that expect self.logger
        self.logger = logging.getLogger(self.__class__.__name__)

        # Global daily quota (per-tenant) default; overridable via env
        try:
            self._global_daily_api_calls_limit = int(os.getenv("GLOBAL_DAILY_API_CALLS", "10000"))
        except Exception:
            self._global_daily_api_calls_limit = 10000

        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()

        logger.info(f"Initialized {name} with auth_type={auth_type.value}")

    async def execute(
        self,
        tenant_id: str,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        validate_input: bool = True,
        use_rate_limiter: bool = True,
    ) -> MCPToolResult:
        """
        Execute tool operation with full error handling and retry logic.

        Args:
            tenant_id: Tenant identifier
            operation: Operation to execute
            params: Operation parameters
            validate_input: Whether to validate input
            use_rate_limiter: Whether to use rate limiter

        Returns:
            MCPToolResult with operation result
        """
        params = params or {}
        start_time = time.time()
        # Cooperative cancel: honor STOP if a job_id is provided
        job_id = str(params.get("job_id") or params.get("jobId") or "")
        if job_id:
            try:
                if await is_job_cancelled(job_id):
                    return MCPToolResult(
                        success=False,
                        data=None,
                        error_message="CANCELLED",
                        error_code="CANCELLED",
                        metadata={"operation": operation, "job_id": job_id},
                    )
            except Exception:
                # Fail-open on cancel check errors
                pass

        try:
            # Log operation start
            logger.info(
                f"Executing {self.name}.{operation}",
                extra={
                    "tenant_id": tenant_id,
                    "operation": operation,
                    "params": {
                        k: "***"
                        if "secret" in k.lower()
                        or "token" in k.lower()
                        or "password" in k.lower()
                        else v
                        for k, v in params.items()
                    },
                },
            )

            # Validate and sanitize input
            if validate_input:
                params = self._validate_and_sanitize_input(operation, params)

            # Confirm-action gate for write operations
            if self._is_write_operation(operation, params):
                if not bool(params.get("confirm_action", False)):
                    return MCPToolResult(
                        success=False,
                        error_message="Confirmation required for write operation",
                        error_code="CONFIRMATION_REQUIRED",
                        metadata={"operation": operation},
                    )

            # Rate limiting (token bucket)
            if use_rate_limiter:
                await self.rate_limiter.wait_for_token(
                    endpoint=operation, timeout=self.timeout
                )

            # Re-check cancel before performing the operation
            if job_id:
                try:
                    if await is_job_cancelled(job_id):
                        return MCPToolResult(
                            success=False,
                            data=None,
                            error_message="CANCELLED",
                            error_code="CANCELLED",
                            metadata={"operation": operation, "job_id": job_id},
                        )
                except Exception:
                    pass

            # Global daily per-tenant quota (Redis)
            try:
                import datetime as _dt
                redis = get_redis_client()
                client = await redis.get_client()
                now = _dt.datetime.utcnow()
                date_str = now.strftime("%Y%m%d")
                key_global = f"quota:{tenant_id}:global:{date_str}"
                async with client.pipeline(transaction=True) as pipe:
                    await pipe.incr(key_global)
                    midnight = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    ttl_seconds = int((midnight - now).total_seconds())
                    await pipe.expire(key_global, ttl_seconds)
                    res = await pipe.execute()
                current_global = int(res[0] or 0)
                if current_global > max(1, self._global_daily_api_calls_limit):
                    return MCPToolResult(
                        success=False,
                        error_message="Global daily quota exceeded",
                        error_code="QUOTA_EXCEEDED",
                        metadata={
                            "limit": self._global_daily_api_calls_limit,
                            "current": current_global,
                            "reset_in": ttl_seconds,
                        },
                    )
            except Exception:
                pass

            # Daily per-tenant per-vendor quota (Redis) before execution
            try:
                import datetime as _dt

                vendor_key = self.name.replace("mcp_", "")
                now = _dt.datetime.utcnow()
                date_str = now.strftime("%Y%m%d")
                quota_defaults = {
                    "slack": 5000,
                    "gmail": 2000,
                    "google_drive": 2000,
                    "ms365": 2000,
                    "shopify": 3000,
                    "jira": 3000,
                    "notion": 3000,
                    "salesforce": 2000,
                }
                limit = quota_defaults.get(vendor_key, 2000)
                redis = get_redis_client()
                client = await redis.get_client()
                key = f"quota:{tenant_id}:{vendor_key}:{date_str}"
                async with client.pipeline(transaction=True) as pipe:
                    await pipe.incr(key)
                    midnight = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    ttl_seconds = int((midnight - now).total_seconds())
                    await pipe.expire(key, ttl_seconds)
                    results = await pipe.execute()
                current = int(results[0] or 0)
                if current > limit:
                    return MCPToolResult(
                        success=False,
                        error_message=f"Daily quota exceeded for {vendor_key}",
                        error_code="QUOTA_EXCEEDED",
                        metadata={
                            "limit": limit,
                            "current": current,
                            "reset_in": ttl_seconds,
                        },
                    )
            except Exception:
                # Quota failures should not crash tool execution; proceed but log would happen at API layer
                pass

            # Execute with circuit breaker and retry
            result = await self.circuit_breaker.call(
                self._execute_with_retry, tenant_id, operation, params
            )

            # Log success
            duration = time.time() - start_time
            logger.info(
                f"Completed {self.name}.{operation}",
                extra={
                    "tenant_id": tenant_id,
                    "operation": operation,
                    "duration_ms": int(duration * 1000),
                    "success": True,
                },
            )

            return MCPToolResult(
                success=True,
                data=result,
                metadata={
                    "operation": operation,
                    "duration_ms": int(duration * 1000),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        except CircuitBreakerOpenError as e:
            logger.error(f"Circuit breaker open for {self.name}.{operation}: {e}")
            return MCPToolResult(
                success=False,
                error_message=str(e),
                error_code=e.error_code,
                metadata={"operation": operation, "error_type": "circuit_breaker"},
            )

        except RateLimitError as e:
            logger.warning(f"Rate limit exceeded for {self.name}.{operation}: {e}")
            return MCPToolResult(
                success=False,
                error_message=str(e),
                error_code=e.error_code,
                metadata={
                    "operation": operation,
                    "retry_after": e.retry_after,
                    "error_type": "rate_limit",
                },
            )

        except ValidationError as e:
            logger.warning(f"Validation error for {self.name}.{operation}: {e}")
            return MCPToolResult(
                success=False,
                error_message=str(e),
                error_code=e.error_code,
                metadata={"operation": operation, "error_type": "validation"},
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Error executing {self.name}.{operation}: {e}",
                exc_info=True,
                extra={
                    "tenant_id": tenant_id,
                    "operation": operation,
                    "duration_ms": int(duration * 1000),
                    "error": str(e),
                },
            )
            return MCPToolResult(
                success=False,
                error_message=str(e),
                error_code="UNKNOWN_ERROR",
                metadata={"operation": operation, "error_type": "unknown"},
            )

    async def _execute_with_retry(
        self, tenant_id: str, operation: str, params: Dict[str, Any]
    ) -> Any:
        """
        Execute operation with exponential backoff retry logic.

        Args:
            tenant_id: Tenant identifier
            operation: Operation to execute
            params: Operation parameters

        Returns:
            Operation result
        """
        last_exception = None
        delay = self.retry_config.initial_delay

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Execute tool-specific logic
                return await self._execute_operation(tenant_id, operation, params)

            except RateLimitError as e:
                # Rate limit errors should always be retried
                last_exception = e
                wait_time = e.retry_after if e.retry_after else delay

                if attempt < self.retry_config.max_retries:
                    logger.warning(
                        f"Rate limit hit, retrying in {wait_time}s (attempt {attempt + 1}/{self.retry_config.max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    delay = min(
                        delay * self.retry_config.exponential_base,
                        self.retry_config.max_delay,
                    )

            except aiohttp.ClientError as e:
                # Network errors
                last_exception = NetworkError(
                    f"Network error: {e}", details={"original_error": str(e)}
                )

                if attempt < self.retry_config.max_retries:
                    # Add jitter if configured
                    if self.retry_config.jitter:
                        import random

                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Network error, retrying in {delay:.2f}s (attempt {attempt + 1}/{self.retry_config.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    delay = min(
                        delay * self.retry_config.exponential_base,
                        self.retry_config.max_delay,
                    )

            except (InvalidCredentialsError, ValidationError) as e:
                # Don't retry these errors
                raise

            except Exception as e:
                last_exception = e

                # Check if we should retry based on error
                should_retry = False
                if (
                    hasattr(e, "status")
                    and e.status in self.retry_config.retry_on_status_codes
                ):
                    should_retry = True

                if should_retry and attempt < self.retry_config.max_retries:
                    if self.retry_config.jitter:
                        import random

                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Retryable error, retrying in {delay:.2f}s (attempt {attempt + 1}/{self.retry_config.max_retries}): {e}"
                    )
                    await asyncio.sleep(delay)
                    delay = min(
                        delay * self.retry_config.exponential_base,
                        self.retry_config.max_delay,
                    )
                else:
                    raise

        # All retries exhausted
        if last_exception:
            raise last_exception
        raise MCPToolError("Max retries exceeded")

    @abstractmethod
    async def _execute_operation(
        self, tenant_id: str, operation: str, params: Dict[str, Any]
    ) -> Any:
        """
        Execute the actual operation (implemented by subclasses).

        Args:
            tenant_id: Tenant identifier
            operation: Operation name
            params: Operation parameters

        Returns:
            Operation result
        """
        pass

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        if params.get("is_write_op") is True:
            return True
        write_prefixes = ("create", "update", "delete", "post", "put", "patch", "insert", "remove")
        return op.startswith(write_prefixes)

    def _validate_and_sanitize_input(
        self, operation: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate and sanitize input parameters.

        Args:
            operation: Operation name
            params: Input parameters

        Returns:
            Sanitized parameters

        Raises:
            ValidationError: If validation fails
        """
        # Get operation schema (override in subclasses)
        schema = self._get_operation_schema(operation)
        if not schema:
            return params

        sanitized = {}

        for field_name, field_config in schema.items():
            value = params.get(field_name)

            # Check required fields
            if field_config.get("required", False) and value is None:
                raise ValidationError(
                    f"Required field '{field_name}' is missing",
                    details={"field": field_name, "operation": operation},
                )

            if value is not None:
                # Type checking
                expected_type = field_config.get("type")
                if expected_type and not isinstance(value, expected_type):
                    try:
                        value = expected_type(value)
                    except (ValueError, TypeError):
                        raise ValidationError(
                            f"Field '{field_name}' must be of type {expected_type.__name__}",
                            details={
                                "field": field_name,
                                "expected_type": expected_type.__name__,
                            },
                        )

                # String sanitization
                if isinstance(value, str):
                    max_length = field_config.get("max_length", 10000)
                    value = InputSanitizer.sanitize_string(value, max_length=max_length)

                # Custom validation
                validator_func = field_config.get("validator")
                if validator_func and callable(validator_func):
                    value = validator_func(value)

                sanitized[field_name] = value

        return sanitized

    def _get_operation_schema(
        self, operation: str
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Get validation schema for operation (override in subclasses).

        Args:
            operation: Operation name

        Returns:
            Schema dictionary or None
        """
        return None

    # ------------------- Generic schema hinting for ALL MCP tools -------------------
    def list_operations(self, max_ops: int = 50) -> List[str]:
        """Introspect supported operations by scanning _handle_* methods in the subclass.

        Returns a truncated list to avoid oversized prompts.
        """
        try:
            ops = []
            for name in dir(self):
                if name.startswith("_handle_") and callable(getattr(self, name)):
                    ops.append(name[len("_handle_"):])
            ops.sort()
            if len(ops) > max_ops:
                return ops[:max_ops]
            return ops
        except Exception:
            return []

    def get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """Public accessor that uses subclass override if available, else returns a heuristic schema."""
        try:
            specific = self._get_operation_schema(operation)
            if specific:
                return specific
        except Exception:
            pass

        # Heuristic fallback based on naming conventions
        op = (operation or "").lower()
        STR = str
        INT = int
        BOOL = bool
        if op.startswith(("get_", "list_", "search_", "fetch_")):
            base = {
                "limit": {"type": INT, "required": False},
                "cursor": {"type": STR, "required": False},
                "query": {"type": STR, "required": False},
            }
            # common id suffixes
            for k in ("id", "channel_id", "user_id", "project_id"):
                base.setdefault(k, {"type": STR, "required": False})
            return base
        if op.startswith(("create_", "update_", "delete_", "insert_", "remove_", "post_", "put_", "patch_")):
            return {
                "confirm_action": {"type": BOOL, "required": False},
                "id": {"type": STR, "required": op.startswith(("update_", "delete_"))},
                "payload": {"type": dict, "required": True},
            }
        # Default minimal
        return {
            "payload": {"type": dict, "required": False},
        }

    def get_schema_hints(self, max_ops: int = 15) -> Dict[str, Any]:
        """Return a JSON-serializable summary of operations and example schemas.

        This is used by the Tool Protocol to guide LLM planning across ALL MCP tools
        without requiring each subclass to implement full schemas.
        """
        try:
            ops = self.list_operations(max_ops=max_ops)
            examples: Dict[str, Any] = {}
            for op in ops[:max_ops]:
                try:
                    schema = self.get_operation_schema(op) or {}
                    # Convert Python types to strings for JSON serialization
                    norm: Dict[str, Any] = {}
                    for k, cfg in (schema or {}).items():
                        t = cfg.get("type")
                        norm[k] = {
                            **{kk: vv for kk, vv in cfg.items() if kk != "type"},
                            "type": getattr(t, "__name__", str(t)) if t else None,
                        }
                    examples[op] = norm
                except Exception:
                    continue
            return {
                "supported_operations": ops,
                "example_param_schemas": examples,
                "conventions": {
                    "write_ops_confirm_action": True,
                    "read_ops_pagination": ["limit", "cursor"],
                },
            }
        except Exception:
            return {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            async with self._session_lock:
                if self.session is None or self.session.closed:
                    self.session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                    )
        return self.session

    async def _make_request(
        self,
        method: HttpMethod,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with error handling.

        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            params: Query parameters
            json_data: JSON body
            data: Raw body data

        Returns:
            Response data
        """
        session = await self._get_session()

        try:
            async with session.request(
                method.value,
                url,
                headers=headers,
                params=params,
                json=json_data,
                data=data,
            ) as response:
                # Check for rate limiting
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    raise RateLimitError(
                        "Rate limit exceeded",
                        retry_after=retry_after,
                        details={"url": url, "status": response.status},
                    )

                # Check for authentication errors
                if response.status == 401:
                    raise InvalidCredentialsError(
                        "Invalid or expired credentials",
                        details={"url": url, "status": response.status},
                    )

                # Check for other errors
                if response.status >= 400:
                    error_text = await response.text()
                    raise MCPToolError(
                        f"HTTP {response.status}: {error_text[:200]}",
                        error_code=f"HTTP_{response.status}",
                        details={"url": url, "status": response.status},
                    )

                # Parse response
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await response.json()
                else:
                    return {"text": await response.text()}

        except aiohttp.ClientError as e:
            raise NetworkError(
                f"Network error: {e}", details={"url": url, "error": str(e)}
            )

    async def _get_credentials(
        self, tenant_id: str, credential_keys: List[str]
    ) -> Dict[str, Optional[str]]:
        """
        Retrieve credentials from secrets manager.

        Args:
            tenant_id: Tenant identifier
            credential_keys: List of credential keys to retrieve

        Returns:
            Dictionary of credentials
        """
        credentials = {}

        for key in credential_keys:
            value = await self.secrets_manager.get_secret(
                tenant_id=tenant_id, service_name=self.name, key_type=key
            )
            credentials[key] = value

        return credentials

    @staticmethod
    def verify_webhook_signature(
        payload: bytes, signature: str, secret: str, algorithm: str = "sha256"
    ) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: Webhook payload
            signature: Provided signature
            secret: Webhook secret
            algorithm: Hash algorithm (sha256, sha1)

        Returns:
            True if signature is valid
        """
        if algorithm == "sha256":
            expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        elif algorithm == "sha1":
            expected = hmac.new(secret.encode(), payload, hashlib.sha1).hexdigest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        return hmac.compare_digest(expected, signature)

    async def close(self) -> None:
        """Close resources."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

# Backward compatibility alias for older imports
BaseMCPTool = EnhancedMCPTool
