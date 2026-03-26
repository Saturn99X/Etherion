# src/etherion_ai/utils/logging_utils.py
import json
import logging
import sys
from typing import Any, Dict
import os

# Try to import Google Cloud Logging client
try:
    from google.cloud import logging as cloud_logging
    CLOUD_LOGGING_AVAILABLE = True
except ImportError:
    CLOUD_LOGGING_AVAILABLE = False


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 
                              'pathname', 'filename', 'module', 'lineno', 
                              'funcName', 'created', 'msecs', 'relativeCreated',
                              'thread', 'threadName', 'processName', 'process',
                              'getMessage', 'exc_info', 'exc_text', 'stack_info'):
                    log_entry[key] = value

        return json.dumps(log_entry)


def setup_logging(level: int = logging.INFO) -> None:
    """Set up structured JSON logging."""
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Allow explicitly disabling Cloud Logging via env flag (useful for tests/local)
    disable_gcp_logging = os.environ.get("DISABLE_GCP_LOGGING", "").lower() in ("1", "true", "yes")

    # If running in Google Cloud, set up Cloud Logging (unless disabled)
    if (not disable_gcp_logging) and CLOUD_LOGGING_AVAILABLE and os.environ.get("GOOGLE_CLOUD_PROJECT"):
        try:
            # Initialize Cloud Logging client
            client = cloud_logging.Client()
            client.setup_logging(log_level=level)
            logger.info("Google Cloud Logging initialized")
        except Exception as e:
            # Fall back to console logging if Cloud Logging fails
            logger.warning(f"Failed to initialize Google Cloud Logging: {str(e)}")
            _setup_console_logging(logger, level)
    else:
        # Use console logging
        _setup_console_logging(logger, level)

    # Prevent propagation to avoid duplicate logs
    logger.propagate = False


def _setup_console_logging(logger: logging.Logger, level: int) -> None:
    """Set up console logging with JSON formatter."""
    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    
    # Clear existing handlers and add our JSON handler
    logger.handlers.clear()
    logger.addHandler(console_handler)


def log_structured(level: int, message: str, **kwargs: Any) -> None:
    """Log a structured message with additional fields."""
    logger = logging.getLogger(__name__)
    extra = {key: value for key, value in kwargs.items()}
    logger.log(level, message, extra=extra)


def log_info(message: str, **kwargs: Any) -> None:
    """Log an info message with structured data."""
    log_structured(logging.INFO, message, **kwargs)


def log_warning(message: str, **kwargs: Any) -> None:
    """Log a warning message with structured data."""
    log_structured(logging.WARNING, message, **kwargs)


def log_error(message: str, **kwargs: Any) -> None:
    """Log an error message with structured data."""
    log_structured(logging.ERROR, message, **kwargs)


def log_critical(message: str, **kwargs: Any) -> None:
    """Log a critical message with structured data."""
    log_structured(logging.CRITICAL, message, **kwargs)


# ------------------------------
# Sensitive data redaction
# ------------------------------
SENSITIVE_HEADER_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-webhook-secret",
    "stripe-signature",
}


def sanitize_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive header values and normalize keys to canonical case."""
    if not isinstance(headers, dict):
        return {}
    sanitized: Dict[str, Any] = {}
    for k, v in headers.items():
        lk = str(k).lower()
        if lk in SENSITIVE_HEADER_KEYS:
            sanitized[k] = "***redacted***"
        else:
            # Avoid logging extremely long header values
            try:
                sval = str(v)
                sanitized[k] = sval if len(sval) <= 1024 else sval[:1024] + "…"
            except Exception:
                sanitized[k] = "<unserializable>"
    return sanitized


def generate_request_id() -> str:
    """Generate a unique request ID."""
    import uuid
    return str(uuid.uuid4())


def log_request(request: Any, request_id: str) -> None:
    """Log request information."""
    try:
        headers = dict(request.headers) if hasattr(request, "headers") else {}
    except Exception:
        headers = {}
    sanitized = sanitize_headers(headers)
    # Resolve contextual attributes
    service = os.environ.get("SERVICE_NAME", "etherion-api")
    tenant_id = getattr(getattr(request, "state", object()), "tenant_id", None)
    user_id = getattr(getattr(request, "state", object()), "user_id", None)
    traceparent = headers.get("traceparent") or ""
    client_ip = request.client.host if hasattr(request, "client") and request.client else "unknown"
    log_info(
        "Request received",
        service=service,
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        method=getattr(request, "method", "UNKNOWN"),
        url=str(getattr(request, "url", "")),
        headers=sanitized,
        client=client_ip,
        traceparent=traceparent,
    )


def log_response(request: Any, response: Any, request_id: str, start_time: float) -> None:
    """Log response information."""
    import time
    processing_time = time.time() - start_time
    try:
        headers = dict(response.headers)
    except Exception:
        headers = {}
    sanitized = sanitize_headers(headers)
    service = os.environ.get("SERVICE_NAME", "etherion-api")
    tenant_id = getattr(getattr(request, "state", object()), "tenant_id", None)
    user_id = getattr(getattr(request, "state", object()), "user_id", None)
    traceparent = getattr(request, "headers", {}).get("traceparent") if hasattr(request, "headers") else ""
    log_info(
        "Response sent",
        service=service,
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        status_code=getattr(response, "status_code", 0),
        processing_time=processing_time,
        headers=sanitized,
        traceparent=traceparent,
    )


def log_graphql_operation(request_id: str, operation_name: str, query: str, variables: dict) -> None:
    """Log GraphQL operation information."""
    log_info(
        "GraphQL operation executed",
        request_id=request_id,
        operation_name=operation_name,
        query=query[:1000],  # Truncate query for logging
        variables_count=len(variables) if variables else 0
    )