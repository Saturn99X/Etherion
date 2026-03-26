# src/utils/input_sanitization.py
import re
import json
import html
import base64
import hashlib
import logging
from typing import Any, Dict, List, Union, Optional, Pattern
from urllib.parse import quote_plus, urlparse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class InputSanitizer:
    """Enhanced utility class for sanitizing various types of input with comprehensive security measures."""
    
    # Whitelist of allowed characters for different contexts
    ALLOWED_URL_CHARS = re.compile(r'^[a-zA-Z0-9\-._~:/?#[\]@!$&\'()*+,;=%]*$')
    ALLOWED_ALPHANUMERIC = re.compile(r'^[a-zA-Z0-9]*$')
    ALLOWED_IDENTIFIER = re.compile(r'^[a-zA-Z0-9_-]*$')
    ALLOWED_EMAIL = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    ALLOWED_PHONE = re.compile(r'^\+?[1-9]\d{1,14}$')
    
    # Dangerous patterns to detect and block
    DANGEROUS_PATTERNS = [
        re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'vbscript:', re.IGNORECASE),
        re.compile(r'data:text/html', re.IGNORECASE),
        re.compile(r'data:application/javascript', re.IGNORECASE),
        re.compile(r'<iframe[^>]*>.*?</iframe>', re.IGNORECASE | re.DOTALL),
        re.compile(r'<object[^>]*>.*?</object>', re.IGNORECASE | re.DOTALL),
        re.compile(r'<embed[^>]*>.*?</embed>', re.IGNORECASE | re.DOTALL),
        re.compile(r'<link[^>]*>', re.IGNORECASE),
        re.compile(r'<meta[^>]*>', re.IGNORECASE),
        re.compile(r'<style[^>]*>.*?</style>', re.IGNORECASE | re.DOTALL),
        re.compile(r'expression\s*\(', re.IGNORECASE),
        re.compile(r'url\s*\(', re.IGNORECASE),
        re.compile(r'@import', re.IGNORECASE),
        re.compile(r'\.\./', re.IGNORECASE),  # Path traversal
        re.compile(r'\.\.\\', re.IGNORECASE),  # Windows path traversal
        re.compile(r'%2e%2e%2f', re.IGNORECASE),  # URL encoded path traversal
        re.compile(r'%2e%2e%5c', re.IGNORECASE),  # URL encoded Windows path traversal
        re.compile(r'<[^>]*on\w+\s*=', re.IGNORECASE),  # Event handlers
        re.compile(r'<[^>]*style\s*=', re.IGNORECASE),  # Inline styles
        re.compile(r'<[^>]*href\s*=', re.IGNORECASE),  # Links
        re.compile(r'<[^>]*src\s*=', re.IGNORECASE),  # Sources
    ]
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        # Context-aware patterns for common verbs to allow natural language usage
        re.compile(r'(\bSELECT\b.*\bFROM\b)', re.IGNORECASE),
        re.compile(r'(\bINSERT\b.*\bINTO\b)', re.IGNORECASE),
        re.compile(r'(\bUPDATE\b.*\bSET\b)', re.IGNORECASE),
        re.compile(r'(\bDELETE\b.*\bFROM\b)', re.IGNORECASE),
        re.compile(r'(\bCREATE\b\s+(TABLE|INDEX|VIEW|PROCEDURE|FUNCTION|TRIGGER|DATABASE|SCHEMA|USER|ROLE)\b)', re.IGNORECASE),
        re.compile(r'(\bDROP\b\s+(TABLE|INDEX|VIEW|PROCEDURE|FUNCTION|TRIGGER|DATABASE|SCHEMA|USER|ROLE)\b)', re.IGNORECASE),
        re.compile(r'(\bALTER\b\s+(TABLE|INDEX|VIEW|PROCEDURE|FUNCTION|TRIGGER|DATABASE|SCHEMA|USER|ROLE)\b)', re.IGNORECASE),
        re.compile(r'(\b(EXEC|EXECUTE)\b\s+)', re.IGNORECASE),
        re.compile(r'(\b(UNION|OR|AND)\b.*\b(SELECT|INSERT|UPDATE|DELETE)\b)', re.IGNORECASE),
        re.compile(r'(\b(WHERE|HAVING)\b.*\b(OR|AND)\b.*\b(1=1|1=0)\b)', re.IGNORECASE),
        re.compile(r'(\b(INFORMATION_SCHEMA|SYS\.|MYSQL\.|PG_)\b)', re.IGNORECASE),
        re.compile(r'(\b(CHAR|ASCII|SUBSTRING|LENGTH|COUNT|SUM|AVG|MAX|MIN)\s*\()', re.IGNORECASE),
        re.compile(r'(\b(WAITFOR|DELAY|SLEEP|BENCHMARK)\b)', re.IGNORECASE),
        re.compile(r'(\b(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b)', re.IGNORECASE),
        re.compile(r'(\b(SP_|XP_)\b)', re.IGNORECASE),  # Stored procedures
        re.compile(r'(\b(CAST|CONVERT)\s*\()', re.IGNORECASE),
        re.compile(r'(\b(CHARINDEX|PATINDEX|STUFF|REPLACE)\s*\()', re.IGNORECASE),
    ]
    
    # Rate limiting and abuse detection
    _rate_limit_cache: Dict[str, List[datetime]] = {}
    _max_requests_per_minute = 100
    _max_requests_per_hour = 1000
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000, allowed_pattern: re.Pattern = None) -> str:
        """
        Sanitize a string input.
        
        Args:
            value: The string to sanitize
            max_length: Maximum allowed length
            allowed_pattern: Regex pattern for allowed characters
            
        Returns:
            Sanitized string
            
        Raises:
            ValueError: If input is invalid
        """
        if not isinstance(value, str):
            raise ValueError("Input must be a string")
        
        if len(value) > max_length:
            raise ValueError(f"Input exceeds maximum length of {max_length}")
        
        # Apply allowed pattern if provided
        if allowed_pattern and not allowed_pattern.match(value):
            raise ValueError("Input contains disallowed characters")
        
        # HTML escape to prevent XSS
        sanitized = html.escape(value)
        
        return sanitized
    
    @staticmethod
    def sanitize_url(url: str, max_length: int = 2000) -> str:
        """
        Sanitize a URL input.
        
        Args:
            url: The URL to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized URL
            
        Raises:
            ValueError: If URL is invalid
        """
        if not isinstance(url, str):
            raise ValueError("URL must be a string")
        
        if len(url) > max_length:
            raise ValueError(f"URL exceeds maximum length of {max_length}")
        
        # Parse URL to validate structure
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")
        
        # Check for allowed characters
        if not InputSanitizer.ALLOWED_URL_CHARS.match(url):
            raise ValueError("URL contains disallowed characters")
        
        # URL encode special characters
        # Note: This is a simplified approach. In practice, you'd want to be more careful
        # about what parts of the URL to encode
        return url
    
    @staticmethod
    def sanitize_json_payload(payload: Union[str, Dict], max_size: int = 1024 * 1024, max_depth: int = 10) -> Dict:
        """
        Sanitize a JSON payload.
        
        Args:
            payload: The JSON payload to sanitize (string or dict)
            max_size: Maximum allowed size in bytes
            max_depth: Maximum allowed nesting depth
            
        Returns:
            Sanitized JSON as dictionary
            
        Raises:
            ValueError: If payload is invalid
        """
        # Convert string to dict if needed
        if isinstance(payload, str):
            if len(payload) > max_size:
                raise ValueError(f"JSON payload exceeds maximum size of {max_size} bytes")
            
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {str(e)}")
        elif isinstance(payload, dict):
            # Convert to string to check size
            payload_str = json.dumps(payload)
            if len(payload_str) > max_size:
                raise ValueError(f"JSON payload exceeds maximum size of {max_size} bytes")
            data = payload
        else:
            raise ValueError("Payload must be a string or dictionary")
        
        # Check nesting depth
        def check_depth(obj, current_depth=0):
            if current_depth > max_depth:
                raise ValueError(f"JSON payload exceeds maximum nesting depth of {max_depth}")
            
            if isinstance(obj, dict):
                for value in obj.values():
                    check_depth(value, current_depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    check_depth(item, current_depth + 1)
        
        check_depth(data)
        
        # Sanitize string values
        def sanitize_values(obj):
            if isinstance(obj, dict):
                return {key: sanitize_values(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_values(item) for item in obj]
            elif isinstance(obj, str):
                return InputSanitizer.sanitize_string(obj, max_length=10000)  # Larger limit for JSON values
            else:
                return obj
        
        return sanitize_values(data)
    
    @staticmethod
    def sanitize_parameters(params: Dict[str, Any], 
                          allowed_keys: List[str] = None, 
                          required_keys: List[str] = None,
                          type_checks: Dict[str, type] = None) -> Dict[str, Any]:
        """
        Sanitize a dictionary of parameters.
        
        Args:
            params: Dictionary of parameters to sanitize
            allowed_keys: List of allowed parameter keys
            required_keys: List of required parameter keys
            type_checks: Dictionary mapping keys to expected types
            
        Returns:
            Sanitized parameters dictionary
            
        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(params, dict):
            raise ValueError("Parameters must be a dictionary")
        
        # Check required keys
        if required_keys:
            for key in required_keys:
                if key not in params:
                    raise ValueError(f"Missing required parameter: {key}")
        
        # Filter allowed keys
        if allowed_keys:
            filtered_params = {key: value for key, value in params.items() if key in allowed_keys}
        else:
            filtered_params = params.copy()
        
        # Apply type checks
        if type_checks:
            for key, expected_type in type_checks.items():
                if key in filtered_params:
                    value = filtered_params[key]
                    if not isinstance(value, expected_type):
                        raise ValueError(f"Parameter {key} must be of type {expected_type.__name__}")
        
        # Sanitize string values
        sanitized_params = {}
        for key, value in filtered_params.items():
            if isinstance(value, str):
                # For identifier-like strings, use stricter pattern
                if key in ['tenant_id', 'service_name', 'key_type']:
                    sanitized_params[key] = InputSanitizer.sanitize_string(
                        value, max_length=100, allowed_pattern=InputSanitizer.ALLOWED_IDENTIFIER
                    )
                else:
                    sanitized_params[key] = InputSanitizer.sanitize_string(value, max_length=1000)
            else:
                sanitized_params[key] = value
        
        return sanitized_params
    
    @staticmethod
    def encode_for_url(value: str) -> str:
        """
        URL encode a string value.
        
        Args:
            value: The string to encode
            
        Returns:
            URL encoded string
        """
        return quote_plus(value)
    
    @staticmethod
    def prevent_xxe(xml_string: str) -> str:
        """
        Prevent XML External Entity (XXE) attacks.
        
        Args:
            xml_string: The XML string to sanitize
            
        Returns:
            Sanitized XML string
            
        Raises:
            ValueError: If XML contains dangerous elements
        """
        if not isinstance(xml_string, str):
            raise ValueError("XML must be a string")
        
        # Check for common XXE patterns
        xxe_patterns = [
            r'<!ENTITY',
            r'<!DOCTYPE',
            r'&[a-zA-Z]+;',
            r'%[a-zA-Z]+;'
        ]
        
        for pattern in xxe_patterns:
            if re.search(pattern, xml_string, re.IGNORECASE):
                raise ValueError("XML contains potentially dangerous XXE patterns")
        
        return xml_string
    
    @staticmethod
    def detect_dangerous_patterns(value: str) -> List[str]:
        """
        Detect dangerous patterns in input.
        
        Args:
            value: The string to analyze
            
        Returns:
            List of detected dangerous patterns
        """
        if not isinstance(value, str):
            return []
        
        detected_patterns = []
        
        # Check for dangerous patterns
        for pattern in InputSanitizer.DANGEROUS_PATTERNS:
            if pattern.search(value):
                detected_patterns.append(f"Dangerous pattern detected: {pattern.pattern}")
        
        # Check for SQL injection patterns
        for pattern in InputSanitizer.SQL_INJECTION_PATTERNS:
            if pattern.search(value):
                detected_patterns.append(f"SQL injection pattern detected: {pattern.pattern}")
        
        return detected_patterns
    
    @staticmethod
    def sanitize_with_security_checks(value: str, max_length: int = 1000, 
                                    allowed_pattern: Optional[Pattern] = None,
                                    check_dangerous: bool = True,
                                    check_sql_injection: bool = True) -> str:
        """
        Enhanced sanitization with comprehensive security checks.
        
        Args:
            value: The string to sanitize
            max_length: Maximum allowed length
            allowed_pattern: Regex pattern for allowed characters
            check_dangerous: Whether to check for dangerous patterns
            check_sql_injection: Whether to check for SQL injection
            
        Returns:
            Sanitized string
            
        Raises:
            ValueError: If input contains security threats
        """
        if not isinstance(value, str):
            raise ValueError("Input must be a string")
        
        # Length check
        if len(value) > max_length:
            raise ValueError(f"Input exceeds maximum length of {max_length}")
        
        # Security checks
        if check_dangerous:
            dangerous_patterns = InputSanitizer.detect_dangerous_patterns(value)
            if dangerous_patterns:
                logger.warning(f"Security threat detected in input: {dangerous_patterns}")
                raise ValueError(f"Input contains security threats: {', '.join(dangerous_patterns)}")
        
        if check_sql_injection:
            sql_patterns = [p for p in InputSanitizer.SQL_INJECTION_PATTERNS if p.search(value)]
            if sql_patterns:
                logger.warning(f"SQL injection attempt detected: {sql_patterns}")
                raise ValueError("Input contains SQL injection patterns")
        
        # Pattern validation
        if allowed_pattern and not allowed_pattern.match(value):
            raise ValueError("Input contains disallowed characters")
        
        # HTML escape to prevent XSS
        sanitized = html.escape(value)
        
        return sanitized
    
    @staticmethod
    def validate_email(email: str) -> str:
        """
        Validate and sanitize email address.
        
        Args:
            email: Email address to validate
            
        Returns:
            Sanitized email address
            
        Raises:
            ValueError: If email is invalid
        """
        if not isinstance(email, str):
            raise ValueError("Email must be a string")
        
        # Basic length check
        if len(email) > 254:  # RFC 5321 limit
            raise ValueError("Email address too long")
        
        # Pattern validation
        if not InputSanitizer.ALLOWED_EMAIL.match(email):
            raise ValueError("Invalid email format")
        
        # Check for dangerous patterns
        dangerous_patterns = InputSanitizer.detect_dangerous_patterns(email)
        if dangerous_patterns:
            raise ValueError(f"Email contains security threats: {', '.join(dangerous_patterns)}")
        
        return email.lower().strip()
    
    @staticmethod
    def validate_phone(phone: str) -> str:
        """
        Validate and sanitize phone number.
        
        Args:
            phone: Phone number to validate
            
        Returns:
            Sanitized phone number
            
        Raises:
            ValueError: If phone is invalid
        """
        if not isinstance(phone, str):
            raise ValueError("Phone must be a string")
        
        # Remove common formatting characters
        cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)
        
        # Pattern validation
        if not InputSanitizer.ALLOWED_PHONE.match(cleaned):
            raise ValueError("Invalid phone number format")
        
        # Check for dangerous patterns
        dangerous_patterns = InputSanitizer.detect_dangerous_patterns(phone)
        if dangerous_patterns:
            raise ValueError(f"Phone contains security threats: {', '.join(dangerous_patterns)}")
        
        return cleaned
    
    @staticmethod
    def sanitize_file_upload(filename: str, allowed_extensions: List[str] = None,
                           max_filename_length: int = 255) -> str:
        """
        Sanitize file upload filename.
        
        Args:
            filename: Original filename
            allowed_extensions: List of allowed file extensions
            max_filename_length: Maximum filename length
            
        Returns:
            Sanitized filename
            
        Raises:
            ValueError: If filename is invalid
        """
        if not isinstance(filename, str):
            raise ValueError("Filename must be a string")
        
        # Length check
        if len(filename) > max_filename_length:
            raise ValueError(f"Filename too long (max {max_filename_length} characters)")
        
        # Check for path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError("Filename contains path traversal characters")
        
        # Check for dangerous patterns
        dangerous_patterns = InputSanitizer.detect_dangerous_patterns(filename)
        if dangerous_patterns:
            raise ValueError(f"Filename contains security threats: {', '.join(dangerous_patterns)}")
        
        # Extract extension
        if '.' in filename:
            name, ext = filename.rsplit('.', 1)
            ext = ext.lower()
            
            # Check allowed extensions
            if allowed_extensions and ext not in allowed_extensions:
                raise ValueError(f"File extension '{ext}' not allowed")
            
            # Sanitize name and extension
            sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
            sanitized_ext = re.sub(r'[^a-zA-Z0-9]', '', ext)
            
            return f"{sanitized_name}.{sanitized_ext}"
        else:
            # No extension, just sanitize the name
            return re.sub(r'[^a-zA-Z0-9_-]', '_', filename)
    
    @staticmethod
    def check_rate_limit(identifier: str, max_per_minute: int = None, 
                        max_per_hour: int = None) -> bool:
        """
        Check if request is within rate limits.
        
        Args:
            identifier: Unique identifier (IP, user ID, etc.)
            max_per_minute: Maximum requests per minute
            max_per_hour: Maximum requests per hour
            
        Returns:
            True if within limits, False if rate limited
        """
        now = datetime.now(timezone.utc)
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        # Initialize cache for identifier if needed
        if identifier not in InputSanitizer._rate_limit_cache:
            InputSanitizer._rate_limit_cache[identifier] = []
        
        # Clean old entries
        InputSanitizer._rate_limit_cache[identifier] = [
            timestamp for timestamp in InputSanitizer._rate_limit_cache[identifier]
            if timestamp > hour_ago
        ]
        
        # Add current request
        InputSanitizer._rate_limit_cache[identifier].append(now)
        
        # Check limits
        requests_last_minute = len([
            timestamp for timestamp in InputSanitizer._rate_limit_cache[identifier]
            if timestamp > minute_ago
        ])
        
        requests_last_hour = len(InputSanitizer._rate_limit_cache[identifier])
        
        max_per_minute = max_per_minute or InputSanitizer._max_requests_per_minute
        max_per_hour = max_per_hour or InputSanitizer._max_requests_per_hour
        
        if requests_last_minute > max_per_minute:
            logger.warning(f"Rate limit exceeded for {identifier}: {requests_last_minute} requests in last minute")
            return False
        
        if requests_last_hour > max_per_hour:
            logger.warning(f"Rate limit exceeded for {identifier}: {requests_last_hour} requests in last hour")
            return False
        
        return True
    
    @staticmethod
    def generate_input_hash(value: str, salt: str = "") -> str:
        """
        Generate a hash for input to detect duplicates or for caching.
        
        Args:
            value: Input value to hash
            salt: Optional salt for additional security
            
        Returns:
            SHA-256 hash of the input
        """
        if not isinstance(value, str):
            value = str(value)
        
        # Combine value with salt
        combined = f"{value}{salt}"
        
        # Generate hash
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()
    
    @staticmethod
    def sanitize_base64(data: str, max_size: int = 1024 * 1024) -> str:
        """
        Sanitize base64 encoded data.
        
        Args:
            data: Base64 encoded string
            max_size: Maximum allowed size in bytes
            
        Returns:
            Sanitized base64 string
            
        Raises:
            ValueError: If data is invalid
        """
        if not isinstance(data, str):
            raise ValueError("Base64 data must be a string")
        
        # Check length (base64 is ~4/3 the size of original data)
        if len(data) > (max_size * 4 // 3):
            raise ValueError(f"Base64 data too large (max {max_size} bytes)")
        
        # Check for valid base64 characters
        if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', data):
            raise ValueError("Invalid base64 format")
        
        # Check for dangerous patterns in decoded data
        try:
            decoded = base64.b64decode(data)
            decoded_str = decoded.decode('utf-8', errors='ignore')
            dangerous_patterns = InputSanitizer.detect_dangerous_patterns(decoded_str)
            if dangerous_patterns:
                raise ValueError(f"Base64 data contains security threats: {', '.join(dangerous_patterns)}")
        except Exception as e:
            raise ValueError(f"Invalid base64 data: {str(e)}")
        
        return data
    
    @staticmethod
    def sanitize_sql_identifier(identifier: str) -> str:
        """
        Sanitize SQL identifier (table name, column name, etc.).
        
        Args:
            identifier: SQL identifier to sanitize
            
        Returns:
            Sanitized SQL identifier
            
        Raises:
            ValueError: If identifier is invalid
        """
        if not isinstance(identifier, str):
            raise ValueError("SQL identifier must be a string")
        
        # Check length
        if len(identifier) > 128:  # Most databases limit identifier length
            raise ValueError("SQL identifier too long")
        
        # Check for valid characters (alphanumeric and underscore)
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
            raise ValueError("SQL identifier contains invalid characters")
        
        # Check for SQL keywords (basic check)
        sql_keywords = {
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
            'TABLE', 'INDEX', 'VIEW', 'PROCEDURE', 'FUNCTION', 'TRIGGER',
            'WHERE', 'FROM', 'JOIN', 'GROUP', 'ORDER', 'HAVING', 'UNION',
            'AND', 'OR', 'NOT', 'IN', 'EXISTS', 'BETWEEN', 'LIKE', 'IS'
        }
        
        if identifier.upper() in sql_keywords:
            raise ValueError(f"SQL identifier cannot be a reserved keyword: {identifier}")
        
        return identifier
    
    @classmethod
    def get_security_report(cls, value: str) -> Dict[str, Any]:
        """
        Generate a comprehensive security report for input.
        
        Args:
            value: Input to analyze
            
        Returns:
            Dictionary with security analysis results
        """
        if not isinstance(value, str):
            return {
                'valid': False,
                'error': 'Input must be a string',
                'threats': [],
                'recommendations': []
            }
        
        threats = []
        recommendations = []
        
        # Check for dangerous patterns
        dangerous_patterns = cls.detect_dangerous_patterns(value)
        if dangerous_patterns:
            threats.extend(dangerous_patterns)
            recommendations.append("Remove or escape dangerous HTML/JavaScript patterns")
        
        # Check for SQL injection
        sql_patterns = [p for p in cls.SQL_INJECTION_PATTERNS if p.search(value)]
        if sql_patterns:
            threats.append("SQL injection patterns detected")
            recommendations.append("Use parameterized queries instead of string concatenation")
        
        # Check length
        if len(value) > 10000:
            threats.append("Input is unusually long")
            recommendations.append("Consider limiting input length")
        
        # Check for suspicious patterns
        if re.search(r'[<>]', value):
            threats.append("Contains HTML/XML characters")
            recommendations.append("HTML escape the input")
        
        if re.search(r'[;&|`$]', value):
            threats.append("Contains shell metacharacters")
            recommendations.append("Avoid shell command execution with this input")
        
        return {
            'valid': len(threats) == 0,
            'threats': threats,
            'recommendations': recommendations,
            'length': len(value),
            'contains_html': bool(re.search(r'[<>]', value)),
            'contains_sql': bool(sql_patterns),
            'contains_script': bool(re.search(r'<script', value, re.IGNORECASE))
        }