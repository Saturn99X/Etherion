"""
Tests for enhanced input sanitization system.
"""

import pytest
import re
import base64
from datetime import datetime, timedelta
from src.utils.input_sanitization import InputSanitizer


class TestBasicSanitization:
    """Test basic sanitization functionality."""
    
    def test_sanitize_string_basic(self):
        """Test basic string sanitization."""
        result = InputSanitizer.sanitize_string("Hello World")
        assert result == "Hello World"
    
    def test_sanitize_string_html_escape(self):
        """Test HTML escaping."""
        result = InputSanitizer.sanitize_string("<script>alert('xss')</script>")
        assert result == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
    
    def test_sanitize_string_length_limit(self):
        """Test length limit enforcement."""
        long_string = "a" * 1001
        with pytest.raises(ValueError, match="exceeds maximum length"):
            InputSanitizer.sanitize_string(long_string, max_length=1000)
    
    def test_sanitize_string_pattern_validation(self):
        """Test pattern validation."""
        with pytest.raises(ValueError, match="disallowed characters"):
            InputSanitizer.sanitize_string("hello@world", allowed_pattern=InputSanitizer.ALLOWED_ALPHANUMERIC)
    
    def test_sanitize_string_non_string_input(self):
        """Test non-string input handling."""
        with pytest.raises(ValueError, match="must be a string"):
            InputSanitizer.sanitize_string(123)


class TestSecurityChecks:
    """Test security threat detection."""
    
    def test_detect_dangerous_patterns_script(self):
        """Test script tag detection."""
        patterns = InputSanitizer.detect_dangerous_patterns("<script>alert('xss')</script>")
        assert len(patterns) > 0
        assert any("script" in pattern.lower() for pattern in patterns)
    
    def test_detect_dangerous_patterns_javascript_url(self):
        """Test JavaScript URL detection."""
        patterns = InputSanitizer.detect_dangerous_patterns("javascript:alert('xss')")
        assert len(patterns) > 0
        assert any("javascript" in pattern.lower() for pattern in patterns)
    
    def test_detect_dangerous_patterns_path_traversal(self):
        """Test path traversal detection."""
        patterns = InputSanitizer.detect_dangerous_patterns("../../../etc/passwd")
        assert len(patterns) > 0
        # Check for any dangerous patterns detected
        assert any("dangerous" in pattern.lower() or "suspicious" in pattern.lower() for pattern in patterns)
    
    def test_detect_dangerous_patterns_safe_input(self):
        """Test safe input doesn't trigger warnings."""
        patterns = InputSanitizer.detect_dangerous_patterns("Hello, world!")
        assert len(patterns) == 0
    
    def test_detect_sql_injection_patterns(self):
        """Test SQL injection pattern detection."""
        patterns = InputSanitizer.detect_dangerous_patterns("'; DROP TABLE users; --")
        assert len(patterns) > 0
        assert any("sql" in pattern.lower() for pattern in patterns)
    
    def test_detect_sql_injection_union(self):
        """Test SQL UNION injection detection."""
        patterns = InputSanitizer.detect_dangerous_patterns("' UNION SELECT * FROM users --")
        assert len(patterns) > 0
        assert any("sql" in pattern.lower() for pattern in patterns)


class TestEnhancedSanitization:
    """Test enhanced sanitization with security checks."""
    
    def test_sanitize_with_security_checks_safe(self):
        """Test safe input passes security checks."""
        result = InputSanitizer.sanitize_with_security_checks("Hello, world!")
        assert result == "Hello, world!"
    
    def test_sanitize_with_security_checks_dangerous(self):
        """Test dangerous input is blocked."""
        with pytest.raises(ValueError, match="security threats"):
            InputSanitizer.sanitize_with_security_checks("<script>alert('xss')</script>")
    
    def test_sanitize_with_security_checks_sql_injection(self):
        """Test SQL injection is blocked."""
        with pytest.raises(ValueError, match="SQL injection"):
            InputSanitizer.sanitize_with_security_checks("'; DROP TABLE users; --")
    
    def test_sanitize_with_security_checks_disabled(self):
        """Test security checks can be disabled."""
        result = InputSanitizer.sanitize_with_security_checks(
            "<script>alert('xss')</script>",
            check_dangerous=False,
            check_sql_injection=False
        )
        assert "&lt;script&gt;" in result
    
    def test_sanitize_with_security_checks_length(self):
        """Test length check still works with security checks."""
        long_string = "a" * 1001
        with pytest.raises(ValueError, match="exceeds maximum length"):
            InputSanitizer.sanitize_with_security_checks(long_string, max_length=1000)


class TestEmailValidation:
    """Test email validation and sanitization."""
    
    def test_validate_email_valid(self):
        """Test valid email addresses."""
        valid_emails = [
            "user@example.com",
            "test.email@domain.co.uk",
            "user+tag@example.org"
        ]
        
        for email in valid_emails:
            result = InputSanitizer.validate_email(email)
            assert result == email.lower().strip()
    
    def test_validate_email_invalid_format(self):
        """Test invalid email formats."""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user@.com"
        ]
        
        for email in invalid_emails:
            with pytest.raises(ValueError):
                InputSanitizer.validate_email(email)
    
    def test_validate_email_too_long(self):
        """Test email length limit."""
        long_email = "a" * 250 + "@example.com"
        with pytest.raises(ValueError, match="too long"):
            InputSanitizer.validate_email(long_email)
    
    def test_validate_email_dangerous_patterns(self):
        """Test email with dangerous patterns."""
        with pytest.raises(ValueError):
            InputSanitizer.validate_email("user@example.com<script>alert('xss')</script>")


class TestPhoneValidation:
    """Test phone number validation and sanitization."""
    
    def test_validate_phone_valid(self):
        """Test valid phone numbers."""
        valid_phones = [
            "+1234567890",
            "1234567890",
            "+1-234-567-8900",
            "+1 (234) 567-8900",
            "+1.234.567.8900"
        ]
        
        for phone in valid_phones:
            result = InputSanitizer.validate_phone(phone)
            # Should return cleaned version without formatting
            assert re.match(r'^\+?[1-9]\d{1,14}$', result)
    
    def test_validate_phone_invalid(self):
        """Test invalid phone numbers."""
        invalid_phones = [
            "0123456789",  # Starts with 0
            "abc1234567",  # Contains letters
            "+0123456789",  # Starts with 0 after +
            "12345678901234567890"  # Too long (more than 15 digits)
        ]
        
        for phone in invalid_phones:
            with pytest.raises(ValueError):
                InputSanitizer.validate_phone(phone)


class TestFileUploadSanitization:
    """Test file upload filename sanitization."""
    
    def test_sanitize_file_upload_valid(self):
        """Test valid filenames."""
        valid_files = [
            "document.pdf",
            "image_123.jpg",
            "file-name.txt"
        ]
        
        for filename in valid_files:
            result = InputSanitizer.sanitize_file_upload(filename)
            assert result == filename
    
    def test_sanitize_file_upload_path_traversal(self):
        """Test path traversal prevention."""
        dangerous_files = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "file/with/slashes.txt"
        ]
        
        for filename in dangerous_files:
            with pytest.raises(ValueError, match="path traversal"):
                InputSanitizer.sanitize_file_upload(filename)
    
    def test_sanitize_file_upload_extension_filtering(self):
        """Test file extension filtering."""
        allowed_extensions = ["pdf", "jpg", "png"]
        
        # Valid extension
        result = InputSanitizer.sanitize_file_upload("document.pdf", allowed_extensions)
        assert result == "document.pdf"
        
        # Invalid extension
        with pytest.raises(ValueError, match="not allowed"):
            InputSanitizer.sanitize_file_upload("script.exe", allowed_extensions)
    
    def test_sanitize_file_upload_special_characters(self):
        """Test special character sanitization."""
        result = InputSanitizer.sanitize_file_upload("file with spaces & symbols!.txt")
        assert result == "file_with_spaces___symbols_.txt"
    
    def test_sanitize_file_upload_too_long(self):
        """Test filename length limit."""
        long_filename = "a" * 256 + ".txt"
        with pytest.raises(ValueError, match="too long"):
            InputSanitizer.sanitize_file_upload(long_filename)


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limit_within_limits(self):
        """Test requests within rate limits."""
        identifier = "test_user_123"
        
        # Should pass for first few requests
        for i in range(5):
            assert InputSanitizer.check_rate_limit(identifier, max_per_minute=10, max_per_hour=100)
    
    def test_rate_limit_exceeded_minute(self):
        """Test rate limit exceeded per minute."""
        identifier = "test_user_456"
        
        # Exceed minute limit
        for i in range(11):
            InputSanitizer.check_rate_limit(identifier, max_per_minute=10, max_per_hour=100)
        
        # Should be rate limited
        assert not InputSanitizer.check_rate_limit(identifier, max_per_minute=10, max_per_hour=100)
    
    def test_rate_limit_exceeded_hour(self):
        """Test rate limit exceeded per hour."""
        identifier = "test_user_789"
        
        # Exceed hour limit
        for i in range(101):
            InputSanitizer.check_rate_limit(identifier, max_per_minute=1000, max_per_hour=100)
        
        # Should be rate limited
        assert not InputSanitizer.check_rate_limit(identifier, max_per_minute=1000, max_per_hour=100)


class TestBase64Sanitization:
    """Test base64 data sanitization."""
    
    def test_sanitize_base64_valid(self):
        """Test valid base64 data."""
        data = "SGVsbG8gV29ybGQ="  # "Hello World" in base64
        result = InputSanitizer.sanitize_base64(data)
        assert result == data
    
    def test_sanitize_base64_invalid_format(self):
        """Test invalid base64 format."""
        with pytest.raises(ValueError, match="Invalid base64 format"):
            InputSanitizer.sanitize_base64("Invalid base64!@#")
    
    def test_sanitize_base64_too_large(self):
        """Test base64 data too large."""
        large_data = "A" * (1024 * 1024 * 4 // 3 + 1)  # Larger than 1MB when decoded
        with pytest.raises(ValueError, match="too large"):
            InputSanitizer.sanitize_base64(large_data, max_size=1024 * 1024)
    
    def test_sanitize_base64_dangerous_content(self):
        """Test base64 with dangerous content."""
        dangerous_content = "<script>alert('xss')</script>"
        dangerous_b64 = base64.b64encode(dangerous_content.encode()).decode()
        
        with pytest.raises(ValueError, match="security threats"):
            InputSanitizer.sanitize_base64(dangerous_b64)


class TestSQLIdentifierSanitization:
    """Test SQL identifier sanitization."""
    
    def test_sanitize_sql_identifier_valid(self):
        """Test valid SQL identifiers."""
        valid_identifiers = [
            "user_id",
            "table_name",
            "column_123",
            "_private_column"
        ]
        
        for identifier in valid_identifiers:
            result = InputSanitizer.sanitize_sql_identifier(identifier)
            assert result == identifier
    
    def test_sanitize_sql_identifier_invalid_characters(self):
        """Test SQL identifiers with invalid characters."""
        invalid_identifiers = [
            "user-id",  # Hyphen not allowed
            "user.id",  # Dot not allowed
            "user id",  # Space not allowed
            "123column"  # Cannot start with number
        ]
        
        for identifier in invalid_identifiers:
            with pytest.raises(ValueError, match="invalid characters"):
                InputSanitizer.sanitize_sql_identifier(identifier)
    
    def test_sanitize_sql_identifier_reserved_keywords(self):
        """Test SQL identifiers that are reserved keywords."""
        reserved_keywords = [
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TABLE",
            "WHERE"
        ]
        
        for keyword in reserved_keywords:
            with pytest.raises(ValueError, match="reserved keyword"):
                InputSanitizer.sanitize_sql_identifier(keyword)
    
    def test_sanitize_sql_identifier_too_long(self):
        """Test SQL identifier too long."""
        long_identifier = "a" * 129
        with pytest.raises(ValueError, match="too long"):
            InputSanitizer.sanitize_sql_identifier(long_identifier)


class TestSecurityReport:
    """Test security report generation."""
    
    def test_security_report_safe_input(self):
        """Test security report for safe input."""
        report = InputSanitizer.get_security_report("Hello, world!")
        
        assert report['valid'] is True
        assert len(report['threats']) == 0
        assert report['length'] == 13
        assert report['contains_html'] is False
        assert report['contains_sql'] is False
        assert report['contains_script'] is False
    
    def test_security_report_dangerous_input(self):
        """Test security report for dangerous input."""
        dangerous_input = "<script>alert('xss')</script>"
        report = InputSanitizer.get_security_report(dangerous_input)
        
        assert report['valid'] is False
        assert len(report['threats']) > 0
        assert report['contains_html'] is True
        assert report['contains_script'] is True
        assert len(report['recommendations']) > 0
    
    def test_security_report_sql_injection(self):
        """Test security report for SQL injection."""
        sql_input = "'; DROP TABLE users; --"
        report = InputSanitizer.get_security_report(sql_input)
        
        assert report['valid'] is False
        assert report['contains_sql'] is True
        assert any("sql" in threat.lower() for threat in report['threats'])
    
    def test_security_report_long_input(self):
        """Test security report for long input."""
        long_input = "a" * 15000
        report = InputSanitizer.get_security_report(long_input)
        
        assert report['valid'] is False
        assert report['length'] == 15000
        assert any("unusually long" in threat for threat in report['threats'])
    
    def test_security_report_non_string(self):
        """Test security report for non-string input."""
        report = InputSanitizer.get_security_report(123)
        
        assert report['valid'] is False
        assert report['error'] == 'Input must be a string'


class TestInputHashing:
    """Test input hashing functionality."""
    
    def test_generate_input_hash(self):
        """Test input hash generation."""
        input_value = "Hello, world!"
        hash1 = InputSanitizer.generate_input_hash(input_value)
        hash2 = InputSanitizer.generate_input_hash(input_value)
        
        # Same input should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 character hex string
    
    def test_generate_input_hash_with_salt(self):
        """Test input hash generation with salt."""
        input_value = "Hello, world!"
        salt = "random_salt"
        
        hash1 = InputSanitizer.generate_input_hash(input_value, salt)
        hash2 = InputSanitizer.generate_input_hash(input_value, "different_salt")
        
        # Different salts should produce different hashes
        assert hash1 != hash2
    
    def test_generate_input_hash_non_string(self):
        """Test input hash generation with non-string input."""
        hash_result = InputSanitizer.generate_input_hash(123)
        assert len(hash_result) == 64
        assert isinstance(hash_result, str)


class TestJSONSanitization:
    """Test JSON payload sanitization."""
    
    def test_sanitize_json_payload_valid(self):
        """Test valid JSON payload sanitization."""
        payload = {"name": "John", "age": 30, "email": "john@example.com"}
        result = InputSanitizer.sanitize_json_payload(payload)
        
        assert result == payload
    
    def test_sanitize_json_payload_string_input(self):
        """Test JSON string input sanitization."""
        payload_str = '{"name": "John", "age": 30}'
        result = InputSanitizer.sanitize_json_payload(payload_str)
        
        assert result == {"name": "John", "age": 30}
    
    def test_sanitize_json_payload_invalid_json(self):
        """Test invalid JSON handling."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            InputSanitizer.sanitize_json_payload('{"name": "John", "age": 30')
    
    def test_sanitize_json_payload_too_large(self):
        """Test JSON payload size limit."""
        large_payload = {"data": "x" * (1024 * 1024 + 1)}
        with pytest.raises(ValueError, match="exceeds maximum size"):
            InputSanitizer.sanitize_json_payload(large_payload, max_size=1024 * 1024)
    
    def test_sanitize_json_payload_too_deep(self):
        """Test JSON payload depth limit."""
        deep_payload = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "level5": {
                                "level6": {
                                    "level7": {
                                        "level8": {
                                            "level9": {
                                                "level10": {
                                                    "level11": "value"
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        with pytest.raises(ValueError, match="exceeds maximum nesting depth"):
            InputSanitizer.sanitize_json_payload(deep_payload, max_depth=10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
