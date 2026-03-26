from datetime import datetime, timedelta
from typing import Optional, Dict
import os
import secrets
from jose import jwt, JWTError
from src.auth.models import TokenData


# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is required and must be provided via environment/Secret Manager")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token with the provided data and expiration."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token with longer expiration."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_token_pair(data: dict, expires_delta: Optional[timedelta] = None) -> Dict[str, str]:
    """Create both access and refresh tokens."""
    access_token = create_access_token(data, expires_delta)
    refresh_token = create_refresh_token(data)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


def decode_access_token(token: str) -> TokenData:
    """Decode and verify a JWT access token, returning the token data."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if this is a refresh token
        if payload.get("type") == "refresh":
            raise ValueError("Invalid token type")

        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        tenant_id: Optional[int] = payload.get("tenant_id")

        if user_id is None or email is None:
            raise ValueError("Invalid token payload")

        token_data = TokenData(user_id=user_id, email=email, tenant_id=tenant_id)
        return token_data
    except JWTError:
        raise ValueError("Invalid token")


def decode_refresh_token(token: str) -> TokenData:
    """Decode and verify a JWT refresh token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if this is actually a refresh token
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        tenant_id: Optional[int] = payload.get("tenant_id")

        if user_id is None or email is None:
            raise ValueError("Invalid token payload")

        token_data = TokenData(user_id=user_id, email=email, tenant_id=tenant_id)
        return token_data
    except JWTError:
        raise ValueError("Invalid refresh token")


def generate_password_reset_token(email: str) -> str:
    """Generate a secure password reset token."""
    data = {
        "email": email,
        "type": "password_reset",
        "nonce": secrets.token_urlsafe(32)
    }
    expire = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiration
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verify a password reset token and return the email."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "password_reset":
            return None

        email = payload.get("email")
        return email
    except JWTError:
        return None


def generate_mfa_token(user_id: str, tenant_id: Optional[int] = None) -> str:
    """Generate a temporary MFA verification token."""
    data = {
        "sub": user_id,
        "type": "mfa_verification",
        "tenant_id": tenant_id,
        "nonce": secrets.token_urlsafe(32)
    }
    expire = datetime.utcnow() + timedelta(minutes=5)  # 5 minutes expiration
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_mfa_token(token: str) -> Optional[TokenData]:
    """Verify an MFA token and return the token data."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "mfa_verification":
            return None

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        if user_id is None:
            return None

        return TokenData(user_id=user_id, tenant_id=tenant_id)
    except JWTError:
        return None