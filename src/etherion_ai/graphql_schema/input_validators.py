# src/etherion_ai/graphql_schema/input_validators.py
"""
Pydantic validation models for GraphQL input types with strict validation rules.
Enhanced with comprehensive security validation and SQL injection protection.
"""

from pydantic import BaseModel, validator, Field, HttpUrl, EmailStr
from typing import Optional, List, Dict, Any
import re
import html
import logging

logger = logging.getLogger(__name__)

# SQL injection patterns to detect - more specific to avoid false positives
SQL_INJECTION_PATTERNS = [
    r"(\bSELECT\s+.*\bFROM\b)",
    r"(\bINSERT\s+INTO\b)",
    r"(\bUPDATE\s+\w+\s+SET\b)",
    r"(\bDELETE\s+FROM\b)",
    r"(\bDROP\s+TABLE\b)",
    r"(\bCREATE\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW)\b)",
    r"(\bALTER\s+TABLE\b)",
    r"(\bEXEC\s+(sp_|xp_|\())",
    r"(\bSCRIPT\s*\()",
    r"(\bUNION\s+SELECT\b)",
    r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
    r"(\b(OR|AND)\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+['\"]?)",
    r"(--|\#|\/\*|\*\/)",
    r"(\bWAITFOR\s+DELAY\b)",
    r"(\bBENCHMARK\s*\()",
    r"(\bSLEEP\s*\()",
    r"(\bPG_SLEEP\s*\()",
    r"(['\"]\s*(OR|AND)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"]?)",
    r"(['\"]\s*;\s*(DROP|DELETE|INSERT|UPDATE|CREATE))",
]

# XSS patterns to detect
XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript:",
    r"vbscript:",
    r"onload\s*=",
    r"onerror\s*=",
    r"onclick\s*=",
    r"onmouseover\s*=",
    r"onfocus\s*=",
    r"onblur\s*=",
    r"onchange\s*=",
    r"onsubmit\s*=",
    r"<iframe[^>]*>",
    r"<object[^>]*>",
    r"<embed[^>]*>",
    r"<link[^>]*>",
    r"<meta[^>]*>",
    r"<style[^>]*>",
    r"expression\s*\(",
    r"url\s*\(",
    r"@import",
]

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",
    r"\.\.\\",
    r"%2e%2e%2f",
    r"%2e%2e%5c",
    r"\.\.%2f",
    r"\.\.%5c",
    r"\.\.%252f",
    r"\.\.%255c",
]

def detect_sql_injection(text: str) -> bool:
    """Detect potential SQL injection attempts."""
    if not text:
        return False
    
    text_upper = text.upper()
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, text_upper, re.IGNORECASE):
            logger.warning(f"Potential SQL injection detected: {pattern} in text: {text[:100]}")
            return True
    return False

def detect_xss(text: str) -> bool:
    """Detect potential XSS attempts."""
    if not text:
        return False
    
    for pattern in XSS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"Potential XSS detected: {pattern} in text: {text[:100]}")
            return True
    return False

def detect_path_traversal(text: str) -> bool:
    """Detect potential path traversal attempts."""
    if not text:
        return False
    
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"Potential path traversal detected: {pattern} in text: {text[:100]}")
            return True
    return False

def sanitize_text(text: str) -> str:
    """Sanitize text by removing potentially harmful content."""
    if not text:
        return text
    
    # HTML escape
    text = html.escape(text)
    
    # Remove script tags
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove other potentially harmful tags
    text = re.sub(r'<[^>]*>', '', text)
    
    return text

def validate_security(text: str, field_name: str) -> None:
    """Validate text for security threats."""
    if not text:
        return
    
    if detect_sql_injection(text):
        raise ValueError(f"Potential SQL injection detected in {field_name}")
    
    if detect_xss(text):
        raise ValueError(f"Potential XSS detected in {field_name}")
    
    if detect_path_traversal(text):
        raise ValueError(f"Potential path traversal detected in {field_name}")


class GoalInputValidator(BaseModel):
    """
    Pydantic validation model for GoalInput.
    """
    goal: str = Field(
        ..., 
        min_length=1, 
        max_length=2000,
        description="The primary, high-level objective for the agentic system."
    )
    
    context: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Optional detailed context for the goal."
    )
    
    output_format_instructions: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional instructions on how the final output should be structured."
    )
    
    user_id: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="The unique identifier for the user making the request."
    )
    
    provider: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional logical provider key (e.g. 'openai', 'vertex', 'azure_openai').",
    )
    model: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional logical model key within the provider (e.g. 'gpt-4.1').",
    )
    
    @validator('goal')
    def validate_goal_content(cls, v):
        """Validate that goal content doesn't contain potentially harmful content."""
        validate_security(v, 'goal')
        return sanitize_text(v)
    
    @validator('context')
    def validate_context_content(cls, v):
        """Validate that context content doesn't contain potentially harmful content."""
        if v:
            validate_security(v, 'context')
            return sanitize_text(v)
        return v


class FeedbackInputValidator(BaseModel):
    """
    Pydantic validation model for FeedbackInput.
    """
    job_id: str = Field(..., min_length=1, max_length=100)
    user_id: str = Field(..., min_length=1, max_length=100)
    goal: str = Field(..., min_length=1, max_length=2000)
    final_output: str = Field(..., min_length=1, max_length=10000)
    feedback_score: int = Field(..., ge=1, le=5)  # Rating from 1-5
    feedback_comment: str = Field(..., min_length=1, max_length=1000)
    
    @validator('feedback_comment')
    def validate_feedback_comment(cls, v):
        """Validate that feedback comment doesn't contain potentially harmful content."""
        validate_security(v, 'feedback_comment')
        return sanitize_text(v)


class SupportTicketInputValidator(BaseModel):
    """
    Pydantic validation model for SupportTicketInput.
    """
    ticket_text: str = Field(
        ..., 
        min_length=10, 
        max_length=5000,
        description="The text content of the customer support ticket."
    )
    
    user_id: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="The unique identifier for the user submitting the ticket."
    )
    
    order_id: Optional[str] = Field(
        default=None,
        max_length=50,
        description="The order ID related to the support ticket, if applicable."
    )
    
    attached_files: Optional[List[str]] = Field(
        default=None,
        max_items=10,
        description="List of file URLs or identifiers attached to the ticket."
    )
    
    @validator('ticket_text')
    def validate_ticket_text(cls, v):
        """Validate that ticket text doesn't contain potentially harmful content."""
        validate_security(v, 'ticket_text')
        return sanitize_text(v)
    
    @validator('attached_files')
    def validate_attached_files(cls, v):
        """Validate that attached file URLs are valid and secure."""
        if v:
            for url in v:
                validate_security(url, 'attached_file_url')
                if not re.match(r'^https?://', url):
                    raise ValueError(f'Invalid URL in attached files: {url}')
        return v


class TenantInputValidator(BaseModel):
    """
    Pydantic validation model for TenantInput.
    """
    name: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="The display name for the tenant."
    )
    
    admin_email: str = Field(
        ..., 
        max_length=255,
        description="The email address of the tenant administrator."
    )
    
    password: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="Optional password for the tenant administrator account."
    )
    
    subdomain: Optional[str] = Field(
        default=None,
        description="Optional desired subdomain for the tenant."
    )
    
    @validator('admin_email')
    def validate_email(cls, v):
        """Validate that email is in a valid format."""
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError('Invalid email format')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        """Validate that password meets security requirements when provided."""
        if v is None:
            return v
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v
    
    @validator('name')
    def validate_name_content(cls, v):
        """Validate that name doesn't contain potentially harmful content."""
        validate_security(v, 'tenant_name')
        return sanitize_text(v)

    @validator('subdomain')
    def validate_subdomain(cls, v):
        if not v:
            return v
        s = v.strip().lower()
        # Must be 3-63 chars, lowercase letters, digits, hyphens. Start/end with alnum.
        if not re.match(r'^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$', s):
            raise ValueError('Invalid subdomain format')
        # Disallow reserved words
        reserved = { 'default', 'www', 'api', 'admin' }
        if s in reserved:
            raise ValueError('Subdomain is reserved')
        return s


class ProjectInputValidator(BaseModel):
    """
    Pydantic validation model for ProjectInput.
    """
    name: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="The name of the project."
    )
    
    description: str = Field(
        default="", 
        max_length=1000,
        description="The description of the project."
    )
    
    @validator('name')
    def validate_name_content(cls, v):
        """Validate that name doesn't contain potentially harmful content."""
        validate_security(v, 'project_name')
        return sanitize_text(v)
    
    @validator('description')
    def validate_description_content(cls, v):
        """Validate that description doesn't contain potentially harmful content."""
        if v:
            validate_security(v, 'project_description')
            return sanitize_text(v)
        return v


class ConversationInputValidator(BaseModel):
    """
    Pydantic validation model for ConversationInput.
    """
    title: str = Field(
        ..., 
        min_length=1, 
        max_length=200,
        description="The title of the conversation."
    )
    
    project_id: int = Field(
        ..., 
        gt=0,
        description="The ID of the project this conversation belongs to."
    )
    
    @validator('title')
    def validate_title_content(cls, v):
        """Validate that title doesn't contain potentially harmful content."""
        validate_security(v, 'conversation_title')
        return sanitize_text(v)