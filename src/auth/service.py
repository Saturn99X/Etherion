from datetime import datetime, timedelta
import os
from typing import Optional, Dict, Any
import secrets
import hashlib
import base64
import hmac
import asyncio
from sqlmodel import Session, select
from sqlalchemy import text as sql_text
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.database.models import User, Tenant, TenantInvite, IPAddressUsage
from src.database.db import get_session
from src.auth.models import UserAuth, TokenData
from src.auth.jwt import create_access_token, decode_access_token
from src.auth.oauth import (
    exchange_google_code_for_token, get_google_user_info,
    exchange_github_code_for_token, get_github_user_info,
    exchange_microsoft_code_for_token, get_microsoft_user_info,
    exchange_slack_code_for_token, get_slack_user_info,
)
from src.utils.secrets_manager import TenantSecretsManager

# IP/VPN enforcement utilities
from src.utils.ip_utils import hash_ip
from src.utils.vpn_check import is_vpn_or_proxy


def _is_postgres_session(session: Session) -> bool:
    try:
        bind = session.get_bind()
        if not bind:
            return False
        return (getattr(bind.dialect, "name", "") or "").lower() in {"postgresql", "postgres"}
    except Exception:
        return False


class SubdomainChecker:
    """Helper to check subdomain existence via DB with RLS support."""
    def __init__(self, session: Session):
        self.session = session
    
    def __contains__(self, subdomain: str) -> bool:
        # Reset tenant_id to ensure we are in "onboarding" mode
        # Use set_config to explicitly set to NULL (RESET might default to empty string)
        if _is_postgres_session(self.session):
            self.session.exec(sql_text("SELECT set_config('app.tenant_id', NULL, false)"))
        
        # Set requested subdomain to allow SELECT via RLS
        # Simple sanitization (subdomain is already validated alphanumeric)
        safe_sub = subdomain.replace("'", "")
        if _is_postgres_session(self.session):
            self.session.exec(sql_text(f"SET app.requested_subdomain = '{safe_sub}'"))
        
        existing = self.session.exec(select(Tenant).where(Tenant.subdomain == subdomain)).first()
        return existing is not None


def _ensure_ip_table(session: "Session") -> None:
    """Create ipaddressusage table and indexes if missing (PostgreSQL)."""
    try:
        session.execute(sql_text(
            """
            CREATE TABLE IF NOT EXISTS ipaddressusage (
              id SERIAL PRIMARY KEY,
              ip_hash TEXT NOT NULL,
              purpose TEXT NOT NULL,
              tenant_id INTEGER NULL,
              user_id INTEGER NULL,
              count INTEGER NOT NULL DEFAULT 0,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              blocked_reason TEXT NULL
            );
            """
        ))
        session.execute(sql_text("CREATE UNIQUE INDEX IF NOT EXISTS ipaddressusage_ip_purpose_ux ON ipaddressusage (ip_hash, purpose)"))
        session.execute(sql_text("CREATE INDEX IF NOT EXISTS ipaddressusage_ip_hash_idx ON ipaddressusage (ip_hash)"))
        session.execute(sql_text("CREATE INDEX IF NOT EXISTS ipaddressusage_purpose_idx ON ipaddressusage (purpose)"))
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass

# Security scheme for token validation
security = HTTPBearer()

# Token cache (in production, use Redis or similar)
token_cache: Dict[str, UserAuth] = {}


async def authenticate_user(oauth_provider: str, token_data: Dict[str, Any]) -> UserAuth:
    """
    Authenticate user based on OAuth provider and token data.
    
    Args:
        oauth_provider: The OAuth provider (google, apple, etc.)
        token_data: The token data from the OAuth provider
        
    Returns:
        UserAuth: Authenticated user data
        
    Raises:
        ValueError: If OAuth provider is unsupported
        NotImplementedError: If OAuth provider is not yet implemented
    """
    if oauth_provider == "google":
        user_info = await get_google_user_info(token_data)
        return UserAuth(
            user_id=user_info["id"],
            email=user_info["email"],
            name=user_info.get("name", ""),
            provider="google",
            profile_picture_url=user_info.get("picture")
        )
    elif oauth_provider == "github":
        user_info = await get_github_user_info(token_data)
        return UserAuth(
            user_id=user_info["id"],
            email=user_info["email"],
            name=user_info.get("name", ""),
            provider="github",
            profile_picture_url=user_info.get("picture")
        )
    elif oauth_provider == "microsoft":
        user_info = await get_microsoft_user_info(token_data)
        return UserAuth(
            user_id=user_info["id"],
            email=user_info["email"],
            name=user_info.get("name", ""),
            provider="microsoft",
            profile_picture_url=user_info.get("picture")
        )
    elif oauth_provider == "slack":
        user_info = await get_slack_user_info(token_data)
        return UserAuth(
            user_id=user_info.get("id") or secrets.token_hex(8),
            email=(user_info.get("email") or ""),
            name=user_info.get("name", "Slack User"),
            provider="slack",
            profile_picture_url=user_info.get("picture")
        )
    # Restrict providers per Phase 8 (Google/GitHub/Microsoft only)
    elif oauth_provider == "apple":
        raise ValueError("Unsupported OAuth provider: apple")
    else:
        raise ValueError(f"Unsupported OAuth provider: {oauth_provider}")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(lambda: get_session(None))  # Unscoped for auth
) -> User:
    """
    FastAPI dependency to get the current authenticated user.
    
    Args:
        credentials: HTTP Authorization header credentials
        session: Database session
        
    Returns:
        User: The authenticated user from the database
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode the token
        token_data = decode_access_token(credentials.credentials)
        
        if token_data.user_id is None or token_data.email is None:
            raise credentials_exception
            
        # Check if user exists in database
        statement = select(User).where(User.user_id == token_data.user_id)
        user = session.exec(statement).first()
        
        if user is None:
            raise credentials_exception
            
        return user
    except Exception:
        raise credentials_exception


def get_current_user_with_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(lambda: get_session(None))  # Unscoped for auth
) -> tuple[User, Tenant]:
    """
    FastAPI dependency to get the current authenticated user and their tenant.
    
    Args:
        credentials: HTTP Authorization header credentials
        session: Database session
        
    Returns:
        tuple[User, Tenant]: The authenticated user and their tenant from the database
        
    Raises:
        HTTPException: If token is invalid or user/tenant not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode the token
        token_data = decode_access_token(credentials.credentials)
        
        if token_data.user_id is None or token_data.email is None:
            raise credentials_exception
            
        # Check if user exists in database
        statement = select(User).where(User.user_id == token_data.user_id)
        user = session.exec(statement).first()
        
        if user is None:
            raise credentials_exception
            
        # Get the tenant for this user
        tenant_statement = select(Tenant).where(Tenant.id == user.tenant_id)
        tenant = session.exec(tenant_statement).first()
        
        if tenant is None:
            raise credentials_exception
            
        return user, tenant
    except Exception:
        raise credentials_exception


def create_user(session: Session, user_auth: UserAuth, tenant_id: int) -> User:
    """
    Create a new user from OAuth data.
    
    Args:
        session: Database session
        user_auth: Authenticated user data
        tenant_id: Tenant ID for the user
        
    Returns:
        User: The created user
    """
    # Check if user already exists
    existing_user = get_user_by_provider_id(session, user_auth.user_id)
    if existing_user:
        # Update existing user's information
        existing_user.email = user_auth.email
        existing_user.name = user_auth.name
        existing_user.profile_picture_url = user_auth.profile_picture_url
        existing_user.provider = user_auth.provider
        existing_user.last_login = datetime.utcnow()
        session.add(existing_user)
        session.commit()
        session.refresh(existing_user)
        return existing_user
    
    # Create new user
    user = User(
        user_id=user_auth.user_id,
        email=user_auth.email,
        name=user_auth.name,
        profile_picture_url=user_auth.profile_picture_url,
        provider=user_auth.provider,
        last_login=datetime.utcnow(),
        tenant_id=tenant_id
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return user


def get_user_by_provider_id(session: Session, provider_id: str) -> Optional[User]:
    """
    Get user by OAuth provider ID.
    
    Args:
        session: Database session
        provider_id: OAuth provider user ID
        
    Returns:
        User: The user if found, None otherwise
    """
    statement = select(User).where(User.user_id == provider_id)
    return session.exec(statement).first()


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    """Get user by email."""
    statement = select(User).where(User.email == email)
    return session.exec(statement).first()


# =====================
# Password hashing utils
# =====================

def _hash_password(password: str, iterations: int = 200_000) -> str:
    """Return a PBKDF2-SHA256 hash string: pbkdf2_sha256$iterations$salt_b64$hash_b64"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_str, salt_b64, hash_b64 = stored.split('$', 3)
        if algo != 'pbkdf2_sha256':
            return False
        iterations = int(iters_str)
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(hash_b64.encode())
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# =====================
# Password auth flows
# =====================

async def password_signup(
    email: str,
    password: str,
    session: Session,
    name: Optional[str] = None,
    invite_token: Optional[str] = None,
    tenant_id: Optional[int] = None,
    client_ip: Optional[str] = None,
    subdomain: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a user with email/password with timeout protection.
    
    Wraps the actual signup logic with a 15-second timeout to prevent indefinite hangs.
    """
    try:
        return await asyncio.wait_for(
            _password_signup_impl(email, password, session, name, invite_token, tenant_id, client_ip, subdomain),
            timeout=15.0  # 15-second hard limit
        )
    except asyncio.TimeoutError:
        try:
            session.rollback()
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Signup request timed out. Please try again."
        )


async def _password_signup_impl(
    email: str,
    password: str,
    session: Session,
    name: Optional[str] = None,
    invite_token: Optional[str] = None,
    tenant_id: Optional[int] = None,
    client_ip: Optional[str] = None,
    subdomain: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a user with email/password, enforcing invite policy and no tenant switching."""
    # Environment flags
    multi_tenant_enabled = os.getenv("ENABLE_MULTI_TENANT", "true").lower() == "true"
    enforce_invite = os.getenv("MULTI_TENANT_ENFORCE_INVITE", "false").lower() == "true"
    enforce_ip_limit = os.getenv("ENFORCE_SIGNUP_IP_LIMIT", "false").lower() == "true"
    block_vpn = os.getenv("BLOCK_VPN_SIGNUP", "false").lower() == "true"
    
    existing_by_email = get_user_by_email(session, email)
    if existing_by_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Strict anti-VPN and one-account-per-IP enforcement (feature-flagged)
    ip = (client_ip or "").strip()
    enforce_ip_limit = os.getenv("ENFORCE_SIGNUP_IP_LIMIT", "false").lower() == "true"
    block_vpn = os.getenv("BLOCK_VPN_SIGNUP", "false").lower() == "true"
    if ip and ip.lower() != "unknown" and (enforce_ip_limit or block_vpn):
        try:
            if block_vpn:
                vpn_res = await is_vpn_or_proxy(ip)
                if vpn_res.is_risky:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signup blocked: VPN/Proxy/Hosting IP not allowed")
            if enforce_ip_limit:
                _ensure_ip_table(session)
                ip_h = hash_ip(ip)
                existing_ip = session.exec(select(IPAddressUsage).where(
                    IPAddressUsage.ip_hash == ip_h,
                    IPAddressUsage.purpose == "account_signup",
                )).first()
                if existing_ip:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signup blocked: this IP has already created an account")
        except Exception:
            # If table doesn't exist or any error occurs, do not block signup
            pass

    created_tenant_subdomain: Optional[str] = None

    # Determine tenant for new user
    if enforce_invite and multi_tenant_enabled:
        if not invite_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invite required to join a tenant")
        inv = session.exec(select(TenantInvite).where(TenantInvite.token == invite_token)).first()
        now = datetime.utcnow()
        if (
            not inv
            or inv.used_at is not None
            or inv.expires_at <= now
            or (inv.email and email.lower() != inv.email.lower())
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired invite")
        tenant_id = inv.tenant_id
        inv.used_at = now
        session.add(inv)
        session.commit()
        session.refresh(inv)
    else:
        if tenant_id is None:
            # SECURITY: Always create a new tenant for a new user if not invited.
            # Do NOT fall back to a shared default tenant.
            from src.services.dns_manager import DNSManager
            from src.database.models import Tenant
            
            # Enforce mandatory subdomain selection
            if not subdomain:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Subdomain is required for new account creation"
                )
            
            # Validate subdomain
            dns_manager = DNSManager()
            is_valid, error_msg = dns_manager.validate_subdomain(subdomain)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid subdomain: {error_msg}"
                )
            
            # Check uniqueness (DB check)
            # Reset tenant context and set requested subdomain for RLS
            # Use set_config to explicitly set to NULL on the current connection
            if _is_postgres_session(session):
                session.connection().execute(sql_text("SELECT set_config('app.tenant_id', NULL, false)"))
            
            safe_sub = subdomain.replace("'", "")
            if _is_postgres_session(session):
                session.exec(sql_text(f"SET app.requested_subdomain = '{safe_sub}'"))

            existing = session.exec(select(Tenant).where(Tenant.subdomain == subdomain)).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Subdomain is already taken"
                )
            
            # Create tenant
            tenant = Tenant(
                tenant_id=Tenant.generate_unique_id(),
                subdomain=subdomain,
                name=f"{name or email}'s Workspace",
                admin_email=email
            )
            session.add(tenant)
            session.commit()
            
            # After commit, SQLAlchemy has populated tenant.id via RETURNING
            tenant_id = tenant.id
            created_tenant_subdomain = tenant.subdomain
            
            # Set tenant context for user creation (RLS)
            if _is_postgres_session(session):
                session.exec(sql_text(f"SET app.tenant_id = '{tenant_id}'"))
            
            # Note: We skip session.refresh(tenant) because RLS might block it
            # and we already have all the data we need

    # Create user
    pwd_hash = _hash_password(password)
    user = User(
        user_id=f"pwd_{secrets.token_hex(8)}",
        email=email,
        name=name or email.split('@')[0],
        provider="password",
        profile_picture_url=None,
        last_login=datetime.utcnow(),
        tenant_id=tenant_id,
        password_hash=pwd_hash,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Grant initial credits to new user (100 credits)
    try:
        from src.services.pricing.credit_manager import CreditManager
        credit_mgr = CreditManager()
        # Use allocate instead of add (method name correction)
        await credit_mgr.allocate(user_id=user.id, amount=100, tenant_id=str(tenant_id))
    except Exception as e:
        # Don't block signup if credit grant fails
        import logging
        logging.getLogger(__name__).warning(f"Failed to grant initial credits to user {user.user_id}: {e}")

    tenant_subdomain = created_tenant_subdomain
    if tenant_subdomain is None:
        try:
            if tenant_id is not None and _is_postgres_session(session):
                try:
                    session.exec(sql_text(f"SET app.tenant_id = '{tenant_id}'"))
                except Exception:
                    pass
            tenant = session.exec(select(Tenant).where(Tenant.id == user.tenant_id)).first()
            tenant_subdomain = tenant.subdomain if tenant else None
        except Exception:
            tenant_subdomain = None
    access_token = create_access_token(
        data={
            "sub": user.user_id,
            "email": user.email,
            "tenant_id": user.tenant_id,
            "tenant_subdomain": tenant_subdomain,
        },
        expires_delta=timedelta(minutes=30),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserAuth(
            user_id=user.user_id, 
            email=user.email or "", 
            name=user.name or "", 
            provider=user.provider, 
            profile_picture_url=user.profile_picture_url,
            tenant_subdomain=tenant_subdomain
        ),
    }


async def password_login(
    email: str,
    password: str,
    session: Session,
    invite_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Login user with email/password and enforce no tenant switching with invites."""
    user = get_user_by_email(session, email)
    if not user or not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not _verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Optional: if invite_token provided, ensure it doesn't point to another tenant (no switching)
    multi_tenant_enabled = os.getenv("ENABLE_MULTI_TENANT", "true").lower() == "true"
    enforce_invite = os.getenv("MULTI_TENANT_ENFORCE_INVITE", "false").lower() == "true"
    if invite_token and multi_tenant_enabled and enforce_invite:
        inv = session.exec(select(TenantInvite).where(TenantInvite.token == invite_token)).first()
        if inv and inv.tenant_id != user.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant switching is not allowed")

    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()

    # Include tenant_subdomain for frontend subdomain redirects
    try:
        tenant = session.exec(select(Tenant).where(Tenant.id == user.tenant_id)).first()
        tenant_subdomain = tenant.subdomain if tenant else None
    except Exception:
        tenant_subdomain = None
    access_token = create_access_token(
        data={
            "sub": user.user_id,
            "email": user.email,
            "tenant_id": user.tenant_id,
            "tenant_subdomain": tenant_subdomain,
        },
        expires_delta=timedelta(minutes=30),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserAuth(
            user_id=user.user_id, 
            email=user.email or "", 
            name=user.name or "", 
            provider=user.provider, 
            profile_picture_url=user.profile_picture_url,
            tenant_subdomain=tenant_subdomain
        ),
    }


async def handle_oauth_callback(
    oauth_provider: str,
    code: str,
    session: Session,
    tenant_id: Optional[int] = None,
    invite_token: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Handle OAuth callback and create/authenticate user.
    
    Args:
        oauth_provider: The OAuth provider (google, apple, etc.)
        code: Authorization code from OAuth provider
        session: Database session
        tenant_id: Optional tenant ID (if multi-tenant)
        
    Returns:
        Dict: Access token and user information
    """
    # Resolve tenant-scoped OAuth client overrides if available
    client_id_override: Optional[str] = None
    client_secret_override: Optional[str] = None
    try:
        if tenant_id is not None:
            tsm = TenantSecretsManager()
            service_name = oauth_provider  # 'google' | 'github' | 'microsoft' | 'slack'
            creds = await tsm.get_secret(str(tenant_id), service_name, "oauth_credentials")
            if isinstance(creds, dict):
                client_id_override = (creds.get("client_id") or creds.get("id") or None)
                client_secret_override = (creds.get("client_secret") or creds.get("secret") or None)
    except Exception:
        # Fallback silently to env-configured app if overrides are not present
        pass

    # Exchange code for token (with overrides when provided)
    if oauth_provider == "google":
        token_data = await exchange_google_code_for_token(
            code,
            redirect_uri=redirect_uri,
            client_id=client_id_override,
            client_secret=client_secret_override,
        )
    elif oauth_provider == "github":
        token_data = await exchange_github_code_for_token(
            code,
            redirect_uri=redirect_uri,
            client_id=client_id_override,
            client_secret=client_secret_override,
        )
    elif oauth_provider == "microsoft":
        token_data = await exchange_microsoft_code_for_token(
            code,
            redirect_uri=redirect_uri,
            client_id=client_id_override,
            client_secret=client_secret_override,
        )
        
    elif oauth_provider == "slack":
        token_data = await exchange_slack_code_for_token(
            code,
            redirect_uri=redirect_uri,
            client_id=client_id_override,
            client_secret=client_secret_override,
        )
    # Restrict providers per Phase 8 (Google/GitHub/Microsoft only)
    elif oauth_provider == "apple":
        raise ValueError("Unsupported OAuth provider: apple")
    else:
        raise ValueError(f"Unsupported OAuth provider: {oauth_provider}")
    
    # Authenticate user
    user_auth = await authenticate_user(oauth_provider, token_data)

    # Environment flags
    multi_tenant_enabled = os.getenv("ENABLE_MULTI_TENANT", "true").lower() == "true"
    enforce_invite = os.getenv("MULTI_TENANT_ENFORCE_INVITE", "false").lower() == "true"
    enforce_ip_limit = os.getenv("ENFORCE_SIGNUP_IP_LIMIT", "false").lower() == "true"
    block_vpn = os.getenv("BLOCK_VPN_SIGNUP", "false").lower() == "true"

    # Determine existing user and enforce no-tenant-switching
    existing_user = get_user_by_provider_id(session, user_auth.user_id)

    if existing_user:
        # If invite provided but points to a different tenant, block switching
        if invite_token and enforce_invite and multi_tenant_enabled:
            inv_stmt = select(TenantInvite).where(TenantInvite.token == invite_token)
            inv = session.exec(inv_stmt).first()
            if inv and inv.tenant_id != existing_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant switching is not allowed"
                )
        tenant_id = existing_user.tenant_id
    else:
        # New user flow - auto-create tenant
        if multi_tenant_enabled:
            if enforce_invite and invite_token:
                # If invite provided, use invite tenant (optional invite flow)
                inv_stmt = select(TenantInvite).where(TenantInvite.token == invite_token)
                invite = session.exec(inv_stmt).first()
                now = datetime.utcnow()
                if (
                    invite
                    and invite.used_at is None
                    and invite.expires_at > now
                    and (not invite.email or (user_auth.email or "").lower() == invite.email.lower())
                ):
                    # Valid invite - use invite tenant
                    tenant_id = invite.tenant_id
                    invite.used_at = now
                    session.add(invite)
                    session.commit()
                else:
                    # Invalid invite - fall through to auto-creation
                    pass
            
            if tenant_id is None:
                # Auto-create tenant for new user
                from src.services.dns_manager import DNSManager, generate_unique_subdomain
                from src.database.models import Tenant
                
                dns_manager = DNSManager()
                
                # Generate subdomain from user info
                # Priority: First name > Email username
                base_name = None
                if user_auth.name:
                    # Take first word of name (usually first name)
                    base_name = user_auth.name.split()[0]
                elif user_auth.email:
                    # Use part before @ in email
                    base_name = user_auth.email.split('@')[0]
                else:
                    base_name = "user"
                
                # Get existing subdomains for uniqueness check
                # Use SubdomainChecker to check DB on demand (RLS-compliant)
                checker = SubdomainChecker(session)
                
                # Generate unique subdomain
                subdomain = generate_unique_subdomain(base_name, checker)
                
                # Validate subdomain (should always pass if generate_unique_subdomain works)
                is_valid, error = dns_manager.validate_subdomain(subdomain)
                if not is_valid:
                    # Fallback to generic tenant naming
                    subdomain = generate_unique_subdomain("tenant", existing_subdomains)
                
                # Create tenant
                tenant = Tenant(
                    tenant_id=Tenant.generate_unique_id(),
                    subdomain=subdomain,
                    name=f"{user_auth.name}'s Workspace" if user_auth.name else "My Workspace",
                    admin_email=user_auth.email or ""
                )
                session.add(tenant)
                session.flush()  # Get ID but don't commit yet
                
                tenant_id = tenant.id
        else:
            # Single-tenant mode: use provided tenant_id or default tenant
            if tenant_id is None:
                default_tenant = session.exec(select(Tenant).where(Tenant.subdomain == "default")).first()
                if default_tenant:
                    tenant_id = default_tenant.id
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Default tenant not found"
                    )

    # Strict anti-VPN and one-account-per-IP enforcement (only for new accounts; feature-flagged)
    ip = (client_ip or "").strip()
    if existing_user is None and ip and ip.lower() != "unknown" and (enforce_ip_limit or block_vpn):
        try:
            if block_vpn:
                vpn_res = await is_vpn_or_proxy(ip)
                if vpn_res.is_risky:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signup blocked: VPN/Proxy/Hosting IP not allowed")
            if enforce_ip_limit:
                _ensure_ip_table(session)
                ip_h = hash_ip(ip)
                existing_ip = session.exec(select(IPAddressUsage).where(
                    IPAddressUsage.ip_hash == ip_h,
                    IPAddressUsage.purpose == "account_signup",
                )).first()
                if existing_ip:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signup blocked: this IP has already created an account")
        except Exception as e:
            # If table doesn't exist or any error occurs, do not block signup
            print(f"Error during signup IP check: {e}")
    
    # Create or get user in database
    user = create_user(session, user_auth, tenant_id)
    
    # Include tenant_subdomain claim for redirect
    try:
        t = session.exec(select(Tenant).where(Tenant.id == tenant_id)).first()
        t_sub = t.subdomain if t else None
    except Exception:
        t_sub = None
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={
            "sub": user_auth.user_id,
            "email": user_auth.email,
            "tenant_id": tenant_id,
            "tenant_subdomain": t_sub,
        },
        expires_delta=access_token_expires,
    )
    
    # Record IP usage for account signup (best-effort; only when enforcement enabled)
    try:
        if enforce_ip_limit and existing_user is None:
            ip = (client_ip or "").strip()
            if ip and ip.lower() != "unknown":
                _ensure_ip_table(session)
                rec = IPAddressUsage(
                    ip_hash=hash_ip(ip),
                    purpose="account_signup",
                    tenant_id=tenant_id,
                    user_id=user.id,
                    count=1,
                )
                session.add(rec)
                session.commit()
    except Exception:
        pass

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_auth
    }
