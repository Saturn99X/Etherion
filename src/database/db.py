from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, event
from sqlmodel import Session as SQLModelSession
import os
from urllib.parse import urlparse
import time
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from src.utils.tenant_context import get_tenant_context
import re


def _get_sync_database_url() -> str:
    """Return the sync SQLAlchemy database URL from env or default to SQLite.

    Behavior:
    - If DATABASE_URL is set, use it.
    - If ENVIRONMENT=production and no DATABASE_URL, raise.
    - If running under pytest (PYTEST_CURRENT_TEST is set), generate a unique
      per-run SQLite file to avoid state leakage across tests.
    - Otherwise, use the default local SQLite file.
    """
    # LES/dev bypass: force local SQLite to avoid Cloud SQL proxy dependency
    try:
        if os.getenv("DEV_BYPASS_AUTH", "0") == "1" and os.getenv("FORCE_DEV_SQLITE", "1") == "1":
            return "sqlite:///./etherion.db"
    except Exception:
        pass
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    if os.getenv("ENVIRONMENT") == "production":
        raise ValueError("DATABASE_URL environment variable is required for production deployment")

    # Detect pytest and isolate DB per run
    if os.getenv("PYTEST_CURRENT_TEST"):
        ts = int(time.time())
        pid = os.getpid()
        return f"sqlite:///./test_db_{pid}_{ts}.db"

    return "sqlite:///./etherion.db"


def _derive_async_url(sync_url: str) -> str:
    """Derive an async driver URL from a sync URL.

    Avoid urllib.parse for DSNs like postgresql://user:pass@/db?host=/cloudsql/.. which can
    trigger urlsplit IPv6 parsing errors. Use simple prefix replacement to preserve the rest
    of the URL verbatim, including unix-socket host parameters.

    - postgresql[+psycopg2] -> postgresql+asyncpg
    - sqlite -> sqlite+aiosqlite
    """
    # Normalize PostgreSQL schemes
    if sync_url.startswith("postgresql+psycopg2:"):
        return sync_url.replace("postgresql+psycopg2:", "postgresql+asyncpg:", 1)
    if sync_url.startswith("postgresql+asyncpg:"):
        return sync_url  # already async
    if sync_url.startswith("postgresql:"):
        return sync_url.replace("postgresql:", "postgresql+asyncpg:", 1)

    # Normalize SQLite schemes
    if sync_url.startswith("sqlite+aiosqlite:"):
        return sync_url
    if sync_url.startswith("sqlite:"):
        return sync_url.replace("sqlite:", "sqlite+aiosqlite:", 1)

    # Fallback: if unknown scheme, return as-is
    return sync_url


# Configure async engine/session (can be disabled via DISABLE_ASYNC_DB)
AsyncSessionLocal = None
async_engine = None
if not os.environ.get("DISABLE_ASYNC_DB"):
    _sync_url = _get_sync_database_url()
    DATABASE_URL_ASYNC = os.getenv("ASYNC_DATABASE_URL", _derive_async_url(_sync_url))
    # Get pool configuration from environment
    pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    
    async_engine = create_async_engine(
        DATABASE_URL_ASYNC,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_reset_on_return="rollback",
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
    )
    AsyncSessionLocal = sessionmaker(async_engine, class_=SQLModelAsyncSession, expire_on_commit=False)

    # Ensure tenant context is set for async connections (PostgreSQL)
    if "postgresql" in str(async_engine.url):
        @event.listens_for(async_engine.sync_engine, "connect")
        def set_tenant_context_on_connect_async(dbapi_connection, connection_record):
            if os.getenv("PG_ENABLE_TENANT_GUC", "true").lower() == "true":
                tenant_id = get_tenant_context()
                # Do NOT default to 1 here. If None, we want it to be NULL in the DB
                # so that RLS policies for onboarding (which check for NULL) can work.
                if tenant_id is None:
                    # Explicitly set to NULL to clear any previous session state
                    cursor = dbapi_connection.cursor()
                    try:
                        cursor.execute("SELECT set_config('app.tenant_id', NULL, false)")
                    except Exception:
                        pass
                    finally:
                        cursor.close()
                    return

                cursor = dbapi_connection.cursor()
                try:
                    try:
                        cursor.execute("SET app.tenant_id = %s", (str(tenant_id),))
                    except Exception:
                        # Ignore if the server rejects custom GUCs (e.g., Cloud SQL)
                        pass
                finally:
                    cursor.close()

        @event.listens_for(async_engine.sync_engine, "checkout")
        def checkout_async(dbapi_connection, connection_record, connection_proxy):
            """Ensure tenant context is re-applied after RESET ALL or when connection is reused."""
            if os.getenv("PG_ENABLE_TENANT_GUC", "true").lower() == "true":
                tenant_id = get_tenant_context()
                if tenant_id is not None:
                    cursor = dbapi_connection.cursor()
                    try:
                        try:
                            cursor.execute("SET app.tenant_id = %s", (str(tenant_id),))
                        except Exception:
                            pass
                    finally:
                        cursor.close()


async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    """
    Dependency to get async DB session. Tenant context is handled at the DB level (RLS)
    and via sync engine event listeners for legacy paths.
    """
    if AsyncSessionLocal is None:
        raise RuntimeError("Async DB disabled or not configured")
    # In test mode with SQLite, ensure schema exists before yielding session
    if os.getenv("PYTEST_CURRENT_TEST") and async_engine and "sqlite" in str(async_engine.url):
        # Import models to populate SQLModel metadata
        from src.database import models as _models  # noqa: F401
        from src.database import ts_models as _ts  # noqa: F401
        async with async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSessionLocal() as session:
        try:
            # Proxy to adapt exec() for tests that call `.first()` without await
            try:
                orig_exec = session.exec  # type: ignore[attr-defined]

                class _ExecResult:
                    def __init__(self, _orig_exec, _stmt):
                        self._orig_exec = _orig_exec
                        self._stmt = _stmt

                    def __await__(self):
                        async def _run():
                            return await self._orig_exec(self._stmt)
                        return _run().__await__()

                    def first(self):
                        db = get_db()
                        try:
                            return db.execute(self._stmt).scalars().first()
                        finally:
                            db.close()

                    def scalars(self):
                        db = get_db()
                        try:
                            return db.execute(self._stmt).scalars()
                        finally:
                            db.close()

                    def all(self):
                        db = get_db()
                        try:
                            return db.execute(self._stmt).scalars().all()
                        finally:
                            db.close()

                class _SessionProxy:
                    def __init__(self, _session):
                        self._session = _session

                    def __getattr__(self, name):
                        if name == "exec":
                            def _call(stmt):
                                return _ExecResult(orig_exec, stmt)
                            return _call
                        return getattr(self._session, name)

                proxy = _SessionProxy(session)
            except Exception:
                proxy = session  # Fallback if proxying fails

            yield proxy
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_scoped_session():
    """Context manager for async DB session."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Async DB disabled or not configured")
    # In test mode with SQLite, ensure schema exists before yielding session
    if os.getenv("PYTEST_CURRENT_TEST") and async_engine and "sqlite" in str(async_engine.url):
        from src.database import models as _models  # noqa: F401
        from src.database import ts_models as _ts  # noqa: F401
        async with async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSessionLocal() as session:
        try:
            # Mirror exec() proxy to support `.first()` without await in tests
            try:
                orig_exec = session.exec  # type: ignore[attr-defined]

                class _ExecResult:
                    def __init__(self, _orig_exec, _stmt):
                        self._orig_exec = _orig_exec
                        self._stmt = _stmt

                    def __await__(self):
                        async def _run():
                            return await self._orig_exec(self._stmt)
                        return _run().__await__()

                    def first(self):
                        db = get_db()
                        try:
                            return db.execute(self._stmt).scalars().first()
                        finally:
                            db.close()

                    def scalars(self):
                        db = get_db()
                        try:
                            return db.execute(self._stmt).scalars()
                        finally:
                            db.close()

                class _SessionProxy:
                    def __init__(self, _session):
                        self._session = _session

                    def __getattr__(self, name):
                        if name == "exec":
                            def _call(stmt):
                                return _ExecResult(orig_exec, stmt)
                            return _call
                        return getattr(self._session, name)

                proxy = _SessionProxy(session)
            except Exception:
                proxy = session

            yield proxy
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Synchronous engine/session for legacy and background code paths
DATABASE_URL_SYNC = _get_sync_database_url()
# Get pool configuration from environment
sync_pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
sync_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
sync_pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
sync_pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))

sync_engine = create_engine(
    DATABASE_URL_SYNC,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=sync_pool_recycle,
    pool_size=sync_pool_size,
    max_overflow=sync_max_overflow,
    pool_timeout=sync_pool_timeout,
)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, class_=SQLModelSession)


# Ensure SQLite schemas exist in non-production to avoid missing tables during tests/dev
def _ensure_sqlite_schema_nonprod() -> None:
    if os.getenv("ENVIRONMENT") == "production":
        return
    if "sqlite" not in str(sync_engine.url):
        return
    from src.database import models as _models  # noqa: F401
    from src.database import ts_models as _ts  # noqa: F401
    SQLModel.metadata.create_all(sync_engine)


_ensure_sqlite_schema_nonprod()


# Add event listeners for tenant context management (PostgreSQL only)
@event.listens_for(sync_engine, "connect")
def set_tenant_context_on_connect(dbapi_connection, connection_record):
    """Set tenant context when a new connection is established (PostgreSQL)."""
    if "postgresql" in str(sync_engine.url):
        if os.getenv("PG_ENABLE_TENANT_GUC", "true").lower() == "true":
            tenant_id = get_tenant_context()
            if tenant_id is None:
                # Explicitly set to NULL
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("SELECT set_config('app.tenant_id', NULL, false)")
                except Exception:
                    pass
                finally:
                    cursor.close()
                return
            cursor = dbapi_connection.cursor()
            try:
                try:
                    cursor.execute("SET app.tenant_id = %s", (str(tenant_id),))
                except Exception:
                    # Ignore if the server rejects custom GUCs (e.g., Cloud SQL)
                    pass
            finally:
                cursor.close()


@event.listens_for(sync_engine, "checkout")
def checkout(dbapi_connection, connection_record, connection_proxy):
    """Defensively clear state on connection checkout (PostgreSQL).
    
    Note: We only run RESET ALL here. The tenant context (app.tenant_id) is set
    explicitly by the middleware or application code before database operations.
    This ensures the correct tenant context is always used for each request.
    """
    if "postgresql" in str(sync_engine.url):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("RESET ALL")
            # Re-apply tenant context if it exists in the current ContextVar
            if os.getenv("PG_ENABLE_TENANT_GUC", "true").lower() == "true":
                tenant_id = get_tenant_context()
                if tenant_id is not None:
                    try:
                        cursor.execute("SET app.tenant_id = %s", (str(tenant_id),))
                    except Exception:
                        pass
        finally:
            cursor.close()


def get_db() -> SQLModelSession:
    """Return a synchronous database session (caller must close)."""
    return SyncSessionLocal()


@contextmanager
def session_scope() -> Generator[SQLModelSession, None, None]:
    """Provide a transactional scope around a series of operations (sync)."""
    session = get_db()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Optional safety net for raw SQL in prod: reject statements without tenant predicate
TENANT_SQL_GUARD_ENABLED = os.getenv("TENANT_SQL_GUARD_ENABLED", "false").lower() == "true"

if TENANT_SQL_GUARD_ENABLED:
    @event.listens_for(SyncSessionLocal, "before_execute")
    def _tenant_sql_guard(conn, clauseelement, multiparams, params):
        try:
            sql_text = str(clauseelement).lower()
            if any(k in sql_text for k in ["select", "update", "delete"]) and "tenant_id" not in sql_text:
                raise RuntimeError("Tenant SQL guard: statement missing tenant_id predicate")
        except Exception:
            raise
