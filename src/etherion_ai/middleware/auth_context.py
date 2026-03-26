# src/etherion_ai/middleware/auth_context.py
from fastapi import Request
from sqlmodel import select
from sqlalchemy import text
from src.database.db import get_db, session_scope
from src.database.models import User, Tenant
from src.auth.jwt import decode_access_token
from src.utils.tenant_context import set_tenant_context
from src.core.redis import get_redis_client
import hashlib
import os
import asyncio


async def resolve_current_user_from_headers(headers) -> tuple[User | None, int | None]:
    auth_header = None
    try:
        auth_header = headers.get("Authorization") or headers.get("authorization")
    except Exception:
        auth_header = None

    if not auth_header or not auth_header.startswith("Bearer "):
        return None, None

    token = auth_header.replace("Bearer ", "")
    try:
        token_data = decode_access_token(token)
    except Exception:
        return None, None

    try:
        set_tenant_context(getattr(token_data, "tenant_id", None))
    except Exception:
        pass

    try:
        redis = get_redis_client()
        h = hashlib.sha256(token.encode()).hexdigest()
        if await redis.get(f"token:blacklist:{h}"):
            return None, None
    except Exception:
        pass

    if not getattr(token_data, "user_id", None):
        return None, None

    try:
        with session_scope() as auth_session:
            statement = select(User).where(User.user_id == token_data.user_id)
            current_user = auth_session.exec(statement).first()
            if current_user:
                return current_user, current_user.tenant_id
    except Exception:
        return None, None

    return None, None


async def graphql_auth_middleware(request: Request, call_next):
    """Middleware to populate GraphQL context with auth info and keep DB session alive during request.

    Important: We must keep the AsyncSession open across the GraphQL request lifecycle; otherwise
    resolvers will see a closed session and GraphQL will return data=null (leading to None.get in tests).
    """
    if request.url.path != "/graphql":
        # Non-GraphQL routes skip this middleware (handled by tenant_middleware for REST)
        return await call_next(request)

    current_user, tenant_id = await resolve_current_user_from_headers(request.headers)

    # Set tenant context for downstream
    set_tenant_context(tenant_id)

    # Skip DB session for unauthenticated GraphQL GET (e.g., public health_check)
    try:
        has_auth = bool(request.headers.get("Authorization")) or bool(request.headers.get("authorization"))
    except Exception:
        has_auth = False

    if (not has_auth) and request.method.upper() == "GET":
        request.state.auth_context = {
            "current_user": None,
            "db_session": None,
            "tenant_id": None,
        }
        request.state.tenant_id = None
        return await call_next(request)

    # Keep a synchronous DB session alive for request lifecycle; degrade gracefully on failure
    db_session = None
    try:
        db_session = get_db()
        try:
            # When Cloud SQL RLS policies expect current_setting('app.tenant_id'), ensure a value is set
            # even for unauthenticated requests by using DEFAULT_TENANT_ID. This avoids
            # "unrecognized configuration parameter 'app.tenant_id'" errors.
            if os.getenv("PG_ENABLE_TENANT_GUC", "true").lower() == "true":
                effective_tenant_id = tenant_id
                if effective_tenant_id is None:
                    # Explicitly set to NULL for onboarding flow
                    db_session.execute(text("SELECT set_config('app.tenant_id', NULL, false)"))
                else:
                    db_session.execute(text("SET app.tenant_id = :tenant_id"), {"tenant_id": effective_tenant_id})
        except Exception:
            # If the server rejects custom GUCs (e.g., Cloud SQL), roll back to clear aborted tx
            try:
                db_session.rollback()
            except Exception:
                pass

        request.state.auth_context = {
            "current_user": current_user,
            "db_session": db_session,
            "tenant_id": tenant_id,
        }
        request.state.tenant_id = tenant_id
        response = await call_next(request)
        try:
            db_session.commit()
        except Exception:
            pass
        return response
    except Exception:
        # If DB session creation fails, allow non-mutating requests
        if request.method.upper() == "GET":
            request.state.auth_context = {
                "current_user": current_user,
                "db_session": None,
                "tenant_id": tenant_id,
            }
            request.state.tenant_id = tenant_id
            return await call_next(request)
        # Re-raise for mutations/POST which must have DB access
        raise
    finally:
        try:
            if db_session is not None:
                db_session.close()
        except Exception:
            pass
