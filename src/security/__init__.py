"""
Security module for Etherion AI.

This module provides comprehensive security features including tenant isolation,
cross-tenant access prevention, and security event logging.
"""

from .tenant_isolation import (
    TenantIsolationGuard,
    TenantAccessAttempt,
    TenantIsolationViolation,
    get_tenant_isolation_guard,
    validate_tenant_access,
    enforce_tenant_isolation,
    set_request_context,
    clear_request_context
)

from .audit_logger import (
    AuditLogger,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    AuditMetrics,
    get_audit_logger,
    log_audit_event,
    log_security_violation,
    log_tenant_isolation_violation,
    log_credential_access,
    log_data_access
)

__all__ = [
    'TenantIsolationGuard',
    'TenantAccessAttempt', 
    'TenantIsolationViolation',
    'get_tenant_isolation_guard',
    'validate_tenant_access',
    'enforce_tenant_isolation',
    'set_request_context',
    'clear_request_context',
    'AuditLogger',
    'AuditEvent',
    'AuditEventType',
    'AuditSeverity',
    'AuditMetrics',
    'get_audit_logger',
    'log_audit_event',
    'log_security_violation',
    'log_tenant_isolation_violation',
    'log_credential_access',
    'log_data_access'
]
