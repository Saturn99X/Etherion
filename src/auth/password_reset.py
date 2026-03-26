"""
Password reset functionality for user authentication.
Handles password reset requests and token validation.
"""

import logging
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json
import hashlib
import os
from hashlib import pbkdf2_hmac

from src.auth.models import PasswordResetRequest, PasswordReset
from src.database.db import get_session
from src.database.models import User
from src.core.redis import get_redis_client
from src.auth.jwt import generate_password_reset_token, verify_password_reset_token

logger = logging.getLogger(__name__)


@dataclass
class PasswordResetInfo:
    """Password reset information."""
    token: str
    email: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    used: bool = False
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class PasswordResetManager:
    """Manages password reset functionality."""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.reset_prefix = "password_reset:"
        self.token_expiry_hours = 1
        self.max_attempts_per_hour = 3
    
    async def _get_redis(self):
        """Get Redis client, initializing if needed."""
        if self.redis_client is None:
            self.redis_client = await get_redis_client()
        return self.redis_client
    
    def _hash_password(self, password: str) -> str:
        """Hash a password with PBKDF2-HMAC-SHA256 and random salt.
        Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
        """
        iterations = 100_000
        salt = os.urandom(16)
        dk = pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"
    
    async def request_password_reset(self, email: str, ip_address: Optional[str] = None, 
                                   user_agent: Optional[str] = None) -> Dict[str, Any]:
        """Request a password reset for a user."""
        redis = await self._get_redis()
        
        # Check rate limiting
        rate_limit_key = f"password_reset_rate:{ip_address or 'unknown'}"
        attempts = await redis.get(rate_limit_key)
        if attempts and int(attempts) >= self.max_attempts_per_hour:
            return {
                "success": False,
                "error": "Too many password reset attempts. Please try again later."
            }
        
        # Find user by email
        with get_session() as session:
            user = session.query(User).filter(User.email == email).first()
            if not user:
                # Don't reveal if email exists or not
                return {
                    "success": True,
                    "message": "If the email exists, a password reset link has been sent."
                }
        
        # Generate reset token
        reset_token = generate_password_reset_token(email)
        
        # Store reset info
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=self.token_expiry_hours)
        
        reset_info = PasswordResetInfo(
            token=reset_token,
            email=email,
            user_id=user.user_id,
            created_at=now,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Store in Redis
        reset_key = f"{self.reset_prefix}{reset_token}"
        reset_data_dict = reset_info.__dict__.copy()
        
        # Convert datetime objects to ISO strings
        for key, value in reset_data_dict.items():
            if isinstance(value, datetime):
                reset_data_dict[key] = value.isoformat()
        
        await redis.setex(
            reset_key,
            self.token_expiry_hours * 3600,  # Convert hours to seconds
            json.dumps(reset_data_dict)
        )
        
        # Update rate limiting
        await redis.incr(rate_limit_key)
        await redis.expire(rate_limit_key, 3600)  # 1 hour
        
        # In a real implementation, you would send an email here
        # For now, we'll just log the reset link
        reset_link = f"https://your-app.com/reset-password?token={reset_token}"
        logger.info(f"Password reset requested for {email}. Reset link: {reset_link}")
        
        return {
            "success": True,
            "message": "If the email exists, a password reset link has been sent.",
            "reset_token": reset_token,  # Only for development/testing
            "reset_link": reset_link     # Only for development/testing
        }
    
    async def verify_reset_token(self, token: str) -> Optional[PasswordResetInfo]:
        """Verify a password reset token."""
        redis = await self._get_redis()
        
        # First verify the JWT token
        email = verify_password_reset_token(token)
        if not email:
            return None
        
        # Get reset info from Redis
        reset_key = f"{self.reset_prefix}{token}"
        reset_data = await redis.get(reset_key)
        
        if not reset_data:
            return None
        
        try:
            reset_dict = json.loads(reset_data)
            
            # Convert ISO strings back to datetime objects
            for key, value in reset_dict.items():
                if key in ['created_at', 'expires_at'] and isinstance(value, str):
                    reset_dict[key] = datetime.fromisoformat(value)
            
            reset_info = PasswordResetInfo(**reset_dict)
            
            # Check if token is expired
            if datetime.utcnow() > reset_info.expires_at:
                await redis.delete(reset_key)
                return None
            
            # Check if token has been used
            if reset_info.used:
                return None
            
            return reset_info
            
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse password reset data: {e}")
            await redis.delete(reset_key)
            return None
    
    async def reset_password(self, token: str, new_password: str) -> Dict[str, Any]:
        """Reset a user's password using a valid token."""
        redis = await self._get_redis()
        
        # Verify token
        reset_info = await self.verify_reset_token(token)
        if not reset_info:
            return {
                "success": False,
                "error": "Invalid or expired password reset token."
            }
        
        # Validate password strength (basic validation)
        if len(new_password) < 8:
            return {
                "success": False,
                "error": "Password must be at least 8 characters long."
            }
        
        # Update user password in database
        with get_session() as session:
            user = session.query(User).filter(User.user_id == reset_info.user_id).first()
            if not user:
                return {
                    "success": False,
                    "error": "User not found."
                }
            
            # Hash the new password
            hashed_password = self._hash_password(new_password)
            user.password_hash = hashed_password
            user.updated_at = datetime.utcnow()
            
            session.commit()
        
        # Mark token as used
        reset_key = f"{self.reset_prefix}{token}"
        reset_info.used = True
        
        reset_data_dict = reset_info.__dict__.copy()
        for key, value in reset_data_dict.items():
            if isinstance(value, datetime):
                reset_data_dict[key] = value.isoformat()
        
        await redis.setex(
            reset_key,
            self.token_expiry_hours * 3600,
            json.dumps(reset_data_dict)
        )
        
        logger.info(f"Password reset completed for user {reset_info.user_id}")
        
        return {
            "success": True,
            "message": "Password has been reset successfully."
        }
    
    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired password reset tokens."""
        redis = await self._get_redis()
        
        reset_keys = await redis.keys(f"{self.reset_prefix}*")
        deleted_count = 0
        
        for reset_key in reset_keys:
            reset_data = await redis.get(reset_key)
            if reset_data:
                try:
                    reset_dict = json.loads(reset_data)
                    expires_at = datetime.fromisoformat(reset_dict['expires_at'])
                    
                    if datetime.utcnow() > expires_at:
                        await redis.delete(reset_key)
                        deleted_count += 1
                        
                except (json.JSONDecodeError, KeyError, ValueError):
                    # Delete malformed tokens
                    await redis.delete(reset_key)
                    deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} expired password reset tokens")
        return deleted_count
    
    async def invalidate_user_reset_tokens(self, user_id: str) -> int:
        """Invalidate all password reset tokens for a user."""
        redis = await self._get_redis()
        
        reset_keys = await redis.keys(f"{self.reset_prefix}*")
        invalidated_count = 0
        
        for reset_key in reset_keys:
            reset_data = await redis.get(reset_key)
            if reset_data:
                try:
                    reset_dict = json.loads(reset_data)
                    if reset_dict.get('user_id') == user_id:
                        await redis.delete(reset_key)
                        invalidated_count += 1
                        
                except (json.JSONDecodeError, KeyError):
                    # Delete malformed tokens
                    await redis.delete(reset_key)
                    invalidated_count += 1
        
        logger.info(f"Invalidated {invalidated_count} password reset tokens for user {user_id}")
        return invalidated_count


# Global password reset manager instance
_password_reset_manager: Optional[PasswordResetManager] = None


async def get_password_reset_manager() -> PasswordResetManager:
    """Get the global password reset manager instance."""
    global _password_reset_manager
    if _password_reset_manager is None:
        _password_reset_manager = PasswordResetManager()
    return _password_reset_manager
