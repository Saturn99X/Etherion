"""
Session management for user authentication.
Handles session creation, validation, and cleanup.
"""

import secrets
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json

from src.auth.models import SessionData, SessionCreate
from src.database.db import get_session
from src.database.models import User, Tenant
from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Session information for internal use."""
    session_id: str
    user_id: str
    tenant_id: Optional[int]
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    ip_address: Optional[str]
    user_agent: Optional[str]
    is_active: bool


class SessionManager:
    """Manages user sessions with Redis storage."""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.session_prefix = "session:"
        self.user_sessions_prefix = "user_sessions:"
        self.default_expiry_hours = 24
        self.max_sessions_per_user = 5
    
    async def _get_redis(self):
        """Get Redis client, initializing if needed."""
        if self.redis_client is None:
            self.redis_client = await get_redis_client()
        return self.redis_client
    
    def _generate_session_id(self) -> str:
        """Generate a secure session ID."""
        return secrets.token_urlsafe(32)
    
    async def create_session(self, session_data: SessionCreate) -> SessionInfo:
        """Create a new user session."""
        redis = await self._get_redis()
        
        # Verify user exists
        with get_session() as db_session:
            user = db_session.query(User).filter(User.user_id == session_data.user_id).first()
            if not user:
                raise ValueError(f"User not found: {session_data.user_id}")
            
            # Verify tenant if provided
            if session_data.tenant_id:
                tenant = db_session.query(Tenant).filter(Tenant.id == session_data.tenant_id).first()
                if not tenant:
                    raise ValueError(f"Tenant not found: {session_data.tenant_id}")
        
        # Generate session ID
        session_id = self._generate_session_id()
        
        # Calculate expiry
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=session_data.expires_in_hours)
        
        # Create session info
        session_info = SessionInfo(
            session_id=session_id,
            user_id=session_data.user_id,
            tenant_id=session_data.tenant_id,
            created_at=now,
            last_accessed=now,
            expires_at=expires_at,
            ip_address=session_data.ip_address,
            user_agent=session_data.user_agent,
            is_active=True
        )
        
        # Store in Redis
        session_key = f"{self.session_prefix}{session_id}"
        session_data_dict = session_info.__dict__.copy()
        
        # Convert datetime objects to ISO strings for JSON serialization
        for key, value in session_data_dict.items():
            if isinstance(value, datetime):
                session_data_dict[key] = value.isoformat()
        
        # Store session with expiry
        await redis.setex(
            session_key,
            session_data.expires_in_hours * 3600,  # Convert hours to seconds
            json.dumps(session_data_dict)
        )
        
        # Add to user's session list
        user_sessions_key = f"{self.user_sessions_prefix}{session_data.user_id}"
        await redis.sadd(user_sessions_key, session_id)
        await redis.expire(user_sessions_key, session_data.expires_in_hours * 3600)
        
        # Clean up old sessions if user has too many
        await self._cleanup_user_sessions(session_data.user_id)
        
        logger.info(f"Created session {session_id} for user {session_data.user_id}")
        return session_info
    
    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session information by session ID."""
        redis = await self._get_redis()
        
        session_key = f"{self.session_prefix}{session_id}"
        session_data = await redis.get(session_key)
        
        if not session_data:
            return None
        
        try:
            session_dict = json.loads(session_data)
            
            # Convert ISO strings back to datetime objects
            for key, value in session_dict.items():
                if key in ['created_at', 'last_accessed', 'expires_at'] and isinstance(value, str):
                    session_dict[key] = datetime.fromisoformat(value)
            
            session_info = SessionInfo(**session_dict)
            
            # Check if session is expired
            if datetime.utcnow() > session_info.expires_at:
                await self.delete_session(session_id)
                return None
            
            return session_info
            
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse session data for {session_id}: {e}")
            await self.delete_session(session_id)
            return None
    
    async def update_session_access(self, session_id: str) -> bool:
        """Update the last accessed time for a session."""
        redis = await self._get_redis()
        
        session_info = await self.get_session(session_id)
        if not session_info:
            return False
        
        # Update last accessed time
        session_info.last_accessed = datetime.utcnow()
        
        # Store updated session
        session_key = f"{self.session_prefix}{session_id}"
        session_data_dict = asdict(session_info)
        
        # Convert datetime objects to ISO strings
        for key, value in session_data_dict.items():
            if isinstance(value, datetime):
                session_data_dict[key] = value.isoformat()
        
        # Update with same expiry
        ttl = await redis.ttl(session_key)
        if ttl > 0:
            await redis.setex(session_key, ttl, json.dumps(session_data_dict))
        
        return True
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        redis = await self._get_redis()
        
        # Get session info to find user_id
        session_info = await self.get_session(session_id)
        if session_info:
            # Remove from user's session list
            user_sessions_key = f"{self.user_sessions_prefix}{session_info.user_id}"
            await redis.srem(user_sessions_key, session_id)
        
        # Delete session
        session_key = f"{self.session_prefix}{session_id}"
        deleted = await redis.delete(session_key)
        
        if deleted:
            logger.info(f"Deleted session {session_id}")
        
        return bool(deleted)
    
    async def delete_user_sessions(self, user_id: str) -> int:
        """Delete all sessions for a user."""
        redis = await self._get_redis()
        
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        session_ids = await redis.smembers(user_sessions_key)
        
        deleted_count = 0
        for session_id in session_ids:
            if await self.delete_session(session_id):
                deleted_count += 1
        
        # Clean up user sessions set
        await redis.delete(user_sessions_key)
        
        logger.info(f"Deleted {deleted_count} sessions for user {user_id}")
        return deleted_count
    
    async def _cleanup_user_sessions(self, user_id: str) -> None:
        """Clean up old sessions if user has too many."""
        redis = await self._get_redis()
        
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        session_ids = await redis.smembers(user_sessions_key)
        
        if len(session_ids) <= self.max_sessions_per_user:
            return
        
        # Get session info for all sessions
        sessions = []
        for session_id in session_ids:
            session_info = await self.get_session(session_id)
            if session_info:
                sessions.append(session_info)
        
        # Sort by last accessed (oldest first)
        sessions.sort(key=lambda s: s.last_accessed)
        
        # Delete oldest sessions
        sessions_to_delete = sessions[:-self.max_sessions_per_user]
        for session in sessions_to_delete:
            await self.delete_session(session.session_id)
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        redis = await self._get_redis()
        
        # Get all session keys
        session_keys = await redis.keys(f"{self.session_prefix}*")
        
        deleted_count = 0
        for session_key in session_keys:
            session_data = await redis.get(session_key)
            if session_data:
                try:
                    session_dict = json.loads(session_data)
                    expires_at = datetime.fromisoformat(session_dict['expires_at'])
                    
                    if datetime.utcnow() > expires_at:
                        session_id = session_key.replace(self.session_prefix, "")
                        if await self.delete_session(session_id):
                            deleted_count += 1
                            
                except (json.JSONDecodeError, KeyError, ValueError):
                    # Delete malformed sessions
                    session_id = session_key.replace(self.session_prefix, "")
                    if await self.delete_session(session_id):
                        deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} expired sessions")
        return deleted_count
    
    async def get_user_sessions(self, user_id: str) -> List[SessionInfo]:
        """Get all active sessions for a user."""
        redis = await self._get_redis()
        
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        session_ids = await redis.smembers(user_sessions_key)
        
        sessions = []
        for session_id in session_ids:
            session_info = await self.get_session(session_id)
            if session_info and session_info.is_active:
                sessions.append(session_info)
        
        return sessions
    
    async def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session (mark as inactive)."""
        session_info = await self.get_session(session_id)
        if not session_info:
            return False
        
        session_info.is_active = False
        
        # Update session in Redis
        redis = await self._get_redis()
        session_key = f"{self.session_prefix}{session_id}"
        session_data_dict = session_info.__dict__.copy()
        
        # Convert datetime objects to ISO strings
        for key, value in session_data_dict.items():
            if isinstance(value, datetime):
                session_data_dict[key] = value.isoformat()
        
        ttl = await redis.ttl(session_key)
        if ttl > 0:
            await redis.setex(session_key, ttl, json.dumps(session_data_dict))
        
        logger.info(f"Invalidated session {session_id}")
        return True


# Global session manager instance
_session_manager: Optional[SessionManager] = None


async def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
