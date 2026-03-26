"""Utility for RLS tenant context management."""
from sqlalchemy import text
from typing import Optional


def _is_postgres_session(session) -> bool:
    try:
        bind = session.get_bind()
        if not bind:
            return False
        return (getattr(bind.dialect, "name", "") or "").lower() in {"postgresql", "postgres"}
    except Exception:
        return False


def set_session_tenant_context(session, tenant_id: Optional[int]) -> None:
    """
    Set app.tenant_id on the given database session's connection for RLS enforcement.
    
    IMPORTANT: Uses session.connection() to ensure the SET runs on the same
    connection that will be used for subsequent operations.
    
    Args:
        session: SQLAlchemy/SQLModel session (sync)
        tenant_id: Tenant ID to set, or None for onboarding flows
    """
    # Get the actual connection to ensure SET runs on the same connection as INSERT
    if not _is_postgres_session(session):
        return
    conn = session.connection()
    if tenant_id is not None:
        conn.execute(text("SET app.tenant_id = :tenant_id"), {"tenant_id": str(tenant_id)})
    else:
        conn.execute(text("SELECT set_config('app.tenant_id', NULL, false)"))


async def set_session_tenant_context_async(session, tenant_id: Optional[int]) -> None:
    """
    Async version of set_session_tenant_context.
    
    IMPORTANT: Uses session.connection() to ensure the SET runs on the same
    connection that will be used for subsequent operations.
    
    Args:
        session: Async SQLAlchemy session
        tenant_id: Tenant ID to set, or None for onboarding flows
    """
    # Get the actual connection to ensure SET runs on the same connection as INSERT
    if not _is_postgres_session(session):
        return
    conn = await session.connection()
    if tenant_id is not None:
        await conn.execute(text("SET app.tenant_id = :tenant_id"), {"tenant_id": str(tenant_id)})
    else:
        await conn.execute(text("SELECT set_config('app.tenant_id', NULL, false)"))

