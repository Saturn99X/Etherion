# src/core/security/audit_logger.py
"""
Comprehensive audit logging system for security events and data access operations.
Implements structured logging with rotation and retention policies.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, asdict
import hashlib
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.core.redis import get_redis_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    AUTHENTICATION_SUCCESS = "authentication_success"
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_SUCCESS = "authorization_success"
    AUTHORIZATION_FAILURE = "authorization_failure"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    ADMIN_ACTION = "admin_action"
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    INPUT_VALIDATION_FAILURE = "input_validation_failure"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    CSRF_ATTEMPT = "csrf_attempt"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    API_ACCESS = "api_access"
    SYSTEM_ERROR = "system_error"


class AuditSeverity(Enum):
    """Severity levels for audit events."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Structured audit event data."""
    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    user_id: Optional[str]
    tenant_id: Optional[str]
    session_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    endpoint: Optional[str]
    method: Optional[str]
    request_id: Optional[str]
    details: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['event_type'] = self.event_type.value
        data['severity'] = self.severity.value
        return data

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class AuditLogger:
    """Main audit logging class."""
    
    def __init__(self):
        self.log_dir = Path(os.getenv("AUDIT_LOG_DIR", "/tmp/etherion/audit"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
        self.max_file_size = int(os.getenv("AUDIT_LOG_MAX_FILE_SIZE", "100MB").replace("MB", "")) * 1024 * 1024
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Setup file handlers for different event types
        self._setup_loggers()
    
    def _setup_loggers(self):
        """Setup separate loggers for different event types."""
        self.loggers = {}
        
        # Main audit logger
        self.loggers['main'] = self._create_logger('audit', 'audit.log')
        
        # Security events logger
        self.loggers['security'] = self._create_logger('security', 'security.log')
        
        # Authentication events logger
        self.loggers['auth'] = self._create_logger('auth', 'auth.log')
        
        # Data access logger
        self.loggers['data'] = self._create_logger('data', 'data_access.log')
    
    def _create_logger(self, name: str, filename: str) -> logging.Logger:
        """Create a logger with file rotation."""
        logger = logging.getLogger(f"audit.{name}")
        logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create file handler with rotation
        log_file = self.log_dir / filename
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self.max_file_size,
            backupCount=10
        )
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        logger.propagate = False
        
        return logger
    
    def _generate_event_id(self, event_data: Dict[str, Any]) -> str:
        """Generate unique event ID."""
        timestamp = datetime.now(timezone.utc).isoformat()
        data_str = f"{timestamp}:{json.dumps(event_data, sort_keys=True)}"
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]
    
    async def _get_redis_client(self):
        """Get Redis client for real-time events."""
        return get_redis_client()
    
    async def log_event(self, event: AuditEvent):
        """Log an audit event."""
        try:
            # Log to appropriate file logger
            await self._log_to_file(event)
            
            # Publish to Redis for real-time monitoring
            await self._publish_to_redis(event)
            
            # Log to console for development
            if os.getenv("ENVIRONMENT") == "development":
                logger.info(f"Audit Event: {event.event_type.value} - {event.details}")
                
        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}")
    
    async def _log_to_file(self, event: AuditEvent):
        """Log event to appropriate file."""
        def write_log():
            # Determine which logger to use
            if event.event_type in [AuditEventType.AUTHENTICATION_SUCCESS, 
                                  AuditEventType.AUTHENTICATION_FAILURE]:
                log_logger = self.loggers['auth']
            elif event.event_type in [AuditEventType.SECURITY_VIOLATION,
                                    AuditEventType.SQL_INJECTION_ATTEMPT,
                                    AuditEventType.XSS_ATTEMPT,
                                    AuditEventType.CSRF_ATTEMPT]:
                log_logger = self.loggers['security']
            elif event.event_type in [AuditEventType.DATA_ACCESS,
                                    AuditEventType.DATA_MODIFICATION]:
                log_logger = self.loggers['data']
            else:
                log_logger = self.loggers['main']
            
            # Log the event
            log_logger.info(event.to_json())
        
        # Run in thread pool to avoid blocking
        await asyncio.get_event_loop().run_in_executor(self.executor, write_log)
    
    async def _publish_to_redis(self, event: AuditEvent):
        """Publish event to Redis for real-time monitoring."""
        try:
            redis_client = await self._get_redis_client()
            
            # Publish to general audit channel
            # Note: RedisClient.publish handles json.dumps, so we pass the dict
            await redis_client.publish("audit:events", event.to_dict())
            
            # Publish to severity-specific channels
            await redis_client.publish(f"audit:{event.severity.value}", event.to_dict())
            
            # Publish to tenant-specific channel if tenant_id exists
            if event.tenant_id:
                await redis_client.publish(f"audit:tenant:{event.tenant_id}", event.to_dict())
                
        except Exception as e:
            logger.error(f"Failed to publish audit event to Redis: {str(e)}")
    
    async def cleanup_old_logs(self):
        """Clean up old log files based on retention policy."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            
            for log_file in self.log_dir.glob("*.log*"):
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    logger.info(f"Deleted old log file: {log_file}")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {str(e)}")


# Global audit logger instance
audit_logger = AuditLogger()


# Convenience functions for common audit events
async def log_authentication_success(
    user_id: str,
    tenant_id: str,
    ip_address: str,
    user_agent: str,
    session_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """Log successful authentication."""
    event = AuditEvent(
        event_id=audit_logger._generate_event_id({"user_id": user_id, "timestamp": datetime.now(timezone.utc).isoformat()}),
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.AUTHENTICATION_SUCCESS,
        severity=AuditSeverity.LOW,
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint="/auth/login",
        method="POST",
        request_id=None,
        details=details or {},
        success=True
    )
    await audit_logger.log_event(event)


async def log_authentication_failure(
    user_id: Optional[str],
    tenant_id: Optional[str],
    ip_address: str,
    user_agent: str,
    reason: str,
    session_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """Log failed authentication attempt."""
    event = AuditEvent(
        event_id=audit_logger._generate_event_id({"ip_address": ip_address, "timestamp": datetime.now(timezone.utc).isoformat()}),
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.AUTHENTICATION_FAILURE,
        severity=AuditSeverity.MEDIUM,
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint="/auth/login",
        method="POST",
        request_id=None,
        details=details or {"reason": reason},
        success=False,
        error_message=reason
    )
    await audit_logger.log_event(event)


async def log_authorization_failure(
    user_id: str,
    tenant_id: str,
    ip_address: str,
    user_agent: str,
    endpoint: str,
    method: str,
    reason: str,
    session_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """Log authorization failure."""
    event = AuditEvent(
        event_id=audit_logger._generate_event_id({"user_id": user_id, "endpoint": endpoint, "timestamp": datetime.now(timezone.utc).isoformat()}),
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.AUTHORIZATION_FAILURE,
        severity=AuditSeverity.HIGH,
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        request_id=None,
        details=details or {"reason": reason},
        success=False,
        error_message=reason
    )
    await audit_logger.log_event(event)


async def log_data_access(
    user_id: str,
    tenant_id: str,
    ip_address: str,
    user_agent: str,
    endpoint: str,
    method: str,
    data_type: str,
    operation: str,
    session_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """Log data access operation."""
    event = AuditEvent(
        event_id=audit_logger._generate_event_id({"user_id": user_id, "data_type": data_type, "timestamp": datetime.now(timezone.utc).isoformat()}),
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.DATA_ACCESS,
        severity=AuditSeverity.LOW,
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        request_id=None,
        details=details or {"data_type": data_type, "operation": operation},
        success=True
    )
    await audit_logger.log_event(event)


async def log_security_violation(
    user_id: Optional[str],
    tenant_id: Optional[str],
    ip_address: str,
    user_agent: str,
    endpoint: str,
    method: str,
    violation_type: str,
    details: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None
):
    """Log security violation."""
    event = AuditEvent(
        event_id=audit_logger._generate_event_id({"ip_address": ip_address, "violation_type": violation_type, "timestamp": datetime.now(timezone.utc).isoformat()}),
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.SECURITY_VIOLATION,
        severity=AuditSeverity.CRITICAL,
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        request_id=None,
        details=details or {"violation_type": violation_type},
        success=False,
        error_message=f"Security violation: {violation_type}"
    )
    await audit_logger.log_event(event)


async def log_rate_limit_exceeded(
    ip_address: str,
    user_agent: str,
    endpoint: str,
    method: str,
    limit_type: str,
    limit_value: int,
    current_count: int,
    details: Optional[Dict[str, Any]] = None
):
    """Log rate limit exceeded."""
    event = AuditEvent(
        event_id=audit_logger._generate_event_id({"ip_address": ip_address, "endpoint": endpoint, "timestamp": datetime.now(timezone.utc).isoformat()}),
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
        severity=AuditSeverity.MEDIUM,
        user_id=None,
        tenant_id=None,
        session_id=None,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        request_id=None,
        details=details or {
            "limit_type": limit_type,
            "limit_value": limit_value,
            "current_count": current_count
        },
        success=False,
        error_message=f"Rate limit exceeded: {current_count}/{limit_value} {limit_type}"
    )
    await audit_logger.log_event(event)


async def log_input_validation_failure(
    user_id: Optional[str],
    tenant_id: Optional[str],
    ip_address: str,
    user_agent: str,
    endpoint: str,
    method: str,
    validation_errors: List[str],
    input_data: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None
):
    """Log input validation failure."""
    event = AuditEvent(
        event_id=audit_logger._generate_event_id({"ip_address": ip_address, "endpoint": endpoint, "timestamp": datetime.now(timezone.utc).isoformat()}),
        timestamp=datetime.now(timezone.utc),
        event_type=AuditEventType.INPUT_VALIDATION_FAILURE,
        severity=AuditSeverity.MEDIUM,
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        request_id=None,
        details={
            "validation_errors": validation_errors,
            "input_data": input_data
        },
        success=False,
        error_message=f"Input validation failed: {', '.join(validation_errors)}"
    )
    await audit_logger.log_event(event)


# Periodic cleanup task
async def start_audit_cleanup_task():
    """Start periodic cleanup of old audit logs."""
    while True:
        try:
            await audit_logger.cleanup_old_logs()
            # Run cleanup daily
            await asyncio.sleep(86400)  # 24 hours
        except Exception as e:
            logger.error(f"Audit cleanup task error: {str(e)}")
            await asyncio.sleep(3600)  # Retry in 1 hour

# Security event logging functions
async def log_security_event(
    event_type: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: AuditSeverity = AuditSeverity.MEDIUM,
    ip_address: str = "unknown",
    user_agent: str = "unknown",
    endpoint: str = "orchestrator",
    method: str = "POST",
    session_id: Optional[str] = None
):
    """
    Log a security event for orchestrator operations.

    Args:
        event_type: Type of security event
        user_id: User ID associated with the event
        tenant_id: Tenant ID associated with the event
        details: Additional event details
        severity: Event severity level
        ip_address: IP address of the request
        user_agent: User agent string
        endpoint: API endpoint
        method: HTTP method
        session_id: Session ID
    """
    try:
        event = AuditEvent(
            event_id=audit_logger._generate_event_id({
                "event_type": event_type,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.SECURITY_VIOLATION,  # Using existing type for now
            severity=severity,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            method=method,
            request_id=None,
            details=details or {"event_type": event_type},
            success=True  # Security events are logged as successful logging operations
        )
        await audit_logger.log_event(event)
    except Exception as e:
        logger.error(f"Failed to log security event: {e}")


async def log_orchestrator_event(
    event_type: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: AuditSeverity = AuditSeverity.MEDIUM,
    ip_address: str = "unknown",
    user_agent: str = "unknown",
    endpoint: str = "orchestrator",
    method: str = "POST",
    session_id: Optional[str] = None
):
    """
    Log an orchestrator-specific event.

    Args:
        event_type: Type of orchestrator event
        user_id: User ID associated with the event
        tenant_id: Tenant ID associated with the event
        details: Additional event details
        severity: Event severity level
        ip_address: IP address of the request
        user_agent: User agent string
        endpoint: API endpoint
        method: HTTP method
        session_id: Session ID
    """
    try:
        event = AuditEvent(
            event_id=audit_logger._generate_event_id({
                "event_type": event_type,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.ADMIN_ACTION,  # Using admin action for orchestrator events
            severity=severity,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            method=method,
            request_id=None,
            details=details or {"event_type": event_type},
            success=True
        )
        await audit_logger.log_event(event)
    except Exception as e:
        logger.error(f"Failed to log orchestrator event: {e}")

class SecurityEventType:
    """Security event type constants."""
    CREDENTIAL_ACCESS = "credential_access"
    CREDENTIAL_MODIFICATION = "credential_modification"
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    PROMPT_INJECTION_SANITIZED = "prompt_injection_sanitized"
    PROMPT_INJECTION_BLOCKED = "prompt_injection_blocked"
