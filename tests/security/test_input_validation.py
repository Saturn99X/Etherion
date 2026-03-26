# tests/security/test_input_validation.py
"""
Comprehensive tests for input validation and security features.
Tests SQL injection protection, XSS prevention, and input sanitization.
"""

import pytest
from pydantic import ValidationError

from src.etherion_ai.graphql_schema.input_validators import (
    GoalInputValidator,
    FeedbackInputValidator,
    SupportTicketInputValidator,
    TenantInputValidator,
    ProjectInputValidator,
    ConversationInputValidator,
    detect_sql_injection,
    detect_xss,
    detect_path_traversal,
    sanitize_text,
    validate_security,
    SQL_INJECTION_PATTERNS,
    XSS_PATTERNS,
    PATH_TRAVERSAL_PATTERNS
)


class TestSecurityDetection:
    """Test cases for security threat detection."""
    
    def test_detect_sql_injection_select(self):
        """Test SQL injection detection for SELECT statements."""
        malicious_inputs = [
            "'; SELECT * FROM users; --",
            "1' OR '1'='1",
            "admin'--",
            "1' UNION SELECT password FROM users--",
            "'; DROP TABLE users; --",
            "1' AND 1=1--",
            "admin' OR 1=1#",
            "1'; EXEC xp_cmdshell('dir'); --",
        ]
        
        for malicious_input in malicious_inputs:
            assert detect_sql_injection(malicious_input) is True, f"Failed to detect SQL injection: {malicious_input}"
    
    def test_detect_sql_injection_legitimate(self):
        """Test that legitimate inputs are not flagged as SQL injection."""
        legitimate_inputs = [
            "Hello world",
            "Create a new project",
            "User wants to delete their account",
            "SELECT is a reserved word but this is just text",
            "I need to update my profile",
            "Please insert a new record",
        ]
        
        for legitimate_input in legitimate_inputs:
            assert detect_sql_injection(legitimate_input) is False, f"False positive for SQL injection: {legitimate_input}"
    
    def test_detect_xss_script_tags(self):
        """Test XSS detection for script tags."""
        malicious_inputs = [
            "<script>alert('XSS')</script>",
            "<script src='malicious.js'></script>",
            "<SCRIPT>alert('XSS')</SCRIPT>",
            "<script>document.cookie='stolen'</script>",
            "<img src=x onerror=alert('XSS')>",
            "<iframe src='javascript:alert(1)'></iframe>",
            "<object data='javascript:alert(1)'></object>",
            "<embed src='javascript:alert(1)'>",
            "<link rel='stylesheet' href='javascript:alert(1)'>",
            "<meta http-equiv='refresh' content='0;url=javascript:alert(1)'>",
            "<style>body{background:url('javascript:alert(1)')}</style>",
        ]
        
        for malicious_input in malicious_inputs:
            assert detect_xss(malicious_input) is True, f"Failed to detect XSS: {malicious_input}"
    
    def test_detect_xss_event_handlers(self):
        """Test XSS detection for event handlers."""
        malicious_inputs = [
            "<div onload='alert(1)'>",
            "<img onerror='alert(1)'>",
            "<button onclick='alert(1)'>",
            "<input onfocus='alert(1)'>",
            "<form onsubmit='alert(1)'>",
            "<select onchange='alert(1)'>",
        ]
        
        for malicious_input in malicious_inputs:
            assert detect_xss(malicious_input) is True, f"Failed to detect XSS: {malicious_input}"
    
    def test_detect_xss_legitimate(self):
        """Test that legitimate HTML is not flagged as XSS."""
        legitimate_inputs = [
            "<p>Hello world</p>",
            "<strong>Bold text</strong>",
            "<em>Italic text</em>",
            "<a href='https://example.com'>Link</a>",
            "<img src='https://example.com/image.jpg' alt='Image'>",
            "<div class='container'>Content</div>",
        ]
        
        for legitimate_input in legitimate_inputs:
            assert detect_xss(legitimate_input) is False, f"False positive for XSS: {legitimate_input}"
    
    def test_detect_path_traversal(self):
        """Test path traversal detection."""
        malicious_inputs = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "%2e%2e%5c%2e%2e%5c%2e%2e%5cwindows%5csystem32",
            "..%252f..%252f..%252fetc%252fpasswd",
            "..%255c..%255c..%255cwindows%255csystem32",
        ]
        
        for malicious_input in malicious_inputs:
            assert detect_path_traversal(malicious_input) is True, f"Failed to detect path traversal: {malicious_input}"
    
    def test_detect_path_traversal_legitimate(self):
        """Test that legitimate paths are not flagged as path traversal."""
        legitimate_inputs = [
            "documents/report.pdf",
            "images/photo.jpg",
            "data/export.csv",
            "uploads/file.txt",
            "static/css/style.css",
            "templates/index.html",
        ]
        
        for legitimate_input in legitimate_inputs:
            assert detect_path_traversal(legitimate_input) is False, f"False positive for path traversal: {legitimate_input}"
    
    def test_sanitize_text(self):
        """Test text sanitization."""
        test_cases = [
            ("<script>alert('XSS')</script>Hello", "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;Hello"),
            ("<p>Hello</p><script>alert('XSS')</script>", "&lt;p&gt;Hello&lt;/p&gt;&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;"),
            ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)&gt;"),
            ("Hello & goodbye", "Hello &amp; goodbye"),
            ("<div>Content</div>", "&lt;div&gt;Content&lt;/div&gt;"),
            ("", ""),
            (None, None),
        ]
        
        for input_text, expected in test_cases:
            result = sanitize_text(input_text)
            assert result == expected, f"Sanitization failed for: {input_text}"
    
    def test_validate_security_raises_exception(self):
        """Test that validate_security raises exceptions for malicious input."""
        malicious_inputs = [
            "'; SELECT * FROM users; --",
            "<script>alert('XSS')</script>",
            "../../../etc/passwd",
        ]
        
        for malicious_input in malicious_inputs:
            with pytest.raises(ValueError):
                validate_security(malicious_input, "test_field")
    
    def test_validate_security_passes_legitimate(self):
        """Test that validate_security passes for legitimate input."""
        legitimate_inputs = [
            "Hello world",
            "Create a new project",
            "User wants to update their profile",
            "<p>This is safe HTML</p>",
            "documents/report.pdf",
        ]
        
        for legitimate_input in legitimate_inputs:
            # Should not raise an exception
            validate_security(legitimate_input, "test_field")


class TestInputValidators:
    """Test cases for Pydantic input validators."""
    
    def test_goal_input_validator_success(self):
        """Test successful GoalInput validation."""
        valid_data = {
            "goal": "Create a new project",
            "context": "This is a test project",
            "output_format_instructions": "Please provide a summary",
            "user_id": "user123"
        }
        
        validator = GoalInputValidator(**valid_data)
        assert validator.goal == "Create a new project"
        assert validator.context == "This is a test project"
        assert validator.user_id == "user123"
    
    def test_goal_input_validator_sql_injection(self):
        """Test GoalInput validation with SQL injection attempt."""
        malicious_data = {
            "goal": "'; DROP TABLE users; --",
            "context": "Test context",
            "output_format_instructions": "Test instructions",
            "user_id": "user123"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            GoalInputValidator(**malicious_data)
        
        assert "Potential SQL injection detected" in str(exc_info.value)
    
    def test_goal_input_validator_xss(self):
        """Test GoalInput validation with XSS attempt."""
        malicious_data = {
            "goal": "<script>alert('XSS')</script>",
            "context": "Test context",
            "output_format_instructions": "Test instructions",
            "user_id": "user123"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            GoalInputValidator(**malicious_data)
        
        assert "Potential XSS detected" in str(exc_info.value)
    
    def test_goal_input_validator_length_validation(self):
        """Test GoalInput validation with length constraints."""
        # Test goal too long
        long_goal = "x" * 2001
        data = {
            "goal": long_goal,
            "context": "Test context",
            "output_format_instructions": "Test instructions",
            "user_id": "user123"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            GoalInputValidator(**data)
        
        assert "String should have at most 2000 characters" in str(exc_info.value)
    
    def test_feedback_input_validator_success(self):
        """Test successful FeedbackInput validation."""
        valid_data = {
            "job_id": "job123",
            "user_id": "user123",
            "goal": "Test goal",
            "final_output": "Test output",
            "feedback_score": 4,
            "feedback_comment": "Good work!"
        }
        
        validator = FeedbackInputValidator(**valid_data)
        assert validator.job_id == "job123"
        assert validator.feedback_score == 4
        assert validator.feedback_comment == "Good work!"
    
    def test_feedback_input_validator_score_validation(self):
        """Test FeedbackInput validation with invalid score."""
        data = {
            "job_id": "job123",
            "user_id": "user123",
            "goal": "Test goal",
            "final_output": "Test output",
            "feedback_score": 6,  # Invalid score (should be 1-5)
            "feedback_comment": "Good work!"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            FeedbackInputValidator(**data)
        
        assert "Input should be less than or equal to 5" in str(exc_info.value)
    
    def test_support_ticket_validator_success(self):
        """Test successful SupportTicketInput validation."""
        valid_data = {
            "ticket_text": "I need help with my account",
            "user_id": "user123",
            "order_id": "order123",
            "attached_files": ["https://example.com/file.pdf"]
        }
        
        validator = SupportTicketInputValidator(**valid_data)
        assert validator.ticket_text == "I need help with my account"
        assert validator.order_id == "order123"
        assert validator.attached_files == ["https://example.com/file.pdf"]
    
    def test_support_ticket_validator_invalid_url(self):
        """Test SupportTicketInput validation with invalid URL."""
        data = {
            "ticket_text": "I need help with my account",
            "user_id": "user123",
            "order_id": "order123",
            "attached_files": ["invalid-url"]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            SupportTicketInputValidator(**data)
        
        assert "Invalid URL in attached files" in str(exc_info.value)
    
    def test_tenant_input_validator_success(self):
        """Test successful TenantInput validation."""
        valid_data = {
            "name": "Test Company",
            "admin_email": "admin@test.com",
            "password": "SecurePass123"
        }
        
        validator = TenantInputValidator(**valid_data)
        assert validator.name == "Test Company"
        assert validator.admin_email == "admin@test.com"
        assert validator.password == "SecurePass123"
    
    def test_tenant_input_validator_invalid_email(self):
        """Test TenantInput validation with invalid email."""
        data = {
            "name": "Test Company",
            "admin_email": "invalid-email",
            "password": "SecurePass123"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TenantInputValidator(**data)
        
        assert "Invalid email format" in str(exc_info.value)
    
    def test_tenant_input_validator_weak_password(self):
        """Test TenantInput validation with weak password."""
        data = {
            "name": "Test Company",
            "admin_email": "admin@test.com",
            "password": "weak"  # No uppercase, no digit
        }
        
        with pytest.raises(ValidationError) as exc_info:
            TenantInputValidator(**data)
        
        assert "String should have at least 8 characters" in str(exc_info.value)
    
    def test_project_input_validator_success(self):
        """Test successful ProjectInput validation."""
        valid_data = {
            "name": "Test Project",
            "description": "A test project description"
        }
        
        validator = ProjectInputValidator(**valid_data)
        assert validator.name == "Test Project"
        assert validator.description == "A test project description"
    
    def test_conversation_input_validator_success(self):
        """Test successful ConversationInput validation."""
        valid_data = {
            "title": "Test Conversation",
            "project_id": 1
        }
        
        validator = ConversationInputValidator(**valid_data)
        assert validator.title == "Test Conversation"
        assert validator.project_id == 1
    
    def test_conversation_input_validator_invalid_project_id(self):
        """Test ConversationInput validation with invalid project ID."""
        data = {
            "title": "Test Conversation",
            "project_id": 0  # Invalid (should be > 0)
        }
        
        with pytest.raises(ValidationError) as exc_info:
            ConversationInputValidator(**data)
        
        assert "Input should be greater than 0" in str(exc_info.value)


class TestSecurityPatterns:
    """Test cases for security pattern detection."""
    
    def test_sql_injection_patterns_comprehensive(self):
        """Test comprehensive SQL injection pattern detection."""
        test_cases = [
            ("SELECT * FROM users", True),
            ("INSERT INTO users VALUES", True),
            ("UPDATE users SET", True),
            ("DELETE FROM users", True),
            ("DROP TABLE users", True),
            ("CREATE TABLE test", True),
            ("ALTER TABLE users", True),
            ("EXEC sp_executesql", True),
            ("UNION SELECT password", True),
            ("1' OR '1'='1", True),
            ("admin'--", True),
            ("1' AND 1=1--", True),
            ("WAITFOR DELAY '00:00:05'", True),
            ("BENCHMARK(5000000,MD5(1))", True),
            ("SLEEP(5)", True),
            ("PG_SLEEP(5)", True),
            ("Hello world", False),
            ("Create a new project", False),
            ("User wants to delete their account", False),
        ]
        
        for input_text, should_detect in test_cases:
            result = detect_sql_injection(input_text)
            assert result == should_detect, f"SQL injection detection failed for: {input_text}"
    
    def test_xss_patterns_comprehensive(self):
        """Test comprehensive XSS pattern detection."""
        test_cases = [
            ("<script>alert(1)</script>", True),
            ("javascript:alert(1)", True),
            ("vbscript:alert(1)", True),
            ("onload=alert(1)", True),
            ("onerror=alert(1)", True),
            ("onclick=alert(1)", True),
            ("<iframe src=javascript:alert(1)>", True),
            ("<object data=javascript:alert(1)>", True),
            ("<embed src=javascript:alert(1)>", True),
            ("<link href=javascript:alert(1)>", True),
            ("<meta http-equiv=refresh content=0;url=javascript:alert(1)>", True),
            ("<style>body{background:url(javascript:alert(1))}</style>", True),
            ("expression(alert(1))", True),
            ("url(javascript:alert(1))", True),
            ("@import url(javascript:alert(1))", True),
            ("<p>Hello world</p>", False),
            ("<strong>Bold text</strong>", False),
            ("<a href='https://example.com'>Link</a>", False),
            ("<img src='https://example.com/image.jpg' alt='Image'>", False),
        ]
        
        for input_text, should_detect in test_cases:
            result = detect_xss(input_text)
            assert result == should_detect, f"XSS detection failed for: {input_text}"
    
    def test_path_traversal_patterns_comprehensive(self):
        """Test comprehensive path traversal pattern detection."""
        test_cases = [
            ("../../../etc/passwd", True),
            ("..\\..\\..\\windows\\system32", True),
            ("%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd", True),
            ("%2e%2e%5c%2e%2e%5c%2e%2e%5cwindows%5csystem32", True),
            ("..%252f..%252f..%252fetc%252fpasswd", True),
            ("..%255c..%255c..%255cwindows%255csystem32", True),
            ("documents/report.pdf", False),
            ("images/photo.jpg", False),
            ("data/export.csv", False),
            ("uploads/file.txt", False),
            ("static/css/style.css", False),
            ("templates/index.html", False),
        ]
        
        for input_text, should_detect in test_cases:
            result = detect_path_traversal(input_text)
            assert result == should_detect, f"Path traversal detection failed for: {input_text}"
