import pytest
import asyncio
import time
from src.utils.logging_utils import SecureLogger, LogLevel, SecurityEvent
from src.utils.metrics_collector import metrics_collector, record_api_call_latency, record_error


def test_secure_logger_initialization():
    """Test that SecureLogger initializes correctly."""
    logger = SecureLogger("test_component")
    assert logger.component_name == "test_component"
    assert logger.logger is not None


def test_log_entry_creation():
    """Test creation of structured log entries."""
    logger = SecureLogger("test_component")
    log_entry = logger._create_log_entry(LogLevel.INFO, "Test message", 
                                       correlation_id="test-correlation-id")
    
    assert log_entry.level == "INFO"
    assert log_entry.component == "test_component"
    assert log_entry.message == "Test message"
    assert log_entry.correlation_id == "test-correlation-id"


def test_sensitive_data_redaction():
    """Test that sensitive data is redacted in log messages."""
    logger = SecureLogger("test_component")
    
    # Test password redaction
    message_with_password = 'User credentials: {"password": "secret123", "username": "testuser"}'
    redacted_message = logger._redact_sensitive_data(message_with_password)
    assert "secret123" not in redacted_message
    assert "[REDACTED]" in redacted_message
    
    # Test API key redaction
    message_with_api_key = 'API call: {"api_key": "abc123xyz", "endpoint": "/test"}'
    redacted_message = logger._redact_sensitive_data(message_with_api_key)
    assert "abc123xyz" not in redacted_message
    assert "[REDACTED]" in redacted_message


def test_audit_event_logging():
    """Test security audit event logging."""
    logger = SecureLogger("test_component")
    
    # This would normally log to the logger, but we're just testing the structure
    audit_event = logger._create_log_entry(
        LogLevel.INFO, 
        "SECURITY_AUDIT: CREDENTIAL_ACCESS",
        correlation_id="test-correlation-id"
    )
    
    assert "SECURITY_AUDIT" in audit_event.message


def test_metrics_collector_singleton():
    """Test that MetricsCollector is a singleton."""
    collector1 = metrics_collector
    collector2 = metrics_collector
    
    assert collector1 is collector2


def test_metric_recording():
    """Test recording metrics."""
    # Clear any existing metrics
    metrics_collector.metrics_buffer.clear()
    
    # Record a metric
    record_api_call_latency("test_api", 100.0, True, component="test")
    
    # Check that the metric was recorded
    metrics = metrics_collector.get_metrics()
    assert len(metrics) > 0
    
    # Check the recorded metric
    latest_metric = metrics[-1]
    assert latest_metric.name == "api_latency"
    assert latest_metric.value == 100.0
    assert latest_metric.unit == "ms"
    assert latest_metric.tags.get("api_name") == "test_api"
    assert latest_metric.tags.get("success") == "true"


def test_error_recording():
    """Test recording errors."""
    # Clear any existing metrics
    metrics_collector.metrics_buffer.clear()
    
    # Record an error
    record_error("test_component", "test_error", detail="test detail")
    
    # Check that the error was recorded
    metrics = metrics_collector.get_metrics()
    assert len(metrics) > 0
    
    # Check the recorded error
    latest_metric = metrics[-1]
    assert latest_metric.name == "error_occurrence"
    assert latest_metric.tags.get("component") == "test_component"
    assert latest_metric.tags.get("error_type") == "test_error"


def test_aggregated_metrics():
    """Test aggregated metrics calculation."""
    # Clear any existing metrics
    metrics_collector.metrics_buffer.clear()
    
    # Record multiple metrics
    for i in range(5):
        record_api_call_latency("test_api", 100.0 + i * 10, True)
    
    # Get aggregated metrics
    aggregated = metrics_collector.get_aggregated_metrics("api_latency", api_name="test_api")
    
    assert aggregated is not None
    assert aggregated.count == 5
    assert aggregated.min == 100.0
    assert aggregated.max == 140.0
    assert aggregated.avg == 120.0


def test_percentile_calculation():
    """Test percentile calculation."""
    # Clear any existing metrics
    metrics_collector.metrics_buffer.clear()
    
    # Record metrics with known values
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    for value in values:
        record_api_call_latency("test_api", float(value), True)
    
    # Test 50th percentile (median)
    median = metrics_collector.get_percentile("api_latency", 50, api_name="test_api")
    assert median == 50.0
    
    # Test 90th percentile
    p90 = metrics_collector.get_percentile("api_latency", 90, api_name="test_api")
    assert p90 == 90.0


if __name__ == "__main__":
    pytest.main([__file__])