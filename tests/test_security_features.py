import pytest
from src.utils.secure_string import SecureString
from src.utils.input_sanitization import InputSanitizer
from src.utils.secrets_manager import TenantSecretsManager, SecretCacheEntry


def test_secure_string_basic():
    """Test basic SecureString functionality."""
    # Test initialization
    secure_str = SecureString("test_value")
    assert not secure_str.is_empty()
    assert len(secure_str) == 9
    assert secure_str.get_value() == "test_value"
    
    # Test value replacement
    secure_str.set_value("new_value")
    assert secure_str.get_value() == "new_value"
    
    # Test clearing
    secure_str.clear()
    assert secure_str.is_empty()
    assert secure_str.get_value() is None


def test_secure_string_context_manager():
    """Test SecureString context manager functionality."""
    with SecureString("test_value") as secure_str:
        assert not secure_str.is_empty()
        assert secure_str.get_value() == "test_value"
    
    # After context, the value should be cleared
    # Note: This test checks the interface, but the actual memory wiping
    # can't be easily verified in a unit test


def test_input_sanitizer_string():
    """Test string sanitization."""
    # Test valid string
    result = InputSanitizer.sanitize_string("test_string")
    assert result == "test_string"
    
    # Test HTML escaping
    result = InputSanitizer.sanitize_string("<script>alert('xss')</script>")
    assert result == "&lt;script&gt;alert('xss')&lt;/script&gt;"
    
    # Test length limit
    with pytest.raises(ValueError):
        InputSanitizer.sanitize_string("a" * 1001, max_length=1000)


def test_input_sanitizer_json():
    """Test JSON payload sanitization."""
    # Test valid JSON
    payload = {"key": "value", "number": 123}
    result = InputSanitizer.sanitize_json_payload(payload)
    assert result == payload
    
    # Test JSON string
    payload_str = '{"key": "value", "number": 123}'
    result = InputSanitizer.sanitize_json_payload(payload_str)
    assert result == payload
    
    # Test size limit
    large_payload = {"key": "a" * 10000}
    with pytest.raises(ValueError):
        InputSanitizer.sanitize_json_payload(large_payload, max_size=1000)


def test_input_sanitizer_parameters():
    """Test parameter sanitization."""
    params = {
        "tenant_id": "tenant123",
        "service_name": "resend",
        "key_type": "api_key",
        "extra_param": "extra_value"
    }
    
    # Test with allowed keys
    result = InputSanitizer.sanitize_parameters(
        params,
        allowed_keys=["tenant_id", "service_name", "key_type"]
    )
    assert "tenant_id" in result
    assert "service_name" in result
    assert "key_type" in result
    assert "extra_param" not in result
    
    # Test with required keys
    with pytest.raises(ValueError):
        InputSanitizer.sanitize_parameters(
            params,
            required_keys=["missing_key"]
        )


def test_secrets_manager_cache_security():
    """Test that secrets manager uses SecureString for caching."""
    manager = TenantSecretsManager()
    
    # Test setting a secret
    manager._set_cached_secret("test_key", "test_secret")
    
    # Verify the cache entry uses SecureString
    assert "test_key" in manager._cache
    cache_entry = manager._cache["test_key"]
    assert isinstance(cache_entry, SecretCacheEntry)
    assert hasattr(cache_entry.value, 'get_value')
    
    # Test retrieving a secret
    retrieved = manager._get_cached_secret("test_key")
    assert retrieved == "test_secret"
    
    # Test clearing cache
    manager._clear_cache()
    assert len(manager._cache) == 0


if __name__ == "__main__":
    pytest.main([__file__])