import strawberry
from strawberry.types import Info
from typing import Optional

from src.auth.models import Token, UserAuth
from src.auth.service import handle_oauth_callback, password_signup, password_login
from src.database.models import User
from src.etherion_ai.graphql_schema.output_types import UserAuthType
from src.utils.ip_utils import get_client_ip


@strawberry.type
class AuthResponse:
    """
    Response structure for authentication operations.
    
    Example:
    {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "token_type": "bearer",
      "user": {
        "user_id": "123456789",
        "email": "user@example.com",
        "name": "John Doe",
        "provider": "google",
        "profile_picture_url": "https://example.com/profile.jpg"
      }
    }
    """
    access_token: str = strawberry.field(
        description="""JWT access token for authenticating subsequent requests.
        
        Constraints:
        - Must be a valid JWT token
        - Expires after 30 minutes"""
    )
    token_type: str = strawberry.field(
        description="""Type of token (typically 'bearer').
        
        Constraints:
        - Must be 'bearer'"""
    )
    user: UserAuthType = strawberry.field(
        description="Authenticated user information."
    )


@strawberry.type
class CurrentUserResponse:
    """
    Response structure for current user information.
    
    Example:
    {
      "id": 123,
      "user_id": "123456789",
      "created_at": "2023-01-01T00:00:00"
    }
    """
    user_id: str = strawberry.field(
        description="OAuth provider user ID."
    )
    created_at: str = strawberry.field(
        description="ISO format timestamp of when the user was created."
    )


@strawberry.type
class AuthMutation:
    @strawberry.mutation
    async def googleLogin(
        self, 
        info: Info,
        code: str,
        invite_token: Optional[str] = None,
        redirect_uri: Optional[str] = None
    ) -> AuthResponse:
        """
        Authenticate user with Google OAuth.
        
        This mutation exchanges a Google OAuth authorization code for an access token
        and creates or updates the user in the database.
        
        Example usage:
        mutation {
            googleLogin(code: "4/0AX4XfWhG...") {
                access_token
                token_type
                user {
                    user_id
                    email
                    name
                }
            }
        }
        
        Args:
            code: Authorization code from Google OAuth
            invite_token: Optional invite token for multi-tenant signup
            redirect_uri: OAuth redirect URI (must match authorization request)
            
        Returns:
            AuthResponse: Access token and user information
            
        Errors:
            - If the authorization code is invalid or expired
            - If OAuth credentials are not configured
            - If there's an issue communicating with Google's OAuth service
            - If there's a database error while creating/updating the user
        """
        try:
            # Get database session from GraphQL context
            auth_context = info.context.get("request").state.auth_context
            db_session = auth_context["db_session"]
            
            request = info.context.get("request")
            client_ip = get_client_ip(request)
            result = await handle_oauth_callback("google", code, db_session, invite_token=invite_token, redirect_uri=redirect_uri, client_ip=client_ip)
            
            return AuthResponse(
                access_token=result["access_token"],
                token_type=result["token_type"],
                user=result["user"]
            )
        except ValueError as e:
            # Configuration/validation errors - user-facing and clear
            raise Exception(str(e))
        except Exception as e:
            # Check for HTTPException detail attribute
            if hasattr(e, 'detail'):
                raise Exception(e.detail)
            # Unexpected errors - log but provide safe generic message
            import traceback
            traceback.print_exc()
            raise Exception(f"Google login failed: {str(e)}")

    @strawberry.mutation
    async def githubLogin(
        self,
        info: Info,
        code: str,
        invite_token: Optional[str] = None,
        redirect_uri: Optional[str] = None
    ) -> AuthResponse:
        """
        Authenticate user with GitHub OAuth.
        
        Args:
            code: Authorization code from GitHub OAuth
            invite_token: Optional invite token for multi-tenant signup
            redirect_uri: OAuth redirect URI (must match authorization request)
        """
        try:
            auth_context = info.context.get("request").state.auth_context
            db_session = auth_context["db_session"]
            request = info.context.get("request")
            client_ip = get_client_ip(request)
            result = await handle_oauth_callback("github", code, db_session, invite_token=invite_token, redirect_uri=redirect_uri, client_ip=client_ip)
            return AuthResponse(
                access_token=result["access_token"],
                token_type=result["token_type"],
                user=result["user"]
            )
        except ValueError as e:
            raise Exception(str(e))
        except Exception as e:
            if hasattr(e, 'detail'):
                raise Exception(e.detail)
            import traceback
            traceback.print_exc()
            raise Exception(f"GitHub login failed: {str(e)}")

    @strawberry.mutation
    async def microsoftLogin(
        self,
        info: Info,
        code: str,
        invite_token: Optional[str] = None,
        redirect_uri: Optional[str] = None
    ) -> AuthResponse:
        """
        Authenticate user with Microsoft OAuth.
        
        Args:
            code: Authorization code from Microsoft OAuth
            invite_token: Optional invite token for multi-tenant signup
            redirect_uri: OAuth redirect URI (must match authorization request)
        """
        try:
            auth_context = info.context.get("request").state.auth_context
            db_session = auth_context["db_session"]
            request = info.context.get("request")
            client_ip = get_client_ip(request)
            result = await handle_oauth_callback("microsoft", code, db_session, invite_token=invite_token, redirect_uri=redirect_uri, client_ip=client_ip)
            return AuthResponse(
                access_token=result["access_token"],
                token_type=result["token_type"],
                user=result["user"]
            )
        except ValueError as e:
            raise Exception(str(e))
        except Exception as e:
            if hasattr(e, 'detail'):
                raise Exception(e.detail)
            import traceback
            traceback.print_exc()
            raise Exception(f"Microsoft login failed: {str(e)}")

    @strawberry.mutation
    async def passwordSignup(
        self,
        info: Info,
        email: str,
        password: str,
        name: Optional[str] = None,
        invite_token: Optional[str] = None,
        subdomain: Optional[str] = None,
    ) -> AuthResponse:
        """Sign up with email/password (invite enforced when configured)."""
        auth_context = info.context.get("request").state.auth_context
        db_session = auth_context["db_session"]
        request = info.context.get("request")
        client_ip = get_client_ip(request)
        result = await password_signup(
            email=email, 
            password=password, 
            session=db_session, 
            name=name, 
            invite_token=invite_token, 
            subdomain=subdomain,
            client_ip=client_ip
        )
        return AuthResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            user=result["user"],
        )

    @strawberry.mutation
    async def passwordLogin(
        self,
        info: Info,
        email: str,
        password: str,
        invite_token: Optional[str] = None,
    ) -> AuthResponse:
        """Login with email/password (no tenant switching with invites)."""
        auth_context = info.context.get("request").state.auth_context
        db_session = auth_context["db_session"]
        result = await password_login(email=email, password=password, session=db_session, invite_token=invite_token)
        return AuthResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            user=result["user"],
        )

    @strawberry.mutation
    async def appleLogin(
        self,
        info: Info,
        code: str
    ) -> AuthResponse:
        """
        Authenticate user with Apple Sign-In (placeholder).
        
        This mutation is a placeholder for Apple Sign-In functionality.
        Apple OAuth implementation is pending.
        
        Example usage:
        mutation {
          appleLogin(code: "c123456789...") {
            access_token
            token_type
            user {
              user_id
              email
              name
            }
          }
        }
        
        Args:
            code: Authorization code from Apple OAuth
            
        Returns:
            AuthResponse: Access token and user information
            
        Errors:
            - Not implemented error (placeholder)
        """
        # Apple OAuth implementation pending
        raise NotImplementedError("Apple OAuth implementation pending")

    @strawberry.mutation
    async def logout(self, info: Info, token: str) -> bool:
        """
        Logout user by invalidating token.
        
        This mutation invalidates the provided JWT token, effectively logging out the user.
        In a production implementation, this would add the token to a blacklist.
        
        Example usage:
        mutation {
          logout(token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...") 
        }
        
        Args:
            token: JWT token to invalidate
            
        Returns:
            bool: True if successful (currently always returns True as a placeholder)
        """
        try:
            from src.core.redis import get_redis_client
            import hashlib
            h = hashlib.sha256(token.encode()).hexdigest()
            redis = get_redis_client()
            client = await redis.get_client()
            # Set TTL from token exp if available
            from jose import jwt
            import time as _time
            ttl = 45 * 60
            try:
                data = jwt.get_unverified_claims(token)
                exp = int(data.get("exp", 0))
                now = int(_time.time())
                if exp > now:
                    ttl = max(60, exp - now)
            except Exception:
                pass
            await client.setex(f"token:blacklist:{h}", ttl, "1")
            # Audit
            try:
                from src.core.security.audit_logger import log_security_event
                ctx = info.context.get("request").state.auth_context
                current_user = ctx.get("current_user") if ctx else None
                await log_security_event(
                    event_type="logout",
                    user_id=current_user.id if current_user else None,
                    tenant_id=current_user.tenant_id if current_user else None,
                    details={"reason": "user_logout"},
                )
            except Exception:
                pass
            return True
        except Exception:
            return True

    @strawberry.mutation
    async def refresh_token(self, info: Info, refresh_token: str) -> AuthResponse:
        """
        Refresh authentication token.
        
        This mutation exchanges a refresh token for a new access token.
        Token refresh implementation is pending.
        
        Example usage:
        mutation {
          refresh_token(refresh_token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...") {
            access_token
            token_type
          }
        }
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            Token: New access token
            
        Errors:
            - Not implemented error (placeholder)
        """
        from src.auth.jwt import decode_refresh_token, create_token_pair
        from src.core.redis import get_redis_client
        import hashlib
        from sqlmodel import select
        from src.database.models import User, Tenant
        from src.etherion_ai.graphql_schema.output_types import UserAuthType
        token_data = decode_refresh_token(refresh_token)
        auth_context = info.context.get("request").state.auth_context
        db_session = auth_context["db_session"]
        statement = select(User).where(User.user_id == token_data.user_id)
        user = db_session.exec(statement).first()
        if not user:
            raise Exception("User not found")
        try:
            h = hashlib.sha256(refresh_token.encode()).hexdigest()
            redis = get_redis_client()
            client = await redis.get_client()
            await client.setex(f"token:blacklist:{h}", 7 * 24 * 3600, "1")
        except Exception:
            pass
        # Include tenant_subdomain claim in refreshed tokens for frontend redirects
        try:
            tenant = db_session.exec(select(Tenant).where(Tenant.id == user.tenant_id)).first()
            tenant_subdomain = tenant.subdomain if tenant else None
        except Exception:
            tenant_subdomain = None
        pair = create_token_pair({
            "sub": user.user_id,
            "email": user.email,
            "tenant_id": user.tenant_id,
            "tenant_subdomain": tenant_subdomain,
        })
        try:
            from src.core.security.audit_logger import log_security_event
            await log_security_event(
                event_type="token_rotated",
                user_id=user.id,
                tenant_id=user.tenant_id,
                details={"user_id": user.user_id},
            )
        except Exception:
            pass
        return AuthResponse(
            access_token=pair["access_token"],
            token_type=pair["token_type"],
            user=UserAuthType(
                user_id=user.user_id,
                email=user.email or "",
                name=user.name or "",
                provider=user.provider,
                profile_picture_url=user.profile_picture_url or "",
            ),
        )

    @strawberry.field
    def getCurrentUser(
        self,
        info: Info,
    ) -> CurrentUserResponse:
        """
        Get current authenticated user information.
        
        This query returns information about the currently authenticated user.
        Requires a valid JWT token in the Authorization header.
        
        Example usage:
        query {
          getCurrentUser {
            user_id
            created_at
          }
        }
        
        Returns:
            CurrentUserResponse: User information
            
        Errors:
            - If the JWT token is missing, invalid, or expired
            - If the user is not found in the database
        """
        # Get current user from GraphQL context
        auth_context = info.context.get("request").state.auth_context
        current_user = auth_context["current_user"]
        
        if not current_user:
            raise Exception("Not authenticated")
            
        return CurrentUserResponse(
            user_id=current_user.user_id,
            created_at=current_user.created_at.isoformat()
        )