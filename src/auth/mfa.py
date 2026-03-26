"""
Multi-Factor Authentication (MFA) implementation.
Supports TOTP, SMS, and email-based MFA.
"""

import secrets
import logging
import pyotp
import qrcode
import io
import base64
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json

from src.auth.models import MFAChallenge, MFAVerification
from src.database.db import get_session
from src.database.models import User
from src.core.redis import get_redis_client
from src.auth.jwt import generate_mfa_token, verify_mfa_token

logger = logging.getLogger(__name__)


@dataclass
class MFAConfig:
    """MFA configuration for a user."""
    user_id: str
    totp_secret: Optional[str] = None
    sms_enabled: bool = False
    email_enabled: bool = False
    backup_codes: list = None
    is_enabled: bool = False
    
    def __post_init__(self):
        if self.backup_codes is None:
            self.backup_codes = []


class MFAManager:
    """Manages Multi-Factor Authentication for users."""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.mfa_prefix = "mfa:"
        self.challenge_prefix = "mfa_challenge:"
        self.challenge_expiry_minutes = 5
        self.max_attempts = 3
    
    async def _get_redis(self):
        """Get Redis client, initializing if needed."""
        if self.redis_client is None:
            self.redis_client = await get_redis_client()
        return self.redis_client
    
    def _generate_totp_secret(self) -> str:
        """Generate a TOTP secret."""
        return pyotp.random_base32()
    
    def _generate_backup_codes(self, count: int = 10) -> list:
        """Generate backup codes for MFA."""
        return [secrets.token_urlsafe(8) for _ in range(count)]
    
    def _generate_challenge_id(self) -> str:
        """Generate a challenge ID."""
        return secrets.token_urlsafe(32)
    
    async def setup_totp(self, user_id: str) -> Dict[str, Any]:
        """Set up TOTP for a user."""
        redis = await self._get_redis()
        
        # Generate TOTP secret
        totp_secret = self._generate_totp_secret()
        totp = pyotp.TOTP(totp_secret)
        
        # Get user info
        with get_session() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                raise ValueError(f"User not found: {user_id}")
            
            # Create provisioning URI
            provisioning_uri = totp.provisioning_uri(
                name=user.email,
                issuer_name="Etherion AI"
            )
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_data = base64.b64encode(buffer.getvalue()).decode()
        
        # Store TOTP secret temporarily (will be confirmed after verification)
        temp_key = f"{self.mfa_prefix}temp_totp:{user_id}"
        await redis.setex(temp_key, 600, totp_secret)  # 10 minutes
        
        return {
            "secret": totp_secret,
            "provisioning_uri": provisioning_uri,
            "qr_code": f"data:image/png;base64,{qr_code_data}",
            "backup_codes": self._generate_backup_codes()
        }
    
    async def verify_totp_setup(self, user_id: str, code: str) -> bool:
        """Verify TOTP setup with a test code."""
        redis = await self._get_redis()
        
        # Get temporary secret
        temp_key = f"{self.mfa_prefix}temp_totp:{user_id}"
        totp_secret = await redis.get(temp_key)
        
        if not totp_secret:
            return False
        
        # Verify code
        totp = pyotp.TOTP(totp_secret)
        if totp.verify(code, valid_window=1):
            # Store permanent secret
            mfa_key = f"{self.mfa_prefix}config:{user_id}"
            config = MFAConfig(
                user_id=user_id,
                totp_secret=totp_secret,
                is_enabled=True
            )
            
            config_dict = asdict(config)
            await redis.set(mfa_key, json.dumps(config_dict))
            
            # Clean up temporary secret
            await redis.delete(temp_key)
            
            logger.info(f"TOTP setup verified for user {user_id}")
            return True
        
        return False
    
    async def get_mfa_config(self, user_id: str) -> Optional[MFAConfig]:
        """Get MFA configuration for a user."""
        redis = await self._get_redis()
        
        mfa_key = f"{self.mfa_prefix}config:{user_id}"
        config_data = await redis.get(mfa_key)
        
        if not config_data:
            return None
        
        try:
            config_dict = json.loads(config_data)
            return MFAConfig(**config_dict)
        except (json.JSONDecodeError, TypeError):
            return None
    
    async def create_challenge(self, user_id: str, method: str = "totp") -> MFAChallenge:
        """Create an MFA challenge for a user."""
        redis = await self._get_redis()
        
        # Get user's MFA config
        config = await self.get_mfa_config(user_id)
        if not config or not config.is_enabled:
            raise ValueError("MFA not enabled for user")
        
        challenge_id = self._generate_challenge_id()
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.challenge_expiry_minutes)
        
        challenge = MFAChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            method=method,
            secret=config.totp_secret if method == "totp" else None,
            created_at=now,
            expires_at=expires_at,
            attempts=0,
            max_attempts=self.max_attempts,
            is_verified=False
        )
        
        # Store challenge
        challenge_key = f"{self.challenge_prefix}{challenge_id}"
        challenge_dict = challenge.model_dump()
        
        # Convert datetime objects to ISO strings
        for key, value in challenge_dict.items():
            if isinstance(value, datetime):
                challenge_dict[key] = value.isoformat()
        
        await redis.setex(
            challenge_key,
            self.challenge_expiry_minutes * 60,
            json.dumps(challenge_dict)
        )
        
        logger.info(f"Created MFA challenge {challenge_id} for user {user_id}")
        return challenge
    
    async def verify_challenge(self, challenge_id: str, code: str) -> bool:
        """Verify an MFA challenge."""
        redis = await self._get_redis()
        
        challenge_key = f"{self.challenge_prefix}{challenge_id}"
        challenge_data = await redis.get(challenge_key)
        
        if not challenge_data:
            return False
        
        try:
            challenge_dict = json.loads(challenge_data)
            
            # Convert ISO strings back to datetime objects
            for key, value in challenge_dict.items():
                if key in ['created_at', 'expires_at'] and isinstance(value, str):
                    challenge_dict[key] = datetime.fromisoformat(value)
            
            challenge = MFAChallenge(**challenge_dict)
            
            # Check if challenge is expired
            if datetime.utcnow() > challenge.expires_at:
                await redis.delete(challenge_key)
                return False
            
            # Check if max attempts exceeded
            if challenge.attempts >= challenge.max_attempts:
                await redis.delete(challenge_key)
                return False
            
            # Verify code based on method
            is_valid = False
            
            if challenge.method == "totp" and challenge.secret:
                totp = pyotp.TOTP(challenge.secret)
                is_valid = totp.verify(code, valid_window=1)
            elif challenge.method == "backup_code":
                # Verify against backup codes
                config = await self.get_mfa_config(challenge.user_id)
                if config and code in config.backup_codes:
                    is_valid = True
                    # Remove used backup code
                    config.backup_codes.remove(code)
                    await self._save_mfa_config(config)
            
            # Update challenge
            challenge.attempts += 1
            if is_valid:
                challenge.is_verified = True
            
            # Save updated challenge
            challenge_dict = challenge.model_dump()
            for key, value in challenge_dict.items():
                if isinstance(value, datetime):
                    challenge_dict[key] = value.isoformat()
            
            await redis.setex(
                challenge_key,
                self.challenge_expiry_minutes * 60,
                json.dumps(challenge_dict)
            )
            
            if is_valid:
                logger.info(f"MFA challenge {challenge_id} verified successfully")
            else:
                logger.warning(f"MFA challenge {challenge_id} verification failed")
            
            return is_valid
            
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"Failed to verify MFA challenge {challenge_id}: {e}")
            return False
    
    async def get_challenge(self, challenge_id: str) -> Optional[MFAChallenge]:
        """Get an MFA challenge by ID."""
        redis = await self._get_redis()
        
        challenge_key = f"{self.challenge_prefix}{challenge_id}"
        challenge_data = await redis.get(challenge_key)
        
        if not challenge_data:
            return None
        
        try:
            challenge_dict = json.loads(challenge_data)
            
            # Convert ISO strings back to datetime objects
            for key, value in challenge_dict.items():
                if key in ['created_at', 'expires_at'] and isinstance(value, str):
                    challenge_dict[key] = datetime.fromisoformat(value)
            
            return MFAChallenge(**challenge_dict)
            
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    
    async def disable_mfa(self, user_id: str) -> bool:
        """Disable MFA for a user."""
        redis = await self._get_redis()
        
        mfa_key = f"{self.mfa_prefix}config:{user_id}"
        config = await self.get_mfa_config(user_id)
        
        if not config:
            return False
        
        config.is_enabled = False
        config.totp_secret = None
        config.backup_codes = []
        
        await self._save_mfa_config(config)
        
        logger.info(f"MFA disabled for user {user_id}")
        return True
    
    async def _save_mfa_config(self, config: MFAConfig) -> None:
        """Save MFA configuration to Redis."""
        redis = await self._get_redis()
        
        mfa_key = f"{self.mfa_prefix}config:{config.user_id}"
        config_dict = asdict(config)
        await redis.set(mfa_key, json.dumps(config_dict))
    
    async def generate_backup_codes(self, user_id: str) -> list:
        """Generate new backup codes for a user."""
        config = await self.get_mfa_config(user_id)
        if not config:
            raise ValueError("MFA not configured for user")
        
        config.backup_codes = self._generate_backup_codes()
        await self._save_mfa_config(config)
        
        logger.info(f"Generated new backup codes for user {user_id}")
        return config.backup_codes
    
    async def cleanup_expired_challenges(self) -> int:
        """Clean up expired MFA challenges."""
        redis = await self._get_redis()
        
        challenge_keys = await redis.keys(f"{self.challenge_prefix}*")
        deleted_count = 0
        
        for challenge_key in challenge_keys:
            challenge_data = await redis.get(challenge_key)
            if challenge_data:
                try:
                    challenge_dict = json.loads(challenge_data)
                    expires_at = datetime.fromisoformat(challenge_dict['expires_at'])
                    
                    if datetime.utcnow() > expires_at:
                        await redis.delete(challenge_key)
                        deleted_count += 1
                        
                except (json.JSONDecodeError, KeyError, ValueError):
                    # Delete malformed challenges
                    await redis.delete(challenge_key)
                    deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} expired MFA challenges")
        return deleted_count


# Global MFA manager instance
_mfa_manager: Optional[MFAManager] = None


async def get_mfa_manager() -> MFAManager:
    """Get the global MFA manager instance."""
    global _mfa_manager
    if _mfa_manager is None:
        _mfa_manager = MFAManager()
    return _mfa_manager
