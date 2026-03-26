# src/utils/logging_utils.py
import logging
import json
import traceback
import uuid
import time
import os
import threading
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
from functools import wraps


class LogLevel(Enum):
    """Log levels for structured logging."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SecurityEvent(Enum):
    """Security event types for audit trails."""
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"


@dataclass
class LogEntry:
    """Structured log entry format."""
    timestamp: str
    level: str
    component: str
    message: str
    correlation_id: str
    thread_id: int
    extra_data: Dict[str, Any] = None


@dataclass
class AuditEvent:
    """Audit trail event format."""
    timestamp: str
    event_type: str
    component: str
    correlation_id: str
    severity: str
    details: Dict[str, Any]
    user_id: Optional[str] = None
    ip_address: Optional[str] = None


class SecureLogger:
    """Secure logging utility with structured logging and audit trails."""
    
    def __init__(self, component_name: str):
        self.component_name = component_name
        self.logger = logging.getLogger(f"etherion.{component_name}")
        
        # Configure logger
        self.logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL', 'INFO')))
        
        # Add handler if not already present
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Lock for thread safety
        self._lock = threading.RLock()
        
        # Redaction patterns for sensitive information
        self._redaction_patterns = [
            (r'("password["\s]*[:=]["\s]*)([^"\s,}]*)', r'\1[REDACTED]'),
            (r'("api_key["\s]*[:=]["\s]*)([^"\s,}]*)', r'\1[REDACTED]'),
            (r'("secret["\s]*[:=]["\s]*)([^"\s,}]*)', r'\1[REDACTED]'),
            (r'("token["\s]*[:=]["\s]*)([^"\s,}]*)', r'\1[REDACTED]'),
        ]
        self._compiled_patterns = [(re.compile(pattern), replacement) 
                                 for pattern, replacement in self._redaction_patterns]
    
    def _generate_correlation_id(self) -> str:
        """Generate a unique correlation ID."""
        return str(uuid.uuid4())
    
    def _redact_sensitive_data(self, message: str) -> str:
        """Redact sensitive information from log messages."""
        redacted_message = message
        for pattern, replacement in self._compiled_patterns:
            redacted_message = pattern.sub(replacement, redacted_message)
        return redacted_message
    
    def _create_log_entry(self, level: LogLevel, message: str, 
                         correlation_id: str = None, **kwargs) -> LogEntry:
        """Create a structured log entry."""
        if correlation_id is None:
            correlation_id = self._generate_correlation_id()
            
        # Redact sensitive data
        safe_message = self._redact_sensitive_data(message)
        safe_extra_data = {}
        if kwargs:
            # Convert to JSON and back to ensure serializability and redact sensitive data
            try:
                json_data = json.dumps(kwargs, default=str)
                safe_json_data = self._redact_sensitive_data(json_data)
                safe_extra_data = json.loads(safe_json_data)
            except:
                safe_extra_data = {"error": "Failed to serialize extra data"}
        
        return LogEntry(
            timestamp=datetime.utcnow().isoformat() + "Z",
            level=level.value,
            component=self.component_name,
            message=safe_message,
            correlation_id=correlation_id,
            thread_id=threading.get_ident(),
            extra_data=safe_extra_data
        )
    
    def _log(self, level: LogLevel, message: str, correlation_id: str = None, **kwargs):
        """Internal logging method."""
        with self._lock:
            log_entry = self._create_log_entry(level, message, correlation_id, **kwargs)
            
            # Log to standard logger
            log_message = json.dumps(asdict(log_entry), default=str)
            getattr(self.logger, level.value.lower())(log_message)
    
    def debug(self, message: str, correlation_id: str = None, **kwargs):
        """Log a debug message."""
        self._log(LogLevel.DEBUG, message, correlation_id, **kwargs)
    
    def info(self, message: str, correlation_id: str = None, **kwargs):
        """Log an info message."""
        self._log(LogLevel.INFO, message, correlation_id, **kwargs)
    
    def warning(self, message: str, correlation_id: str = None, **kwargs):
        """Log a warning message."""
        self._log(LogLevel.WARNING, message, correlation_id, **kwargs)
    
    def error(self, message: str, correlation_id: str = None, **kwargs):
        """Log an error message."""
        self._log(LogLevel.ERROR, message, correlation_id, **kwargs)
    
    def critical(self, message: str, correlation_id: str = None, **kwargs):
        """Log a critical message."""
        self._log(LogLevel.CRITICAL, message, correlation_id, **kwargs)
    
    def log_exception(self, message: str = "Unhandled exception", 
                     correlation_id: str = None, **kwargs):
        """Log an exception with stack trace."""
        kwargs['stack_trace'] = traceback.format_exc()
        self._log(LogLevel.ERROR, message, correlation_id, **kwargs)
    
    def log_audit_event(self, event_type: SecurityEvent, severity: str,
                       details: Dict[str, Any], user_id: str = None,
                       ip_address: str = None, correlation_id: str = None):
        """Log a security audit event."""
        if correlation_id is None:
            correlation_id = self._generate_correlation_id()
        
        audit_event = AuditEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            event_type=event_type.value,
            component=self.component_name,
            correlation_id=correlation_id,
            severity=severity,
            details=details,
            user_id=user_id,
            ip_address=ip_address
        )
        
        # Log to audit trail
        audit_message = f"SECURITY_AUDIT: {event_type.value}"
        self._log(LogLevel.INFO, audit_message, correlation_id, 
                 audit_event=asdict(audit_event))
    
    def log_performance_metric(self, operation: str, duration: float,
                              success: bool = True, correlation_id: str = None, **kwargs):
        """Log a performance metric."""
        kwargs.update({
            'operation': operation,
            'duration_ms': duration * 1000,
            'success': success
        })
        self._log(LogLevel.INFO, f"PERFORMANCE_METRIC: {operation}", 
                 correlation_id, **kwargs)


def get_logger(component_name: str) -> SecureLogger:
    """Get a secure logger instance for a component."""
    return SecureLogger(component_name)


def log_security_event(event_type: SecurityEvent, component: str, severity: str,
                      details: Dict[str, Any], user_id: str = None,
                      ip_address: str = None):
    """Global function to log security events."""
    logger = get_logger(component)
    logger.log_audit_event(event_type, severity, details, user_id, ip_address)


def performance_monitor(operation_name: str = None):
    """Decorator for monitoring function performance."""
    def decorator(func):
        nonlocal operation_name
        if operation_name is None:
            operation_name = func.__name__
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            start_time = time.time()
            correlation_id = logger._generate_correlation_id()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log_performance_metric(
                    operation_name, duration, True, correlation_id,
                    args_count=len(args), kwargs_count=len(kwargs)
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.log_performance_metric(
                    operation_name, duration, False, correlation_id,
                    error_type=type(e).__name__, error_message=str(e)
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            start_time = time.time()
            correlation_id = logger._generate_correlation_id()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log_performance_metric(
                    operation_name, duration, True, correlation_id,
                    args_count=len(args), kwargs_count=len(kwargs)
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.log_performance_metric(
                    operation_name, duration, False, correlation_id,
                    error_type=type(e).__name__, error_message=str(e)
                )
                raise
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

# Create a logger instance for use by other modules
logger = logging.getLogger(__name__)