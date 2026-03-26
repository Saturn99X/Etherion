"""
Comprehensive audit logging system for security events.

This module provides enhanced audit logging capabilities for tracking security events,
compliance requirements, and forensic analysis.
"""

import os
import json
import time
import hashlib
import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import threading
from collections import defaultdict, deque
from src.utils.logging_utils import get_logger, SecurityEvent, LogLevel


class AuditEventType(Enum):
    """Types of audit events."""
    # Authentication and Authorization
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    PASSWORD_RESET = "PASSWORD_RESET"
    TOKEN_ISSUED = "TOKEN_ISSUED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    PERMISSION_GRANTED = "PERMISSION_GRANTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    
    # Data Access
    DATA_ACCESS = "DATA_ACCESS"
    DATA_CREATE = "DATA_CREATE"
    DATA_UPDATE = "DATA_UPDATE"
    DATA_DELETE = "DATA_DELETE"
    DATA_EXPORT = "DATA_EXPORT"
    DATA_IMPORT = "DATA_IMPORT"
    
    # System Events
    SYSTEM_STARTUP = "SYSTEM_STARTUP"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    SERVICE_START = "SERVICE_START"
    SERVICE_STOP = "SERVICE_STOP"
    
    # Security Events
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    INTRUSION_DETECTED = "INTRUSION_DETECTED"
    MALWARE_DETECTED = "MALWARE_DETECTED"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # Tenant Events
    TENANT_CREATED = "TENANT_CREATED"
    TENANT_UPDATED = "TENANT_UPDATED"
    TENANT_DELETED = "TENANT_DELETED"
    TENANT_ISOLATION_VIOLATION = "TENANT_ISOLATION_VIOLATION"
    CROSS_TENANT_ACCESS_ATTEMPT = "CROSS_TENANT_ACCESS_ATTEMPT"
    
    # Credential Events
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    CREDENTIAL_CREATED = "CREDENTIAL_CREATED"
    CREDENTIAL_UPDATED = "CREDENTIAL_UPDATED"
    CREDENTIAL_DELETED = "CREDENTIAL_DELETED"
    CREDENTIAL_EXPOSED = "CREDENTIAL_EXPOSED"
    
    # API Events
    API_ACCESS = "API_ACCESS"
    API_RATE_LIMIT = "API_RATE_LIMIT"
    API_ERROR = "API_ERROR"
    API_SECURITY_VIOLATION = "API_SECURITY_VIOLATION"
    
    # Database Events
    DATABASE_ACCESS = "DATABASE_ACCESS"
    DATABASE_QUERY = "DATABASE_QUERY"
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_BACKUP = "DATABASE_BACKUP"
    DATABASE_RESTORE = "DATABASE_RESTORE"
    
    # Network Events
    NETWORK_ACCESS = "NETWORK_ACCESS"
    NETWORK_BLOCKED = "NETWORK_BLOCKED"
    NETWORK_SECURITY_VIOLATION = "NETWORK_SECURITY_VIOLATION"
    
    # Compliance Events
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"
    COMPLIANCE_VIOLATION = "COMPLIANCE_VIOLATION"
    DATA_RETENTION_POLICY = "DATA_RETENTION_POLICY"
    PRIVACY_REQUEST = "PRIVACY_REQUEST"


class AuditSeverity(Enum):
    """Severity levels for audit events."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class AuditEvent:
    """Represents an audit event."""
    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    component: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    risk_score: Optional[float] = None
    correlation_id: Optional[str] = None
    tags: Optional[List[str]] = None


@dataclass
class AuditMetrics:
    """Audit metrics for monitoring."""
    total_events: int = 0
    events_by_type: Dict[str, int] = None
    events_by_severity: Dict[str, int] = None
    events_by_component: Dict[str, int] = None
    events_by_tenant: Dict[str, int] = None
    high_risk_events: int = 0
    violations: int = 0
    last_updated: Optional[datetime] = None
    
    def __post_init__(self):
        if self.events_by_type is None:
            self.events_by_type = defaultdict(int)
        if self.events_by_severity is None:
            self.events_by_severity = defaultdict(int)
        if self.events_by_component is None:
            self.events_by_component = defaultdict(int)
        if self.events_by_tenant is None:
            self.events_by_tenant = defaultdict(int)


class AuditLogger:
    """
    Comprehensive audit logger for security events.
    
    Provides structured logging, metrics collection, and compliance reporting
    for security events across the application.
    """
    
    def __init__(self):
        self.logger = get_logger("audit_logger")
        
        # Configuration
        self.enabled = os.getenv('AUDIT_LOGGING_ENABLED', 'true').lower() == 'true'
        self.log_level = os.getenv('AUDIT_LOG_LEVEL', 'INFO').upper()
        self.retention_days = int(os.getenv('AUDIT_RETENTION_DAYS', '90'))
        self.max_events_in_memory = int(os.getenv('AUDIT_MAX_EVENTS_MEMORY', '10000'))
        
        # Storage
        self._events: deque = deque(maxlen=self.max_events_in_memory)
        self._metrics = AuditMetrics()
        self._lock = threading.RLock()
        
        # File logging - use /tmp for Cloud Run compatibility (read-only root filesystem)
        self.audit_log_file = os.getenv('AUDIT_LOG_FILE', '/tmp/logs/audit.log')
        self._ensure_log_directory()
        
        # Risk scoring
        self.risk_weights = {
            AuditEventType.LOGIN_FAILURE: 0.3,
            AuditEventType.SECURITY_VIOLATION: 0.9,
            AuditEventType.TENANT_ISOLATION_VIOLATION: 0.8,
            AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT: 0.7,
            AuditEventType.CREDENTIAL_EXPOSED: 0.9,
            AuditEventType.INTRUSION_DETECTED: 1.0,
            AuditEventType.MALWARE_DETECTED: 1.0,
            AuditEventType.SUSPICIOUS_ACTIVITY: 0.6,
            AuditEventType.RATE_LIMIT_EXCEEDED: 0.4,
            AuditEventType.API_SECURITY_VIOLATION: 0.7,
            AuditEventType.NETWORK_SECURITY_VIOLATION: 0.8,
            AuditEventType.COMPLIANCE_VIOLATION: 0.5,
        }
        
        self.logger.info("AuditLogger initialized", 
                        enabled=self.enabled,
                        log_level=self.log_level,
                        retention_days=self.retention_days,
                        max_events_memory=self.max_events_in_memory)
    
    def _ensure_log_directory(self):
        """Ensure the log directory exists."""
        log_dir = Path(self.audit_log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_event_id(self, event_type: AuditEventType, timestamp: datetime) -> str:
        """Generate a unique event ID."""
        timestamp_str = timestamp.isoformat()
        content = f"{event_type.value}_{timestamp_str}_{os.getpid()}_{threading.get_ident()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _calculate_risk_score(self, event_type: AuditEventType, details: Dict[str, Any]) -> float:
        """Calculate risk score for an event."""
        base_score = self.risk_weights.get(event_type, 0.1)
        
        # Adjust based on details
        if details:
            # Multiple failed attempts
            if 'attempt_count' in details and details['attempt_count'] > 3:
                base_score += 0.2
            
            # Cross-tenant access
            if 'cross_tenant' in details and details['cross_tenant']:
                base_score += 0.3
            
            # Privilege escalation
            if 'privilege_escalation' in details and details['privilege_escalation']:
                base_score += 0.4
            
            # Data exposure
            if 'data_exposed' in details and details['data_exposed']:
                base_score += 0.5
        
        return min(base_score, 1.0)
    
    def log_event(self, event_type: AuditEventType, severity: AuditSeverity,
                  component: str, user_id: Optional[str] = None,
                  tenant_id: Optional[str] = None, session_id: Optional[str] = None,
                  request_id: Optional[str] = None, ip_address: Optional[str] = None,
                  user_agent: Optional[str] = None, resource_type: Optional[str] = None,
                  resource_id: Optional[str] = None, action: Optional[str] = None,
                  result: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
                  tags: Optional[List[str]] = None) -> str:
        """
        Log an audit event.
        
        Returns:
            str: The event ID
        """
        if not self.enabled:
            return ""
        
        timestamp = datetime.now(timezone.utc)
        event_id = self._generate_event_id(event_type, timestamp)
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(event_type, details or {})
        
        # Create audit event
        audit_event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type,
            severity=severity,
            component=component,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            result=result,
            details=details,
            risk_score=risk_score,
            correlation_id=request_id,
            tags=tags
        )
        
        with self._lock:
            # Store event
            self._events.append(audit_event)
            
            # Update metrics
            self._update_metrics(audit_event)
            
            # Log to file
            self._write_to_file(audit_event)
            
            # Log to structured logger
            self._log_to_structured_logger(audit_event)
        
        return event_id
    
    def _update_metrics(self, event: AuditEvent):
        """Update audit metrics."""
        self._metrics.total_events += 1
        self._metrics.events_by_type[event.event_type.value] += 1
        self._metrics.events_by_severity[event.severity.value] += 1
        self._metrics.events_by_component[event.component] += 1
        
        if event.tenant_id:
            self._metrics.events_by_tenant[event.tenant_id] += 1
        
        if event.risk_score and event.risk_score > 0.7:
            self._metrics.high_risk_events += 1
        
        if event.severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL]:
            self._metrics.violations += 1
        
        self._metrics.last_updated = event.timestamp
    
    def _write_to_file(self, event: AuditEvent):
        """Write audit event to file."""
        try:
            with open(self.audit_log_file, 'a') as f:
                event_dict = asdict(event)
                # Convert datetime to ISO string
                event_dict['timestamp'] = event.timestamp.isoformat()
                f.write(json.dumps(event_dict) + '\n')
        except Exception as e:
            self.logger.error("Failed to write audit event to file", 
                            event_id=event.event_id, error=str(e))
    
    def _log_to_structured_logger(self, event: AuditEvent):
        """Log to structured logger."""
        log_data = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "component": event.component,
            "user_id": event.user_id,
            "tenant_id": event.tenant_id,
            "session_id": event.session_id,
            "request_id": event.request_id,
            "ip_address": event.ip_address,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "action": event.action,
            "result": event.result,
            "risk_score": event.risk_score,
            "details": event.details,
            "tags": event.tags
        }
        
        # Remove None values
        log_data = {k: v for k, v in log_data.items() if v is not None}
        
        if event.severity == AuditSeverity.CRITICAL:
            self.logger.critical(f"AUDIT_EVENT: {event.event_type.value}", **log_data)
        elif event.severity == AuditSeverity.HIGH:
            self.logger.error(f"AUDIT_EVENT: {event.event_type.value}", **log_data)
        elif event.severity == AuditSeverity.MEDIUM:
            self.logger.warning(f"AUDIT_EVENT: {event.event_type.value}", **log_data)
        else:
            self.logger.info(f"AUDIT_EVENT: {event.event_type.value}", **log_data)
    
    def get_events(self, event_type: Optional[AuditEventType] = None,
                   severity: Optional[AuditSeverity] = None,
                   component: Optional[str] = None,
                   tenant_id: Optional[str] = None,
                   user_id: Optional[str] = None,
                   limit: int = 100) -> List[AuditEvent]:
        """Get audit events with optional filtering."""
        with self._lock:
            events = list(self._events)
        
        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if severity:
            events = [e for e in events if e.severity == severity]
        if component:
            events = [e for e in events if e.component == component]
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        
        # Sort by timestamp (newest first)
        events.sort(key=lambda e: e.timestamp, reverse=True)
        
        return events[:limit]
    
    def get_high_risk_events(self, limit: int = 50) -> List[AuditEvent]:
        """Get high-risk audit events."""
        with self._lock:
            events = [e for e in self._events if e.risk_score and e.risk_score > 0.7]
        
        events.sort(key=lambda e: e.risk_score, reverse=True)
        return events[:limit]
    
    def get_metrics(self) -> AuditMetrics:
        """Get audit metrics."""
        with self._lock:
            return AuditMetrics(
                total_events=self._metrics.total_events,
                events_by_type=dict(self._metrics.events_by_type),
                events_by_severity=dict(self._metrics.events_by_severity),
                events_by_component=dict(self._metrics.events_by_component),
                events_by_tenant=dict(self._metrics.events_by_tenant),
                high_risk_events=self._metrics.high_risk_events,
                violations=self._metrics.violations,
                last_updated=self._metrics.last_updated
            )
    
    def get_compliance_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate a compliance report for the specified date range."""
        with self._lock:
            events = [e for e in self._events 
                     if start_date <= e.timestamp <= end_date]
        
        report = {
            "report_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "total_events": len(events),
            "events_by_type": defaultdict(int),
            "events_by_severity": defaultdict(int),
            "high_risk_events": 0,
            "violations": 0,
            "tenant_activity": defaultdict(int),
            "user_activity": defaultdict(int),
            "security_events": [],
            "compliance_violations": []
        }
        
        for event in events:
            report["events_by_type"][event.event_type.value] += 1
            report["events_by_severity"][event.severity.value] += 1
            
            if event.risk_score and event.risk_score > 0.7:
                report["high_risk_events"] += 1
            
            if event.severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL]:
                report["violations"] += 1
            
            if event.tenant_id:
                report["tenant_activity"][event.tenant_id] += 1
            
            if event.user_id:
                report["user_activity"][event.user_id] += 1
            
            # Security events
            if event.event_type in [
                AuditEventType.SECURITY_VIOLATION,
                AuditEventType.INTRUSION_DETECTED,
                AuditEventType.MALWARE_DETECTED,
                AuditEventType.SUSPICIOUS_ACTIVITY,
                AuditEventType.TENANT_ISOLATION_VIOLATION,
                AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT
            ]:
                report["security_events"].append({
                    "event_id": event.event_id,
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type.value,
                    "severity": event.severity.value,
                    "component": event.component,
                    "user_id": event.user_id,
                    "tenant_id": event.tenant_id,
                    "details": event.details
                })
            
            # Compliance violations
            if event.event_type == AuditEventType.COMPLIANCE_VIOLATION:
                report["compliance_violations"].append({
                    "event_id": event.event_id,
                    "timestamp": event.timestamp.isoformat(),
                    "details": event.details
                })
        
        # Convert defaultdicts to regular dicts
        report["events_by_type"] = dict(report["events_by_type"])
        report["events_by_severity"] = dict(report["events_by_severity"])
        report["tenant_activity"] = dict(report["tenant_activity"])
        report["user_activity"] = dict(report["user_activity"])
        
        return report
    
    def clear_old_events(self, days: int = None):
        """Clear events older than specified days."""
        if days is None:
            days = self.retention_days
        
        cutoff_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)
        
        with self._lock:
            # Remove old events
            self._events = deque([e for e in self._events if e.timestamp >= cutoff_date], 
                               maxlen=self.max_events_in_memory)
        
        self.logger.info("Cleared old audit events", 
                        cutoff_date=cutoff_date.isoformat(),
                        remaining_events=len(self._events))


# Global audit logger instance
_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    return _audit_logger


def log_audit_event(event_type: AuditEventType, severity: AuditSeverity,
                   component: str, **kwargs) -> str:
    """Log an audit event using the global audit logger."""
    return _audit_logger.log_event(event_type, severity, component, **kwargs)


def log_security_violation(component: str, violation_type: str, 
                          user_id: Optional[str] = None,
                          tenant_id: Optional[str] = None,
                          details: Optional[Dict[str, Any]] = None) -> str:
    """Log a security violation."""
    return log_audit_event(
        AuditEventType.SECURITY_VIOLATION,
        AuditSeverity.HIGH,
        component,
        user_id=user_id,
        tenant_id=tenant_id,
        details={"violation_type": violation_type, **(details or {})}
    )


def log_tenant_isolation_violation(component: str, attempted_tenant: str,
                                  actual_tenant: str, resource_type: str,
                                  resource_id: str, user_id: Optional[str] = None) -> str:
    """Log a tenant isolation violation."""
    return log_audit_event(
        AuditEventType.TENANT_ISOLATION_VIOLATION,
        AuditSeverity.CRITICAL,
        component,
        user_id=user_id,
        tenant_id=attempted_tenant,
        resource_type=resource_type,
        resource_id=resource_id,
        details={
            "attempted_tenant": attempted_tenant,
            "actual_tenant": actual_tenant,
            "cross_tenant": True
        }
    )


def log_credential_access(component: str, credential_type: str,
                         tenant_id: str, user_id: Optional[str] = None,
                         success: bool = True, details: Optional[Dict[str, Any]] = None) -> str:
    """Log credential access."""
    return log_audit_event(
        AuditEventType.CREDENTIAL_ACCESS,
        AuditSeverity.MEDIUM if success else AuditSeverity.HIGH,
        component,
        user_id=user_id,
        tenant_id=tenant_id,
        resource_type="credential",
        action="access",
        result="success" if success else "failure",
        details={"credential_type": credential_type, **(details or {})}
    )


def log_data_access(component: str, data_type: str, action: str,
                   tenant_id: str, user_id: Optional[str] = None,
                   success: bool = True, details: Optional[Dict[str, Any]] = None) -> str:
    """Log data access."""
    return log_audit_event(
        AuditEventType.DATA_ACCESS,
        AuditSeverity.LOW if success else AuditSeverity.MEDIUM,
        component,
        user_id=user_id,
        tenant_id=tenant_id,
        resource_type="data",
        resource_id=data_type,
        action=action,
        result="success" if success else "failure",
        details=details
    )
