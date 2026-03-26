"""
Tenant isolation and cross-tenant access prevention.

This module provides comprehensive security measures to prevent cross-tenant
credential access and ensure proper tenant isolation throughout the application.
"""

import os
import time
import hashlib
import logging
from typing import Dict, Any, Optional, Set, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from contextvars import ContextVar
from src.utils.logging_utils import get_logger, SecurityEvent
from src.utils.tenant_context import get_tenant_context, set_tenant_context
from .audit_logger import log_tenant_isolation_violation, log_security_violation


# Context variable for tracking the current request's tenant context
_request_tenant_context: ContextVar[Optional[str]] = ContextVar('request_tenant_context', default=None)
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


@dataclass
class TenantAccessAttempt:
    """Represents a tenant access attempt for audit logging."""
    timestamp: datetime
    tenant_id: str
    resource_type: str
    resource_id: str
    action: str
    success: bool
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None


@dataclass
class TenantIsolationViolation:
    """Represents a detected tenant isolation violation."""
    timestamp: datetime
    violation_type: str
    attempted_tenant_id: str
    actual_tenant_id: str
    resource_type: str
    resource_id: str
    severity: str
    source_ip: Optional[str] = None
    request_id: Optional[str] = None


class TenantIsolationGuard:
    """
    Comprehensive tenant isolation guard that prevents cross-tenant access
    and provides audit logging for security events.
    """
    
    def __init__(self):
        self.logger = get_logger("tenant_isolation")
        
        # Track recent access attempts for anomaly detection
        self._access_attempts: Dict[str, List[TenantAccessAttempt]] = {}
        self._violations: List[TenantIsolationViolation] = []
        
        # Configuration
        self._max_attempts_per_minute = int(os.getenv('TENANT_MAX_ATTEMPTS_PER_MINUTE', '100'))
        self._violation_threshold = int(os.getenv('TENANT_VIOLATION_THRESHOLD', '5'))
        self._block_duration_minutes = int(os.getenv('TENANT_BLOCK_DURATION_MINUTES', '15'))
        
        # Blocked tenants (in-memory, in production this would be in Redis/DB)
        self._blocked_tenants: Dict[str, datetime] = {}
        
        # Allowed resource patterns for each tenant
        self._tenant_resource_patterns: Dict[str, Set[str]] = {}
        
        self.logger.info("TenantIsolationGuard initialized", 
                        max_attempts_per_minute=self._max_attempts_per_minute,
                        violation_threshold=self._violation_threshold)
    
    def validate_tenant_access(self, tenant_id: str, resource_type: str, 
                             resource_id: str, action: str) -> bool:
        """
        Validate that a tenant can access a specific resource.
        
        Args:
            tenant_id: The tenant attempting access
            resource_type: Type of resource (e.g., 'secret', 'database', 'api')
            resource_id: Specific resource identifier
            action: Action being performed (e.g., 'read', 'write', 'delete')
            
        Returns:
            True if access is allowed, False otherwise
        """
        current_time = datetime.utcnow()
        request_id = _request_id.get()
        
        # Check if tenant is blocked
        if self._is_tenant_blocked(tenant_id):
            self._log_violation(
                violation_type="blocked_tenant_access",
                attempted_tenant_id=tenant_id,
                actual_tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                severity="HIGH",
                request_id=request_id
            )
            return False
        
        # Validate resource ownership
        if not self._validate_resource_ownership(tenant_id, resource_type, resource_id):
            self._log_violation(
                violation_type="unauthorized_resource_access",
                attempted_tenant_id=tenant_id,
                actual_tenant_id=self._get_resource_owner(resource_type, resource_id),
                resource_type=resource_type,
                resource_id=resource_id,
                severity="CRITICAL",
                request_id=request_id
            )
            return False
        
        # Check rate limits
        if not self._check_rate_limits(tenant_id):
            self._log_violation(
                violation_type="rate_limit_exceeded",
                attempted_tenant_id=tenant_id,
                actual_tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                severity="MEDIUM",
                request_id=request_id
            )
            return False
        
        # Log successful access attempt
        self._log_access_attempt(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            success=True,
            request_id=request_id
        )
        
        return True
    
    def validate_tenant_context(self, expected_tenant_id: str) -> bool:
        """
        Validate that the current request context matches the expected tenant.
        
        Args:
            expected_tenant_id: The tenant ID that should be in the current context
            
        Returns:
            True if context matches, False otherwise
        """
        current_tenant_id = get_tenant_context()
        request_tenant_id = _request_tenant_context.get()

        # If no context is set (e.g., in tests), allow the operation
        if current_tenant_id is None and request_tenant_id is None:
            return True

        exp = str(expected_tenant_id)

        # Validate current tenant context if present
        if current_tenant_id is not None and str(current_tenant_id) != exp:
            self._log_violation(
                violation_type="context_mismatch",
                attempted_tenant_id=exp,
                actual_tenant_id=str(current_tenant_id),
                resource_type="context",
                resource_id="tenant_context",
                severity="HIGH"
            )
            return False

        # Validate request tenant context if present
        if request_tenant_id is not None and str(request_tenant_id) != exp:
            self._log_violation(
                violation_type="context_mismatch",
                attempted_tenant_id=exp,
                actual_tenant_id=str(request_tenant_id),
                resource_type="context",
                resource_id="tenant_context",
                severity="HIGH"
            )
            return False

        return True
    
    def enforce_tenant_isolation(self, tenant_id: str, resource_type: str, 
                               resource_id: str, action: str) -> bool:
        """
        Enforce tenant isolation for a specific operation.
        
        Args:
            tenant_id: The tenant performing the operation
            resource_type: Type of resource being accessed
            resource_id: Specific resource identifier
            action: Action being performed
            
        Returns:
            True if operation is allowed, False otherwise
        """
        # Validate tenant access
        if not self.validate_tenant_access(tenant_id, resource_type, resource_id, action):
            return False
        
        # Validate tenant context
        if not self.validate_tenant_context(tenant_id):
            return False
        
        # Additional security checks
        if not self._perform_additional_security_checks(tenant_id, resource_type, resource_id):
            return False
        
        return True
    
    def _is_tenant_blocked(self, tenant_id: str) -> bool:
        """Check if a tenant is currently blocked."""
        if tenant_id in self._blocked_tenants:
            block_until = self._blocked_tenants[tenant_id]
            if datetime.utcnow() < block_until:
                return True
            else:
                # Remove expired block
                del self._blocked_tenants[tenant_id]
        return False
    
    def _validate_resource_ownership(self, tenant_id: str, resource_type: str, 
                                   resource_id: str) -> bool:
        """Validate that a tenant owns the resource they're trying to access."""
        # For secrets, check the naming convention
        if resource_type == "secret":
            return self._validate_secret_ownership(tenant_id, resource_id)
        
        # For database resources, check tenant_id in the resource_id
        if resource_type == "database":
            return self._validate_database_ownership(tenant_id, resource_id)
        
        # For API resources, check tenant patterns
        if resource_type == "api":
            return self._validate_api_ownership(tenant_id, resource_id)
        
        # Default: allow if no specific validation is needed
        return True
    
    def _validate_secret_ownership(self, tenant_id: str, secret_id: str) -> bool:
        """Validate that a tenant owns a secret based on naming convention."""
        # Secret naming convention: {tenant_id}--{service_name}--{key_type}
        if not secret_id.startswith(f"{tenant_id}--"):
            return False
        
        # Additional validation: ensure the tenant_id in the secret matches
        parts = secret_id.split("--")
        if len(parts) >= 1 and parts[0] != tenant_id:
            return False
        
        return True
    
    def _validate_database_ownership(self, tenant_id: str, resource_id: str) -> bool:
        """Validate that a tenant owns a database resource."""
        # Database resources should contain tenant_id
        return tenant_id in resource_id
    
    def _validate_api_ownership(self, tenant_id: str, resource_id: str) -> bool:
        """Validate that a tenant owns an API resource."""
        # API resources should be tenant-scoped
        return tenant_id in resource_id
    
    def _get_resource_owner(self, resource_type: str, resource_id: str) -> str:
        """Get the owner of a resource."""
        if resource_type == "secret":
            parts = resource_id.split("--")
            return parts[0] if parts else "unknown"
        
        # For other resource types, extract tenant_id from resource_id
        if "tenant-" in resource_id:
            # Extract tenant ID from resource ID
            parts = resource_id.split("-")
            for i, part in enumerate(parts):
                if part == "tenant" and i + 1 < len(parts):
                    return f"tenant-{parts[i + 1]}"
        
        return "unknown"
    
    def _check_rate_limits(self, tenant_id: str) -> bool:
        """Check if tenant is within rate limits."""
        current_time = datetime.utcnow()
        minute_ago = current_time - timedelta(minutes=1)
        
        # Get recent attempts for this tenant
        if tenant_id not in self._access_attempts:
            self._access_attempts[tenant_id] = []
        
        attempts = self._access_attempts[tenant_id]
        
        # Remove old attempts
        attempts[:] = [attempt for attempt in attempts if attempt.timestamp > minute_ago]
        
        # Check if within limits
        if len(attempts) >= self._max_attempts_per_minute:
            return False
        
        return True
    
    def _perform_additional_security_checks(self, tenant_id: str, resource_type: str, 
                                          resource_id: str) -> bool:
        """Perform additional security checks."""
        # Check for suspicious patterns
        if self._detect_suspicious_patterns(tenant_id, resource_type, resource_id):
            return False
        
        # Check for privilege escalation attempts
        if self._detect_privilege_escalation(tenant_id, resource_type, resource_id):
            return False
        
        return True
    
    def _detect_suspicious_patterns(self, tenant_id: str, resource_type: str, 
                                  resource_id: str) -> bool:
        """Detect suspicious access patterns."""
        # Check for rapid access to multiple resources
        current_time = datetime.utcnow()
        minute_ago = current_time - timedelta(minutes=1)
        
        if tenant_id in self._access_attempts:
            recent_attempts = [
                attempt for attempt in self._access_attempts[tenant_id]
                if attempt.timestamp > minute_ago
            ]
            
            # If accessing many different resources in a short time
            unique_resources = set(attempt.resource_id for attempt in recent_attempts)
            if len(unique_resources) > 20:  # Suspicious if accessing >20 different resources per minute
                return True
        
        return False
    
    def _detect_privilege_escalation(self, tenant_id: str, resource_type: str, 
                                   resource_id: str) -> bool:
        """Detect privilege escalation attempts."""
        # Check for attempts to access system-level resources
        if resource_type == "secret" and "system" in resource_id.lower():
            return True
        
        # Check for attempts to access admin resources
        if "admin" in resource_id.lower() or "root" in resource_id.lower():
            return True
        
        return False
    
    def _log_access_attempt(self, tenant_id: str, resource_type: str, resource_id: str,
                          action: str, success: bool, request_id: Optional[str] = None):
        """Log a tenant access attempt."""
        attempt = TenantAccessAttempt(
            timestamp=datetime.utcnow(),
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            success=success,
            request_id=request_id
        )
        
        if tenant_id not in self._access_attempts:
            self._access_attempts[tenant_id] = []
        
        self._access_attempts[tenant_id].append(attempt)
        
        # Log the attempt
        self.logger.info("Tenant access attempt",
                        tenant_id=tenant_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        action=action,
                        success=success,
                        request_id=request_id)
    
    def _log_violation(self, violation_type: str, attempted_tenant_id: str,
                      actual_tenant_id: str, resource_type: str, resource_id: str,
                      severity: str, source_ip: Optional[str] = None,
                      request_id: Optional[str] = None):
        """Log a tenant isolation violation."""
        violation = TenantIsolationViolation(
            timestamp=datetime.utcnow(),
            violation_type=violation_type,
            attempted_tenant_id=attempted_tenant_id,
            actual_tenant_id=actual_tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            severity=severity,
            source_ip=source_ip,
            request_id=request_id
        )
        
        self._violations.append(violation)
        
        # Log security event using enhanced audit logger
        if violation_type == "unauthorized_resource_access":
            log_tenant_isolation_violation(
                component="tenant_isolation",
                attempted_tenant=attempted_tenant_id,
                actual_tenant=actual_tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                user_id=None  # Could be extracted from request context
            )
        else:
            log_security_violation(
                component="tenant_isolation",
                violation_type=violation_type,
                tenant_id=attempted_tenant_id,
                details={
                    "attempted_tenant_id": attempted_tenant_id,
                    "actual_tenant_id": actual_tenant_id,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "request_id": request_id
                }
            )
        
        # Check if tenant should be blocked
        self._check_violation_threshold(attempted_tenant_id)
    
    def _check_violation_threshold(self, tenant_id: str):
        """Check if tenant has exceeded violation threshold and should be blocked."""
        current_time = datetime.utcnow()
        hour_ago = current_time - timedelta(hours=1)
        
        # Count recent violations for this tenant
        recent_violations = [
            violation for violation in self._violations
            if (violation.attempted_tenant_id == tenant_id and 
                violation.timestamp > hour_ago)
        ]
        
        if len(recent_violations) >= self._violation_threshold:
            # Block the tenant
            block_until = current_time + timedelta(minutes=self._block_duration_minutes)
            self._blocked_tenants[tenant_id] = block_until
            
            self.logger.log_audit_event(
                SecurityEvent.SECURITY_VIOLATION,
                "CRITICAL",
                {
                    "violation_type": "tenant_blocked",
                    "tenant_id": tenant_id,
                    "violation_count": len(recent_violations),
                    "block_until": block_until.isoformat()
                }
            )
    
    def get_tenant_security_status(self, tenant_id: str) -> Dict[str, Any]:
        """Get security status for a tenant."""
        current_time = datetime.utcnow()
        hour_ago = current_time - timedelta(hours=1)
        
        # Get recent violations
        recent_violations = [
            violation for violation in self._violations
            if (violation.attempted_tenant_id == tenant_id and 
                violation.timestamp > hour_ago)
        ]
        
        # Get recent access attempts
        recent_attempts = []
        if tenant_id in self._access_attempts:
            recent_attempts = [
                attempt for attempt in self._access_attempts[tenant_id]
                if attempt.timestamp > hour_ago
            ]
        
        return {
            "tenant_id": tenant_id,
            "is_blocked": self._is_tenant_blocked(tenant_id),
            "block_until": self._blocked_tenants.get(tenant_id),
            "recent_violations": len(recent_violations),
            "recent_access_attempts": len(recent_attempts),
            "violation_threshold": self._violation_threshold,
            "max_attempts_per_minute": self._max_attempts_per_minute
        }
    
    def get_security_metrics(self) -> Dict[str, Any]:
        """Get overall security metrics."""
        current_time = datetime.utcnow()
        hour_ago = current_time - timedelta(hours=1)
        
        # Count recent violations by type
        recent_violations = [
            violation for violation in self._violations
            if violation.timestamp > hour_ago
        ]
        
        violation_counts = {}
        for violation in recent_violations:
            violation_counts[violation.violation_type] = violation_counts.get(violation.violation_type, 0) + 1
        
        return {
            "total_violations_last_hour": len(recent_violations),
            "violations_by_type": violation_counts,
            "blocked_tenants": len(self._blocked_tenants),
            "active_tenants": len(self._access_attempts),
            "violation_threshold": self._violation_threshold,
            "max_attempts_per_minute": self._max_attempts_per_minute
        }


# Global tenant isolation guard instance
_tenant_isolation_guard = TenantIsolationGuard()


def get_tenant_isolation_guard() -> TenantIsolationGuard:
    """Get the global tenant isolation guard instance."""
    return _tenant_isolation_guard


def validate_tenant_access(tenant_id: str, resource_type: str, resource_id: str, 
                         action: str) -> bool:
    """Validate tenant access using the global guard."""
    return _tenant_isolation_guard.validate_tenant_access(tenant_id, resource_type, resource_id, action)


def enforce_tenant_isolation(tenant_id: str, resource_type: str, resource_id: str, 
                           action: str) -> bool:
    """Enforce tenant isolation using the global guard."""
    return _tenant_isolation_guard.enforce_tenant_isolation(tenant_id, resource_type, resource_id, action)


def set_request_context(tenant_id: str, request_id: str):
    """Set the request context for tenant isolation."""
    _request_tenant_context.set(tenant_id)
    _request_id.set(request_id)
    set_tenant_context(int(tenant_id.split('-')[-1]) if tenant_id.startswith('tenant-') else int(tenant_id))


def clear_request_context():
    """Clear the request context."""
    _request_tenant_context.set(None)
    _request_id.set(None)
    set_tenant_context(None)
