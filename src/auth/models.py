from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime


class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: Optional[int] = None


class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    tenant_id: Optional[int] = None


class UserAuth(BaseModel):
    user_id: str
    email: str
    name: str
    provider: str
    profile_picture_url: Optional[str] = None
    tenant_subdomain: Optional[str] = None


class OAuthToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    id_token: Optional[str] = None


class SessionData(BaseModel):
    session_id: str
    user_id: str
    tenant_id: Optional[int] = None
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True


class MFAChallenge(BaseModel):
    challenge_id: str
    user_id: str
    method: str  # "totp", "sms", "email"
    secret: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    max_attempts: int = 3
    is_verified: bool = False


class PasswordResetRequest(BaseModel):
    email: EmailStr
    redirect_url: Optional[str] = None


class PasswordReset(BaseModel):
    token: str
    new_password: str
    confirm_password: str


class MFAVerification(BaseModel):
    challenge_id: str
    code: str


class SessionCreate(BaseModel):
    user_id: str
    tenant_id: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    expires_in_hours: int = 24


class AuthResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    requires_mfa: bool = False
    mfa_challenge_id: Optional[str] = None