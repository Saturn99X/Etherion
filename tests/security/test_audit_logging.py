# tests/security/test_audit_logging.py
"""
Comprehensive tests for audit logging functionality.
Tests audit event creation, logging, and security event tracking.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from src.core.security.audit_logger import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    AuditLogger,
    log_authentication_success,
    log_authentication_failure,
    log_authorization_failure,
    log_data_access,
    log_security_violation,
    log_rate_limit_exceeded,
    log_input_validation_failure,
    audit_logger
)


class TestAuditEvent:
    """Test cases for AuditEvent class."""
    
    def test_audit_event_creation(self):
        """Test AuditEvent creation."""
        event = AuditEvent(
            event_id="test123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            user_id="user123",
            tenant_id="tenant123",
            session_id="session123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            endpoint="/auth/login",
            method="POST",
            request_id="req123",
            details={"test": "data"},
            success=True
        )
        
        assert event.event_id == "test123"
        assert event.event_type == AuditEventType.AUTHENTICATION_SUCCESS
        assert event.severity == AuditSeverity.LOW
        assert event.user_id == "user123"
        assert event.success is True
    
    def test_audit_event_to_dict(self):
        """Test AuditEvent to_dict conversion."""
        event = AuditEvent(
            event_id="test123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            user_id="user123",
            tenant_id="tenant123",
            session_id="session123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            endpoint="/auth/login",
            method="POST",
            request_id="req123",
            details={"test": "data"},
            success=True
        )
        
        event_dict = event.to_dict()
        
        assert isinstance(event_dict, dict)
        assert event_dict["event_id"] == "test123"
        assert event_dict["event_type"] == "authentication_success"
        assert event_dict["severity"] == "low"
        assert event_dict["user_id"] == "user123"
        assert event_dict["success"] is True
        assert "timestamp" in event_dict
    
    def test_audit_event_to_json(self):
        """Test AuditEvent to_json conversion."""
        event = AuditEvent(
            event_id="test123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            user_id="user123",
            tenant_id="tenant123",
            session_id="session123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            endpoint="/auth/login",
            method="POST",
            request_id="req123",
            details={"test": "data"},
            success=True
        )
        
        event_json = event.to_json()
        
        assert isinstance(event_json, str)
        event_data = json.loads(event_json)
        assert event_data["event_id"] == "test123"
        assert event_data["event_type"] == "authentication_success"


class TestAuditLogger:
    """Test cases for AuditLogger class."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for log files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def mock_audit_logger(self, temp_log_dir):
        """Create a mock AuditLogger with temporary directory."""
        with patch('src.core.security.audit_logger.Path') as mock_path:
            mock_path.return_value = temp_log_dir
            logger = AuditLogger()
            return logger
    
    def test_audit_logger_initialization(self, mock_audit_logger):
        """Test AuditLogger initialization."""
        assert mock_audit_logger.log_dir is not None
        assert mock_audit_logger.retention_days == 90
        assert mock_audit_logger.max_file_size > 0
        assert "main" in mock_audit_logger.loggers
        assert "security" in mock_audit_logger.loggers
        assert "auth" in mock_audit_logger.loggers
        assert "data" in mock_audit_logger.loggers
    
    def test_generate_event_id(self, mock_audit_logger):
        """Test event ID generation."""
        event_data = {"test": "data", "timestamp": datetime.utcnow().isoformat()}
        event_id = mock_audit_logger._generate_event_id(event_data)
        
        assert isinstance(event_id, str)
        assert len(event_id) == 16
        
        # Same data should generate same ID
        event_id2 = mock_audit_logger._generate_event_id(event_data)
        assert event_id == event_id2
        
        # Different data should generate different ID
        event_data2 = {"test": "different", "timestamp": datetime.utcnow().isoformat()}
        event_id3 = mock_audit_logger._generate_event_id(event_data2)
        assert event_id != event_id3
    
    @pytest.mark.asyncio
    async def test_log_event_success(self, mock_audit_logger):
        """Test successful event logging."""
        event = AuditEvent(
            event_id="test123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            user_id="user123",
            tenant_id="tenant123",
            session_id="session123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            endpoint="/auth/login",
            method="POST",
            request_id="req123",
            details={"test": "data"},
            success=True
        )
        
        with patch.object(mock_audit_logger, '_log_to_file') as mock_log_file:
            with patch.object(mock_audit_logger, '_publish_to_redis') as mock_redis:
                await mock_audit_logger.log_event(event)
                
                mock_log_file.assert_called_once_with(event)
                mock_redis.assert_called_once_with(event)
    
    @pytest.mark.asyncio
    async def test_log_event_failure(self, mock_audit_logger):
        """Test event logging with failure."""
        event = AuditEvent(
            event_id="test123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            user_id="user123",
            tenant_id="tenant123",
            session_id="session123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            endpoint="/auth/login",
            method="POST",
            request_id="req123",
            details={"test": "data"},
            success=True
        )
        
        with patch.object(mock_audit_logger, '_log_to_file', side_effect=Exception("Log failed")):
            with patch('src.core.security.audit_logger.logger') as mock_logger:
                # Should not raise exception, just log error
                await mock_audit_logger.log_event(event)
                mock_logger.error.assert_called()
    
    @pytest.mark.asyncio
    async def test_publish_to_redis_success(self, mock_audit_logger):
        """Test successful Redis publishing."""
        event = AuditEvent(
            event_id="test123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            user_id="user123",
            tenant_id="tenant123",
            session_id="session123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            endpoint="/auth/login",
            method="POST",
            request_id="req123",
            details={"test": "data"},
            success=True
        )
        
        mock_redis = AsyncMock()
        mock_redis.publish.return_value = 1
        
        with patch.object(mock_audit_logger, '_get_redis_client', return_value=mock_redis):
            await mock_audit_logger._publish_to_redis(event)
            
            # Should publish to multiple channels
            assert mock_redis.publish.call_count >= 3
            mock_redis.publish.assert_any_call("audit:events", event.to_json())
            mock_redis.publish.assert_any_call("audit:low", event.to_json())
            mock_redis.publish.assert_any_call("audit:tenant:tenant123", event.to_json())
    
    @pytest.mark.asyncio
    async def test_publish_to_redis_failure(self, mock_audit_logger):
        """Test Redis publishing with failure."""
        event = AuditEvent(
            event_id="test123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            user_id="user123",
            tenant_id="tenant123",
            session_id="session123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            endpoint="/auth/login",
            method="POST",
            request_id="req123",
            details={"test": "data"},
            success=True
        )
        
        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = Exception("Redis connection failed")
        
        with patch.object(mock_audit_logger, '_get_redis_client', return_value=mock_redis):
            with patch('src.core.security.audit_logger.logger') as mock_logger:
                # Should not raise exception, just log error
                await mock_audit_logger._publish_to_redis(event)
                mock_logger.error.assert_called()
    
    @pytest.mark.asyncio
    async def test_cleanup_old_logs(self, mock_audit_logger):
        """Test cleanup of old log files."""
        # Create some mock log files
        old_file = mock_audit_logger.log_dir / "old.log"
        new_file = mock_audit_logger.log_dir / "new.log"
        
        old_file.touch()
        new_file.touch()
        
        # Mock file modification times
        old_time = (datetime.utcnow() - timedelta(days=100)).timestamp()
        new_time = datetime.utcnow().timestamp()
        
        with patch.object(Path, 'stat') as mock_stat:
            def mock_stat_side_effect(self):
                stat = Mock()
                if self.name == "old.log":
                    stat.st_mtime = old_time
                else:
                    stat.st_mtime = new_time
                return stat
            
            mock_stat.side_effect = mock_stat_side_effect
            
            with patch.object(Path, 'unlink') as mock_unlink:
                with patch('src.core.security.audit_logger.logger') as mock_logger:
                    await mock_audit_logger.cleanup_old_logs()
                    
                    # Should delete old file but not new file
                    mock_unlink.assert_called_once_with(old_file)
                    mock_logger.info.assert_called()


class TestAuditLoggingFunctions:
    """Test cases for audit logging convenience functions."""
    
    @pytest.mark.asyncio
    async def test_log_authentication_success(self):
        """Test authentication success logging."""
        with patch.object(audit_logger, 'log_event') as mock_log_event:
            await log_authentication_success(
                user_id="user123",
                tenant_id="tenant123",
                ip_address="127.0.0.1",
                user_agent="test-agent",
                session_id="session123",
                details={"provider": "google"}
            )
            
            mock_log_event.assert_called_once()
            event = mock_log_event.call_args[0][0]
            assert event.event_type == AuditEventType.AUTHENTICATION_SUCCESS
            assert event.severity == AuditSeverity.LOW
            assert event.user_id == "user123"
            assert event.tenant_id == "tenant123"
            assert event.success is True
    
    @pytest.mark.asyncio
    async def test_log_authentication_failure(self):
        """Test authentication failure logging."""
        with patch.object(audit_logger, 'log_event') as mock_log_event:
            await log_authentication_failure(
                user_id="user123",
                tenant_id="tenant123",
                ip_address="127.0.0.1",
                user_agent="test-agent",
                reason="Invalid credentials",
                session_id="session123",
                details={"attempts": 3}
            )
            
            mock_log_event.assert_called_once()
            event = mock_log_event.call_args[0][0]
            assert event.event_type == AuditEventType.AUTHENTICATION_FAILURE
            assert event.severity == AuditSeverity.MEDIUM
            assert event.user_id == "user123"
            assert event.tenant_id == "tenant123"
            assert event.success is False
            assert event.error_message == "Invalid credentials"
    
    @pytest.mark.asyncio
    async def test_log_authorization_failure(self):
        """Test authorization failure logging."""
        with patch.object(audit_logger, 'log_event') as mock_log_event:
            await log_authorization_failure(
                user_id="user123",
                tenant_id="tenant123",
                ip_address="127.0.0.1",
                user_agent="test-agent",
                endpoint="/admin/users",
                method="GET",
                reason="Insufficient permissions",
                session_id="session123",
                details={"required_permission": "manage_users"}
            )
            
            mock_log_event.assert_called_once()
            event = mock_log_event.call_args[0][0]
            assert event.event_type == AuditEventType.AUTHORIZATION_FAILURE
            assert event.severity == AuditSeverity.HIGH
            assert event.user_id == "user123"
            assert event.tenant_id == "tenant123"
            assert event.success is False
            assert event.error_message == "Insufficient permissions"
    
    @pytest.mark.asyncio
    async def test_log_data_access(self):
        """Test data access logging."""
        with patch.object(audit_logger, 'log_event') as mock_log_event:
            await log_data_access(
                user_id="user123",
                tenant_id="tenant123",
                ip_address="127.0.0.1",
                user_agent="test-agent",
                endpoint="/api/projects",
                method="GET",
                data_type="project",
                operation="read",
                session_id="session123",
                details={"project_id": 1}
            )
            
            mock_log_event.assert_called_once()
            event = mock_log_event.call_args[0][0]
            assert event.event_type == AuditEventType.DATA_ACCESS
            assert event.severity == AuditSeverity.LOW
            assert event.user_id == "user123"
            assert event.tenant_id == "tenant123"
            assert event.success is True
    
    @pytest.mark.asyncio
    async def test_log_security_violation(self):
        """Test security violation logging."""
        with patch.object(audit_logger, 'log_event') as mock_log_event:
            await log_security_violation(
                user_id="user123",
                tenant_id="tenant123",
                ip_address="127.0.0.1",
                user_agent="test-agent",
                endpoint="/api/users",
                method="POST",
                violation_type="SQL injection attempt",
                details={"query": "'; DROP TABLE users; --"},
                session_id="session123"
            )
            
            mock_log_event.assert_called_once()
            event = mock_log_event.call_args[0][0]
            assert event.event_type == AuditEventType.SECURITY_VIOLATION
            assert event.severity == AuditSeverity.CRITICAL
            assert event.user_id == "user123"
            assert event.tenant_id == "tenant123"
            assert event.success is False
            assert event.error_message == "Security violation: SQL injection attempt"
    
    @pytest.mark.asyncio
    async def test_log_rate_limit_exceeded(self):
        """Test rate limit exceeded logging."""
        with patch.object(audit_logger, 'log_event') as mock_log_event:
            await log_rate_limit_exceeded(
                ip_address="127.0.0.1",
                user_agent="test-agent",
                endpoint="/auth/login",
                method="POST",
                limit_type="per minute",
                limit_value=10,
                current_count=15,
                details={"window": "minute"}
            )
            
            mock_log_event.assert_called_once()
            event = mock_log_event.call_args[0][0]
            assert event.event_type == AuditEventType.RATE_LIMIT_EXCEEDED
            assert event.severity == AuditSeverity.MEDIUM
            assert event.ip_address == "127.0.0.1"
            assert event.success is False
            assert event.error_message == "Rate limit exceeded: 15/10 per minute"
    
    @pytest.mark.asyncio
    async def test_log_input_validation_failure(self):
        """Test input validation failure logging."""
        with patch.object(audit_logger, 'log_event') as mock_log_event:
            await log_input_validation_failure(
                user_id="user123",
                tenant_id="tenant123",
                ip_address="127.0.0.1",
                user_agent="test-agent",
                endpoint="/api/projects",
                method="POST",
                validation_errors=["Name is required", "Description too long"],
                input_data={"name": "", "description": "x" * 1000},
                session_id="session123"
            )
            
            mock_log_event.assert_called_once()
            event = mock_log_event.call_args[0][0]
            assert event.event_type == AuditEventType.INPUT_VALIDATION_FAILURE
            assert event.severity == AuditSeverity.MEDIUM
            assert event.user_id == "user123"
            assert event.tenant_id == "tenant123"
            assert event.success is False
            assert "Input validation failed" in event.error_message


class TestAuditEventTypes:
    """Test cases for audit event types and severities."""
    
    def test_audit_event_types(self):
        """Test that all audit event types are defined."""
        expected_types = [
            "authentication_success",
            "authentication_failure",
            "authorization_success",
            "authorization_failure",
            "data_access",
            "data_modification",
            "admin_action",
            "security_violation",
            "rate_limit_exceeded",
            "input_validation_failure",
            "sql_injection_attempt",
            "xss_attempt",
            "csrf_attempt",
            "file_upload",
            "file_download",
            "api_access",
            "system_error"
        ]
        
        for event_type in expected_types:
            assert hasattr(AuditEventType, event_type.upper())
    
    def test_audit_severities(self):
        """Test that all audit severities are defined."""
        expected_severities = ["low", "medium", "high", "critical"]
        
        for severity in expected_severities:
            assert hasattr(AuditSeverity, severity.upper())
    
    def test_severity_hierarchy(self):
        """Test that severity hierarchy is logical."""
        assert AuditSeverity.LOW.value == "low"
        assert AuditSeverity.MEDIUM.value == "medium"
        assert AuditSeverity.HIGH.value == "high"
        assert AuditSeverity.CRITICAL.value == "critical"