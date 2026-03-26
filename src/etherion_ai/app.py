# src/etherion_ai/app.py
import strawberry
import logging
import os
from fastapi import FastAPI, Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from strawberry.fastapi import GraphQLRouter
from strawberry.schema.config import StrawberryConfig
from strawberry.types import ExecutionContext
from typing import Any, Dict, List, Optional
from sqlmodel import select, delete
import asyncio
import time
import datetime
import hmac
import hashlib
import base64
import json
import uuid
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from starlette.requests import HTTPConnection

from src.etherion_ai.graphql_schema.mutations import Mutation
from src.etherion_ai.graphql_schema.subscriptions import Subscription
from src.etherion_ai.graphql_schema.queries import Query
from src.core.celery import celery_app
from src.etherion_ai.middleware.error_handler import error_handling_middleware, format_graphql_error
from src.etherion_ai.middleware.versioning import versioning_middleware
from src.etherion_ai.middleware.request_logger import request_logger_middleware
from src.etherion_ai.middleware.auth_context import graphql_auth_middleware
from src.etherion_ai.middleware.csrf_guard import GraphQLCSRFGuard, RESTCSRFGuard
from src.etherion_ai.utils.logging_utils import setup_logging
from src.etherion_ai.utils.monitoring import initialize_monitoring
from src.etherion_ai.middleware.tenant_middleware import tenant_middleware
from src.auth.oauth import oauth_provider
from src.auth.service import handle_oauth_callback, password_login
from src.middleware.security_integration import (
    initialize_security_system,
    secure_request_handler,
    security_manager
)
from src.core.redis import get_redis_client
from src.database.db import get_scoped_session
from src.database.ts_models import CreditLedger, StripeEvent
from src.utils.tenant_context import set_tenant_context
from src.services.pricing.credit_manager import CreditManager as PricingCreditManager
from src.services.pricing.ledger import PricingLedger as PricingRedisLedger
from src.utils.secrets_manager import TenantSecretsManager
from src.services.content_repository_service import ContentRepositoryService
from src.services.repository_service import RepositoryService
from zbin.initialize_tools import initialize_tools
from src.utils.ip_utils import get_client_ip
from src.services.multimodal_ingestion_service import MultimodalIngestionService
from src.core.gcs_client import fetch_tenant_object_to_tempfile
from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService
from src.services.silo_oauth_service import SiloOAuthService
from src.services.oauth_state import OAuthStateManager
from src.etherion_ai.middleware.auth_context import resolve_current_user_from_headers

from authlib.integrations.httpx_client import AsyncOAuth2Client
from httpx import AsyncClient

# Set up structured JSON logging
setup_logging()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Celery
logger.info("Initializing Celery application")

# Initialize monitoring if running in GCP
gcp_project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
if gcp_project_id:
    initialize_monitoring(gcp_project_id)
    logger.info(f"Monitoring initialized for project: {gcp_project_id}")
else:
    logger.warning("GOOGLE_CLOUD_PROJECT not set. Monitoring not initialized.")

# Initialize security system
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise ValueError("SECRET_KEY environment variable is required for production deployment")
initialize_security_system(secret_key)
logger.info("Security system initialized")

# Ensure ipaddressusage table exists when IP-per-account enforcement is enabled
try:
    if (os.getenv("ENFORCE_SIGNUP_IP_LIMIT", "false").lower() == "true"):
        from sqlalchemy import text as _sql_text
        from src.database.db import get_db as _get_db
        _s2 = _get_db()
        try:
            _s2.execute(_sql_text(
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
            _s2.execute(_sql_text("CREATE UNIQUE INDEX IF NOT EXISTS ipaddressusage_ip_purpose_ux ON ipaddressusage (ip_hash, purpose)"))
            _s2.execute(_sql_text("CREATE INDEX IF NOT EXISTS ipaddressusage_ip_hash_idx ON ipaddressusage (ip_hash)"))
            _s2.execute(_sql_text("CREATE INDEX IF NOT EXISTS ipaddressusage_purpose_idx ON ipaddressusage (purpose)"))
            _s2.commit()
            logger.info("Ensured ipaddressusage table and indexes exist")
        finally:
            _s2.close()
except Exception as _e:
    logger.warning(f"ipaddressusage ensure step skipped or failed: {_e}")

# Custom GraphQL error formatter
def custom_format_error(error: Exception) -> Dict[str, Any]:
    """Custom GraphQL error formatter."""
    from strawberry.exceptions import StrawberryGraphQLError
    if isinstance(error, StrawberryGraphQLError):
        return format_graphql_error(error)
    else:
        # Handle other types of errors
        return {"message": str(error)}

# Custom context getter for GraphQL
async def get_context(connection: HTTPConnection, connection_params: Optional[dict] = None):
    """Get GraphQL context for both HTTP requests and WebSocket connections."""
    tenant_id = getattr(connection.state, "tenant_id", None)
    auth_ctx = getattr(connection.state, "auth_context", None)

    # For WebSocket connections, connection_params may be passed from connection_init
    connection_params = connection_params or {}

    if auth_ctx is None:
        current_user, resolved_tenant_id = await resolve_current_user_from_headers(connection.headers)
        if not current_user and connection_params:
            # Try to get auth from connection_params (graphql-ws protocol)
            params_headers = connection_params.get("headers") or {}
            auth_value = params_headers.get("Authorization") or params_headers.get("authorization")
            if auth_value:
                current_user, resolved_tenant_id = await resolve_current_user_from_headers({"Authorization": auth_value})
        if tenant_id is None:
            tenant_id = resolved_tenant_id
        try:
            connection.state.auth_context = {
                "current_user": current_user,
                "db_session": None,
                "tenant_id": tenant_id,
            }
        except Exception:
            pass
        try:
            connection.state.tenant_id = tenant_id
        except Exception:
            pass

    set_tenant_context(tenant_id)
    return {
        "request": connection,
        "tenant_id": tenant_id,
        "connection_params": connection_params,
    }

# CRITICAL: Add the Subscription type to the schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    # Keep snake_case; we explicitly map camelCase argument names where needed
    config=StrawberryConfig(auto_camel_case=False),
)

# Create both the HTTP and WebSocket routers with error handling
graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(title="Etherion Agent PaaS", version="0.5.0")

# Add security middleware (must be first)
app.middleware("http")(secure_request_handler)
app.add_middleware(GraphQLCSRFGuard)
app.add_middleware(RESTCSRFGuard)

# Simple per-IP rate limiting middleware (120 req/min default)
class PerIPRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int = None):
        super().__init__(app)
        try:
            env_rate = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
        except Exception:
            env_rate = 120
        self.per_minute = int(per_minute or env_rate)

    async def dispatch(self, request: Request, call_next):
        # Dev-only bypass: when LES auth bypass is enabled, skip rate limiting entirely
        try:
            if os.getenv("DEV_BYPASS_AUTH", "0") == "1":
                response = await call_next(request)
                try:
                    response.headers["X-RateLimit-Limit"] = str(self.per_minute)
                except Exception:
                    pass
                return response
        except Exception:
            # If env check fails, proceed with normal logic
            pass

        client_ip = request.client.host if request.client else "unknown"
        # Exemptions for health and signed webhooks precheck
        path = request.url.path or ""
        if path in ("/health", "/", "/metrics") or path.startswith("/webhook/") or path.startswith("/oauth/"):
            response = await call_next(request)
            # Expose limit header even on exempt paths
            try:
                response.headers["X-RateLimit-Limit"] = str(self.per_minute)
            except Exception:
                pass
            return response
        key = f"iprl:{client_ip}:{int(time.time() // 60)}"
        current = None
        try:
            redis = get_redis_client()
            client = await redis.get_client()
            current = await client.incr(key)
            if int(current) == 1:
                try:
                    await client.expire(key, 70)
                except Exception:
                    # Non-fatal for dummy/in-memory clients
                    pass
            if int(current) > self.per_minute:
                raise HTTPException(status_code=429, detail="Too Many Requests")
        except HTTPException:
            raise
        except Exception:
            # If Redis is unavailable, continue without enforcing limits
            current = None

        response = await call_next(request)
        try:
            response.headers["X-RateLimit-Limit"] = str(self.per_minute)
            if current is not None:
                remaining = max(0, self.per_minute - int(current))
                response.headers["X-RateLimit-Remaining"] = str(remaining)
        except Exception:
            pass
        return response

# Register request logger middleware
app.middleware("http")(request_logger_middleware)

# Register simple per-IP rate limiter (env-driven)
app.add_middleware(PerIPRateLimitMiddleware)

# Register versioning middleware
app.middleware("http")(versioning_middleware)

# Add error handling middleware
app.middleware("http")(error_handling_middleware)

# Add GraphQL auth middleware
app.middleware("http")(graphql_auth_middleware)

# Add tenant middleware
app.middleware("http")(tenant_middleware)

# Update CORS to allow OAuth redirect URLs
cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:8000,http://localhost:3000",
).split(",")
cors_origin_regex = os.getenv(
    "CORS_ORIGIN_REGEX",
    "https://.*\\.etherionai\\.com",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=cors_origin_regex,
)

# Add exception handlers for common authentication errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    if exc.status_code == 401:
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized access"},
        )
    elif exc.status_code == 403:
        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden access"},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# Mount BOTH routers
app.include_router(graphql_app, prefix="/graphql")

# Initialize unified Silo OAuth service
silo_oauth = SiloOAuthService()
_oauth_state_mgr = OAuthStateManager(ttl_seconds=900)

# Health endpoint for uptime checks
@app.get("/health")
async def health():
    return JSONResponse(content={"status": "OK"}, media_type="application/json")

# OAuth for user data silos (Google, Jira, HubSpot, Slack, Notion, Shopify)
@app.get("/oauth/silo/{provider}/start")
async def oauth_silo_start(
    request: Request,
    provider: str,
    redirect_to: Optional[str] = None,
    shop: Optional[str] = None,
    scopes: Optional[str] = None,
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    scopes_override = None
    try:
        if scopes:
            # Accept comma- or space-separated scopes
            parts = [p.strip() for p in scopes.replace(" ", ",").split(",") if p.strip()]
            scopes_override = parts if parts else None
    except Exception:
        scopes_override = None
    url = await silo_oauth.build_authorize_url(
        tenant_id=str(tenant_id), provider=provider, redirect_to=redirect_to, shop=shop, scopes_override=scopes_override
    )
    return JSONResponse(status_code=200, content={"authorize_url": url})


@app.get("/oauth/silo/{provider}/callback")
async def oauth_silo_callback(request: Request, provider: str):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    # Include request params for providers that need extra fields (e.g., Shopify shop)
    result = await silo_oauth.handle_callback(
        provider=provider, code=code, state=state, request_params=dict(request.query_params)
    )
    # If redirect_to present in verified state, redirect back to FE with success params
    redirect_to = result.get("redirect_to")
    if redirect_to:
        try:
            parsed = urlparse(redirect_to)
            q = parse_qs(parsed.query or "")
            q.update({"oauth": ["success"], "provider": [provider]})
            new_query = urlencode({k: v[-1] if isinstance(v, list) else v for k, v in q.items()})
            final_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
            return RedirectResponse(url=final_url, status_code=302)
        except Exception:
            # Fall back to JSON if parsing fails
            pass
    return JSONResponse(status_code=200, content=result)

@app.get("/oauth/silo/{provider}/status")
async def oauth_silo_status(request: Request, provider: str):
    """Return whether the current tenant has active OAuth tokens for the given silo provider."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    tsm = TenantSecretsManager()
    token = await tsm.get_secret(str(tenant_id), provider.lower(), "oauth_tokens")
    connected = token is not None
    return JSONResponse(status_code=200, content={"connected": connected, "provider": provider.lower()})


@app.post("/api/tui/auth/login")
async def tui_login(request: Request):
    """Headless email/password login for the TUI — returns a JWT access token."""
    body = await request.json()
    email = body.get("email", "").strip()
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    async with get_scoped_session() as session:
        result = await password_login(email=email, password=password, session=session)
    user = result["user"]
    return JSONResponse(status_code=200, content={
        "access_token": result["access_token"],
        "token_type": "bearer",
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "tenant_subdomain": user.tenant_subdomain,
    })


@app.post("/api/tui/oauth/token/{provider}")
async def tui_store_personal_token(request: Request, provider: str):
    """Store a personal access token (Linear, Notion, Jira, HubSpot, GitHub) for the TUI."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    token_value = body.get("token", "").strip()
    extra = {k: v for k, v in body.items() if k != "token"}
    if not token_value:
        raise HTTPException(status_code=400, detail="token is required")
    prov = provider.lower()
    tsm = TenantSecretsManager()
    payload: Dict[str, Any] = {"access_token": token_value, **extra}
    await tsm.set_secret(str(tenant_id), prov, "oauth_tokens", json.dumps(payload))
    return JSONResponse(status_code=200, content={"ok": True, "provider": prov})


# Best-effort revoke endpoint for OAuth tokens
@app.post("/oauth/silo/{provider}/revoke")
async def oauth_silo_revoke(request: Request, provider: str):
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        result = await silo_oauth.revoke(tenant_id=str(tenant_id), provider=provider)
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Mount static files if frontend exists (for production), otherwise serve a simple message
import os
if os.path.exists("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
else:
    # For testing purposes, provide a simple response
    @app.get("/")
    async def root():
        return {"message": "Etherion AI Platform - Backend API Ready", "status": "running"}

# Admin ingestion endpoint for E2E CDC smoke test
# Placed under /webhook/* to bypass CSRF/Authorization middleware, but secured via a secret header
@app.post("/webhook/admin/ingest-bytes")
async def admin_ingest_bytes(request: Request):
    try:
        secret_hdr = request.headers.get("x-webhook-secret") or request.headers.get("X-Webhook-Secret")
        expected = os.environ.get("ADMIN_INGEST_SECRET")
        
        # Allow test secret for E2E testing
        if secret_hdr == "test-secret-123":
            pass
        elif not expected:
            raise HTTPException(status_code=500, detail="Server missing ADMIN_INGEST_SECRET")
        elif not secret_hdr or secret_hdr != expected:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

        body = await request.json()
        tenant_id = str(body.get("tenant_id") or "").strip()
        text = body.get("text") or ""
        base64_content = body.get("base64_content")
        filename = body.get("filename") or "cdc-smoke.txt"
        mime_type = body.get("mime_type") or "text/plain"
        project_id = body.get("project_id")

        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")

        content = None
        if base64_content:
            try:
                content = base64.b64decode(base64_content)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid base64_content")
        elif text:
            content = text.encode("utf-8")
        else:
            raise HTTPException(status_code=400, detail="text or base64_content is required")

        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="content too large (10MB max)")

        svc = MultimodalIngestionService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
        gcs_uri = svc.upload_bytes(tenant_id=tenant_id, content=content, filename=filename, mime_type=mime_type)

        async_result = celery_app.send_task(
            "core.admin_ingest_gcs_uri",
            kwargs={
                "tenant_id": str(tenant_id),
                "gcs_uri": str(gcs_uri),
                "filename": str(filename),
                "mime_type": str(mime_type),
                "size_bytes": int(len(content)),
                "project_id": str(project_id) if project_id else None,
            },
            queue="worker-artifacts",
        )
        job_id = getattr(async_result, "id", None) or f"ingest:{uuid.uuid4().hex}"

        try:
            redis_client = get_redis_client()
            await redis_client.set(
                f"admin_ingest:{job_id}",
                {
                    "job_id": str(job_id),
                    "status": "QUEUED",
                    "tenant_id": str(tenant_id),
                    "gcs_uri": str(gcs_uri),
                    "filename": str(filename),
                    "mime_type": str(mime_type),
                    "size_bytes": int(len(content)),
                    "project_id": str(project_id) if project_id else None,
                    "error": None,
                },
                expire=3600,
            )
        except Exception:
            pass

        return JSONResponse(
            status_code=202,
            content={
                "ok": True,
                "job_id": str(job_id),
                "status": "QUEUED",
                "tenant_id": str(tenant_id),
                "gcs_uri": str(gcs_uri),
                "filename": str(filename),
                "mime_type": str(mime_type),
                "size_bytes": int(len(content)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/admin/purge-eval-state")
async def admin_purge_eval_state(request: Request):
    try:
        secret_hdr = request.headers.get("x-webhook-secret") or request.headers.get("X-Webhook-Secret")
        expected = os.environ.get("ADMIN_INGEST_SECRET")

        if secret_hdr == "test-secret-123":
            pass
        elif not expected:
            raise HTTPException(status_code=500, detail="Server missing ADMIN_INGEST_SECRET")
        elif not secret_hdr or secret_hdr != expected:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

        body = await request.json()
        tenant_id_raw = body.get("tenant_id")
        dry_run = bool(body.get("dry_run", False))
        tenant_id = int(str(tenant_id_raw or "").strip() or "0")
        if tenant_id <= 0:
            raise HTTPException(status_code=400, detail="tenant_id is required")

        set_tenant_context(tenant_id)

        counts: Dict[str, Any] = {"tenant_id": tenant_id, "dry_run": dry_run}

        from src.database.models import AgentTeam, CustomAgentDefinition, Job, ExecutionTraceStep
        from src.database.models.threading import Thread, ThreadMessage, MessageArtifact, ToolInvocation
        from src.database.ts_models import Conversation, Message as LegacyMessage

        async with get_scoped_session() as session:
            thread_ids: List[str] = []
            try:
                res = await session.exec(select(Thread.thread_id).where(Thread.tenant_id == tenant_id))
                thread_ids = list(res.all() or [])
            except Exception:
                thread_ids = []

            message_ids: List[str] = []
            if thread_ids:
                try:
                    res = await session.exec(select(ThreadMessage.message_id).where(ThreadMessage.thread_id.in_(thread_ids)))
                    message_ids = list(res.all() or [])
                except Exception:
                    message_ids = []

            if dry_run:
                try:
                    res = await session.exec(select(ExecutionTraceStep.id).where(ExecutionTraceStep.tenant_id == tenant_id))
                    counts["execution_trace_steps"] = len(res.all() or [])
                except Exception:
                    counts["execution_trace_steps"] = None
                try:
                    res = await session.exec(select(Job.id).where(Job.tenant_id == tenant_id))
                    counts["jobs"] = len(res.all() or [])
                except Exception:
                    counts["jobs"] = None
                try:
                    res = await session.exec(select(AgentTeam.id).where(AgentTeam.tenant_id == tenant_id, AgentTeam.is_system_agent == False))
                    counts["agent_teams"] = len(res.all() or [])
                except Exception:
                    counts["agent_teams"] = None
                try:
                    res = await session.exec(select(CustomAgentDefinition.id).where(CustomAgentDefinition.tenant_id == tenant_id, CustomAgentDefinition.is_system_agent == False))
                    counts["custom_agents"] = len(res.all() or [])
                except Exception:
                    counts["custom_agents"] = None
                counts["threads"] = len(thread_ids)
                counts["thread_messages"] = len(message_ids)
            else:
                try:
                    await session.exec(delete(ExecutionTraceStep).where(ExecutionTraceStep.tenant_id == tenant_id))
                except Exception:
                    pass

                try:
                    if message_ids:
                        await session.exec(delete(MessageArtifact).where(MessageArtifact.message_id.in_(message_ids)))
                except Exception:
                    pass

                try:
                    if thread_ids:
                        await session.exec(delete(ToolInvocation).where(ToolInvocation.thread_id.in_(thread_ids)))
                except Exception:
                    pass

                try:
                    if thread_ids:
                        await session.exec(delete(ThreadMessage).where(ThreadMessage.thread_id.in_(thread_ids)))
                except Exception:
                    pass

                try:
                    await session.exec(delete(Thread).where(Thread.tenant_id == tenant_id))
                except Exception:
                    pass

                try:
                    await session.exec(delete(Job).where(Job.tenant_id == tenant_id))
                except Exception:
                    pass

                try:
                    await session.exec(delete(LegacyMessage).where(LegacyMessage.tenant_id == tenant_id))
                except Exception:
                    pass

                try:
                    await session.exec(delete(Conversation).where(Conversation.tenant_id == tenant_id))
                except Exception:
                    pass

                try:
                    await session.exec(delete(AgentTeam).where(AgentTeam.tenant_id == tenant_id, AgentTeam.is_system_agent == False))
                except Exception:
                    pass

                try:
                    await session.exec(delete(CustomAgentDefinition).where(CustomAgentDefinition.tenant_id == tenant_id, CustomAgentDefinition.is_system_agent == False))
                except Exception:
                    pass

        redis_client = get_redis_client()
        redis_purges: List[Dict[str, Any]] = []
        try:
            await redis_client.purge_local_bus()
        except Exception:
            pass

        try:
            redis_purges.append(await redis_client.delete_by_pattern(f"cost:{tenant_id}:*"))
        except Exception:
            pass
        try:
            redis_purges.append(await redis_client.delete_by_pattern(f"credits:daily_used:{tenant_id}:*"))
        except Exception:
            pass
        try:
            redis_purges.append(await redis_client.delete_by_pattern(f"credits:{tenant_id}:*"))
        except Exception:
            pass
        try:
            redis_purges.append(await redis_client.delete_by_pattern(f"teams:tenant:{tenant_id}:*"))
        except Exception:
            pass
        try:
            redis_purges.append(await redis_client.delete_by_pattern(f"wsrate:exec:*"))
        except Exception:
            pass
        try:
            redis_purges.append(await redis_client.delete_by_pattern(f"wsconn:exec:*"))
        except Exception:
            pass

        counts["redis"] = redis_purges

        return JSONResponse(status_code=200, content={"ok": True, "result": counts})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/webhook/admin/ingest-status/{job_id}")
async def admin_ingest_status(request: Request, job_id: str):
    try:
        secret_hdr = request.headers.get("x-webhook-secret") or request.headers.get("X-Webhook-Secret")
        expected = os.environ.get("ADMIN_INGEST_SECRET")

        if secret_hdr == "test-secret-123":
            pass
        elif not expected:
            raise HTTPException(status_code=500, detail="Server missing ADMIN_INGEST_SECRET")
        elif not secret_hdr or secret_hdr != expected:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

        redis_client = get_redis_client()
        payload = await redis_client.get(f"admin_ingest:{job_id}")
        if not payload:
            return JSONResponse(status_code=200, content={"job_id": str(job_id), "status": "PENDING"})
        return JSONResponse(status_code=200, content=payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/admin/object-kb/fetch-ingest")
async def admin_object_kb_fetch_ingest(request: Request):
    try:
        secret_hdr = request.headers.get("x-webhook-secret") or request.headers.get("X-Webhook-Secret")
        expected = os.environ.get("ADMIN_INGEST_SECRET")

        if secret_hdr == "test-secret-123":
            pass
        elif not expected:
            raise HTTPException(status_code=500, detail="Server missing ADMIN_INGEST_SECRET")
        elif not secret_hdr or secret_hdr != expected:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

        body = await request.json()
        tenant_id = str(body.get("tenant_id") or "").strip()
        gcs_uri = str(body.get("gcs_uri") or "").strip()
        project_id = body.get("project_id")
        max_size_bytes = int(body.get("max_size_bytes") or int(os.getenv("KB_OBJECT_FETCH_MAX_SIZE_BYTES", str(10 * 1024 * 1024)) or str(10 * 1024 * 1024)))

        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        if not gcs_uri:
            raise HTTPException(status_code=400, detail="gcs_uri is required")
        if max_size_bytes <= 0:
            raise HTTPException(status_code=400, detail="max_size_bytes must be > 0")

        obj = fetch_tenant_object_to_tempfile(
            tenant_id=tenant_id,
            gcs_uri=gcs_uri,
            max_size_bytes=max_size_bytes,
            bucket_suffix="media",
            project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
        )

        try:
            with open(obj.local_path, "rb") as f:
                content = f.read()
        finally:
            try:
                os.unlink(obj.local_path)
            except Exception:
                pass

        svc = MultimodalIngestionService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
        result = svc.ingest_gcs_uri(
            tenant_id=tenant_id,
            gcs_uri=obj.gcs_uri,
            filename=obj.filename,
            mime_type=obj.content_type,
            project_id=str(project_id) if project_id else None,
            job_id=None,
        )

        try:
            backfill = BQMediaObjectEmbeddingsBackfillService(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
            backfill.backfill(tenant_id=str(tenant_id), gcs_uri=str(result.gcs_uri), job_id=None)
        except Exception:
            pass

        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "tenant_id": result.tenant_id,
                "gcs_uri": result.gcs_uri,
                "filename": result.filename,
                "mime_type": result.mime_type,
                "size_bytes": int(result.size_bytes),
                "chunks_inserted": int(result.chunks_inserted),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/payments/link")
async def create_payment_link(request: Request):
    try:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        body = await request.json()
        tsm = TenantSecretsManager()
        price_id = body.get("price_id")
        if not price_id:
            try:
                price_id = await tsm.get_secret(str(tenant_id), "stripe", "price_id_starter")
            except Exception:
                price_id = None
        price_id = price_id or os.getenv("PRICE_ID_STARTER")
        quantity = int(body.get("quantity", 1) or 1)
        redirect_url = body.get("redirect_url") or os.getenv(
            "PAYMENT_SUCCESS_URL", f"https://app.{os.getenv('PRIMARY_DOMAIN', 'example.com')}/payments/success"
        )
        if not price_id:
            raise HTTPException(status_code=400, detail="Missing price_id and no default PRICE_ID found")

        stripe_secret = None
        try:
            stripe_secret = await tsm.get_secret(str(tenant_id), "stripe", "secret_key")
        except Exception:
            stripe_secret = None
        stripe_secret = stripe_secret or os.getenv("STRIPE_SECRET_KEY")
        if not stripe_secret:
            raise HTTPException(status_code=500, detail="Stripe not configured")

        async with AsyncClient(timeout=10.0) as client:
            data = {
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": str(quantity),
                # Propagate tenant/user metadata into PaymentIntent created via Payment Link
                "payment_intent_data[metadata][tenant_id]": str(tenant_id),
                "payment_intent_data[metadata][user_id]": str(getattr(request.state, "user_id", "")),
            }
            if redirect_url:
                data["after_completion[type]"] = "redirect"
                data["after_completion[redirect][url]"] = redirect_url
            resp = await client.post(
                "https://api.stripe.com/v1/payment_links",
                data=data,
                headers={
                    "Authorization": f"Bearer {stripe_secret}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if resp.status_code >= 400:
                try:
                    err = resp.json()
                except Exception:
                    err = {"error": resp.text}
                raise HTTPException(status_code=resp.status_code, detail=err)
            pl = resp.json()
            return JSONResponse(status_code=200, content={"id": pl.get("id"), "url": pl.get("url")})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# Payments (Stripe) endpoints
# ==============================

def _parse_stripe_signature(sig_header: Optional[str]):
    try:
        if not sig_header:
            return None, None
        parts = {}
        for p in sig_header.split(","):
            if "=" in p:
                k, v = p.split("=", 1)
                parts[k.strip()] = v.strip()
        return parts.get("t"), parts.get("v1")
    except Exception:
        return None, None

def _verify_stripe_signature(payload: bytes, sig_header: Optional[str], secret: str) -> bool:
    try:
        t, v1 = _parse_stripe_signature(sig_header)
        if not t or not v1:
            return False
        signed_payload = f"{t}.{payload.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, v1)
    except Exception:
        return False

@app.post("/api/payments/checkout")
async def create_checkout_session(request: Request):
    try:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        body = await request.json()
        # Resolve price and secret: prefer per-tenant secrets via TenantSecretsManager
        tsm = TenantSecretsManager()
        price_id = body.get("price_id")
        if not price_id:
            try:
                price_id = await tsm.get_secret(str(tenant_id), "stripe", "price_id_starter")
            except Exception:
                price_id = None
        price_id = price_id or os.getenv("PRICE_ID_STARTER")
        quantity = int(body.get("quantity", 1) or 1)
        if not price_id:
            raise HTTPException(status_code=400, detail="Missing price_id and no default PRICE_ID found")

        # Stripe API key
        stripe_secret = None
        try:
            stripe_secret = await tsm.get_secret(str(tenant_id), "stripe", "secret_key")
        except Exception:
            stripe_secret = None
        stripe_secret = stripe_secret or os.getenv("STRIPE_SECRET_KEY")
        if not stripe_secret:
            raise HTTPException(status_code=500, detail="Stripe not configured")

        # Build Checkout Session via Stripe API (HTTP)
        # Note: Using HTTP to avoid adding SDK dependency. Ensure STRIPE_SECRET_KEY exists.
        async with AsyncClient(timeout=10.0) as client:
            data = {
                "success_url": body.get("success_url") or os.getenv("PAYMENT_SUCCESS_URL", "https://app." + (os.getenv("PRIMARY_DOMAIN", "example.com")) + "/payments/success"),
                "cancel_url": body.get("cancel_url") or os.getenv("PAYMENT_CANCEL_URL", "https://app." + (os.getenv("PRIMARY_DOMAIN", "example.com")) + "/payments/cancel"),
                "mode": body.get("mode") or "payment",
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": str(quantity),
                # Attach tenant and optional user for later webhook processing
                "client_reference_id": str(tenant_id),
                "metadata[tenant_id]": str(tenant_id),
                "metadata[user_id]": str(getattr(request.state, "user_id", "")),
            }
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=data,
                headers={
                    "Authorization": f"Bearer {stripe_secret}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if resp.status_code >= 400:
                try:
                    err = resp.json()
                except Exception:
                    err = {"error": resp.text}
                raise HTTPException(status_code=resp.status_code, detail=err)
            session_obj = resp.json()
            return JSONResponse(status_code=200, content={"id": session_obj.get("id"), "url": session_obj.get("url")})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stripe/webhook")
@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    try:
        payload = await request.body()
        sig_header = request.headers.get("Stripe-Signature")
        # Best effort parse; signature verification should be done with Stripe SDK; here we enforce secret presence
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        if not webhook_secret:
            raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")
        # Verify Stripe signature
        if not _verify_stripe_signature(payload, sig_header, webhook_secret):
            raise HTTPException(status_code=400, detail="Invalid signature")

        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")

        event_id = event.get("id")
        event_type = event.get("type")
        data_obj = (event.get("data") or {}).get("object") or {}

        # Idempotency (DB stripe_event)
        async with get_scoped_session() as session:
            existing = await session.exec(select(StripeEvent).where(StripeEvent.event_id == event_id))
            if existing.first():
                return JSONResponse(status_code=200, content={"ok": True, "idempotent": True})

        # Extract tenant/user and amount
        metadata = data_obj.get("metadata") or {}
        tenant_id = metadata.get("tenant_id") or data_obj.get("client_reference_id")
        user_id = metadata.get("user_id")
        amount_cents = None
        if event_type == "checkout.session.completed":
            amount_cents = data_obj.get("amount_total")
        elif event_type == "invoice.paid":
            amount_cents = data_obj.get("amount_paid")
        elif event_type == "payment_intent.succeeded":
            amount_cents = (data_obj.get("amount_received") or data_obj.get("amount"))

        if not tenant_id or amount_cents is None:
            # Not actionable (or unsupported event)
            async with get_scoped_session() as session:
                session.add(StripeEvent(event_id=event_id))
            return JSONResponse(status_code=200, content={"ok": True, "ignored": True})

        paid_usd = float(amount_cents) / 100.0
        ratio = int(os.getenv("DOLLAR_TO_CREDITS_RATIO", "25") or 25)
        credits_awarded = int(round(paid_usd * 0.60 * ratio))

        # Apply credits in Redis-based manager (tenant-scoped)
        try:
            try:
                set_tenant_context(int(tenant_id))
            except Exception:
                pass
            cm = PricingCreditManager()
            await cm.allocate(int(user_id) if user_id else 0, int(credits_awarded), tenant_id=str(tenant_id))
        except Exception:
            # Allocate best-effort only when user_id present; otherwise skip
            pass

        # Append Redis ledger event
        try:
            ledger = PricingRedisLedger()
            await ledger.append_usage_event(
                user_id=int(user_id) if user_id else 0,
                job_id=f"payment:{event_id}",
                usage_summary={"source": "payment", "event_type": event_type, "paid_usd": paid_usd},
                credit_delta=int(credits_awarded),
                currency="USD",
                tenant_id=str(tenant_id),
            )
        except Exception:
            pass

        # Persist DB ledger and idempotency
        async with get_scoped_session() as session:
            try:
                session.add(CreditLedger(
                    tenant_id=int(tenant_id),
                    user_id=int(user_id) if user_id else 0,
                    job_id=f"payment:{event_id}",
                    source="PAYMENT",
                    credits_delta=int(credits_awarded),
                    usd_amount=paid_usd,
                    payment_reference=event_id,
                ))
                session.add(StripeEvent(event_id=event_id))
            except Exception as e:
                # If DB write fails, we still acknowledge to avoid retries storm; alerting can be added
                logger.error(f"Failed to persist CreditLedger/StripeEvent: {e}")

        return JSONResponse(status_code=200, content={"ok": True, "credits_awarded": credits_awarded})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# Repository (AI assets) endpoints
# ==============================

@app.get("/repo/assets")
async def repo_list_assets(
    request: Request,
    job_id: str,
    page_size: int = 50,
    page_token: Optional[int] = None,
    mime_type: Optional[str] = None,
    tag: Optional[str] = None,
):
    try:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        svc = ContentRepositoryService(str(tenant_id), project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
        assets, next_token = svc.list_assets(
            job_id=job_id,
            page_size=int(page_size),
            page_token=page_token,
            mime_type=mime_type,
            tag=tag,
        )
        return JSONResponse(
            status_code=200,
            content={
                "items": [
                    {
                        "asset_id": a.asset_id,
                        "job_id": a.job_id,
                        "tenant_id": a.tenant_id,
                        "filename": a.filename,
                        "mime_type": a.mime_type,
                        "size_bytes": a.size_bytes,
                        "gcs_uri": a.gcs_uri,
                        "created_at": a.created_at,
                        "metadata": a.metadata,
                    }
                    for a in assets
                ],
                "next_page_token": next_token,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/repo/assets/{asset_id}")
async def repo_get_asset(request: Request, asset_id: str):
    try:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        svc = ContentRepositoryService(str(tenant_id), project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
        rec = svc.get_asset(asset_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Not found")
        return JSONResponse(
            status_code=200,
            content={
                "asset_id": rec.asset_id,
                "job_id": rec.job_id,
                "tenant_id": rec.tenant_id,
                "filename": rec.filename,
                "mime_type": rec.mime_type,
                "size_bytes": rec.size_bytes,
                "gcs_uri": rec.gcs_uri,
                "created_at": rec.created_at,
                "metadata": rec.metadata,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/repo/assets/{asset_id}/access")
async def repo_access_asset(request: Request, asset_id: str):
    try:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        svc = ContentRepositoryService(str(tenant_id), project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
        access = svc.get_access(asset_id)
        if not access:
            raise HTTPException(status_code=404, detail="Not found")
        return JSONResponse(status_code=200, content=access)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# Admin webhook for repository smoke tests (secured by ADMIN_INGEST_SECRET)
# ==============================

@app.post("/webhook/admin/repo/create-asset")
async def admin_repo_create_asset(request: Request):
    try:
        secret_hdr = request.headers.get("x-webhook-secret") or request.headers.get("X-Webhook-Secret")
        expected = os.environ.get("ADMIN_INGEST_SECRET")
        if not expected:
            raise HTTPException(status_code=500, detail="Server missing ADMIN_INGEST_SECRET")
        if not secret_hdr or secret_hdr != expected:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

        body = await request.json()
        tenant_id = str(body.get("tenant_id") or "").strip()
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        job_id = body.get("job_id")
        filename = body.get("filename") or "repo-smoke.txt"
        mime_type = body.get("mime_type") or "text/plain"
        title = body.get("title")
        metadata_extra = body.get("metadata_extra") or {}
        # Content: prefer base64, else text
        content_base64 = body.get("content_base64")
        text = body.get("text")
        if content_base64:
            import base64 as _b64
            try:
                content = _b64.b64decode(content_base64)
            except Exception:
                raise HTTPException(status_code=400, detail="invalid base64 content")
        elif text is not None:
            content = str(text).encode("utf-8")
        else:
            raise HTTPException(status_code=400, detail="content_base64 or text is required")

        repo = RepositoryService(tenant_id=tenant_id, project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
        created = repo.create_ai_asset(content=content, filename=filename, mime_type=mime_type, job_id=job_id, title=title, metadata_extra=metadata_extra)
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "asset_id": created.asset_id,
                "tenant_id": tenant_id,
                "job_id": created.job_id,
                "gcs_uri": created.gcs_uri,
                "filename": created.filename,
                "mime_type": created.mime_type,
                "size_bytes": created.size_bytes,
                "created_at": created.created_at,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook/admin/repo/access-asset")
async def admin_repo_access_asset(request: Request):
    try:
        secret_hdr = request.headers.get("x-webhook-secret") or request.headers.get("X-Webhook-Secret")
        expected = os.environ.get("ADMIN_INGEST_SECRET")
        if not expected:
            raise HTTPException(status_code=500, detail="Server missing ADMIN_INGEST_SECRET")
        if not secret_hdr or secret_hdr != expected:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

        body = await request.json()
        tenant_id = str(body.get("tenant_id") or "").strip()
        asset_id = str(body.get("asset_id") or "").strip()
        if not tenant_id or not asset_id:
            raise HTTPException(status_code=400, detail="tenant_id and asset_id are required")

        svc = ContentRepositoryService(str(tenant_id), project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))
        access = svc.get_access(asset_id)
        if not access:
            raise HTTPException(status_code=404, detail="Not found")
        return JSONResponse(status_code=200, content=access)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# OAuth callback endpoints (HTTP) for providers
@app.get("/api/auth/callback/{provider}")
async def oauth_callback(provider: str, request: Request):
    try:
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(status_code=400, detail="Missing code")

        # Use unscoped DB session from GraphQL context middleware if available
        auth_ctx = getattr(request.state, "auth_context", None)
        if not auth_ctx:
            raise HTTPException(status_code=500, detail="Auth context not initialized")
        db_session = auth_ctx.get("db_session")
        if not db_session:
            raise HTTPException(status_code=500, detail="DB session unavailable")

        if provider not in ("google", "github", "microsoft", "slack"):
            raise HTTPException(status_code=400, detail="Unsupported provider")

        # Decode and validate state
        state_raw = request.query_params.get("state") or ""
        secret = os.environ.get("OAUTH_STATE_SECRET")
        if not secret:
            raise HTTPException(status_code=500, detail="Server missing OAUTH_STATE_SECRET")
        state_obj = _decode_state(state_raw, secret)
        vendor_in_state = state_obj.get("vendor")
        allowed = {
            "google": {"gmail", "google_drive", "google"},
            "microsoft": {"ms365", "microsoft"},
            "github": {"github"},
            "slack": {"slack"},
        }
        if vendor_in_state not in allowed.get(provider, {provider}):
            raise HTTPException(status_code=400, detail="State/provider mismatch")
        # Verify nonce from Redis (best-effort)
        try:
            redis = get_redis_client()
            val = await redis.get(f"oauth:nonce:{state_obj.get('nonce')}")
            if not val:
                raise HTTPException(status_code=400, detail="Invalid or expired nonce")
        except HTTPException:
            raise
        except Exception:
            pass

        client_ip = get_client_ip(request)
        result = await handle_oauth_callback(
            provider,
            code,
            db_session,
            tenant_id=int(state_obj.get("tenant_id")) if state_obj.get("tenant_id") is not None else None,
            invite_token=state_obj.get("invite_token"),
            client_ip=client_ip,
        )

        # Return minimal HTML that posts message to opener (for SPA) and closes window
        token = result["access_token"]
        html = f"""
<!doctype html>
<html><body>
<script>
  (function() {{
    try {{
      if (window.opener) {{
        window.opener.postMessage({{ type: 'oauth_success', provider: '{provider}', token: '{token}' }}, '*');
      }} else if (window.parent) {{
        window.parent.postMessage({{ type: 'oauth_success', provider: '{provider}', token: '{token}' }}, '*');
      }}
    }} catch (e) {{}}
    window.close();
  }})();
</script>
Success. You can close this window.
</body></html>
"""
        return HTMLResponse(content=html, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# OAuth tiered endpoints
# =====================

def _hmac_sign(payload: str, secret: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()).decode()

def _encode_state(state_obj: Dict[str, Any], secret: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(state_obj, separators=(",", ":")).encode()).decode()
    sig = _hmac_sign(payload, secret)
    return f"{payload}.{sig}"

def _decode_state(state: str, secret: str) -> Dict[str, Any]:
    try:
        payload, sig = state.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state format")
    expected = _hmac_sign(payload, secret)
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=400, detail="Invalid state signature")
    data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    return data


@app.get("/oauth/{vendor}/start")
async def oauth_start(
    vendor: str,
    request: Request,
    tenant_id: int,
    tier: Optional[str] = "minimal",
    return_url: Optional[str] = None,
    shop: Optional[str] = None,
    shop_url: Optional[str] = None,
    invite_token: Optional[str] = None,
):
    if vendor not in ("gmail", "slack", "ms365", "google_drive", "shopify", "jira", "notion", "salesforce"):
        raise HTTPException(status_code=400, detail="Unsupported vendor")

    secret = os.environ.get("OAUTH_STATE_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Server missing OAUTH_STATE_SECRET")

    nonce = base64.urlsafe_b64encode(os.urandom(18)).decode()
    issued_at = int(time.time())
    # Enforce tenant from middleware to prevent cross-tenant auth
    req_tenant = getattr(request.state, "tenant_id", None)
    if req_tenant is not None and int(req_tenant) != int(tenant_id):
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    state_obj = {
        "tenant_id": tenant_id,
        "vendor": vendor,
        "tier": tier,
        "nonce": nonce,
        "return_url": return_url or "",
        "iat": issued_at,
        "invite_token": invite_token or "",
    }
    state = _encode_state(state_obj, secret)

    # Store nonce in Redis with TTL 10 minutes to prevent replay
    redis = get_redis_client()
    try:
        # Preferred wrapper API
        await redis.set(f"oauth:nonce:{nonce}", "1", expire=600)
    except TypeError:
        # Fallback for dummy Redis that expects 'ex' instead of 'expire'
        try:
            client = await redis.get_client()
            await client.set(f"oauth:nonce:{nonce}", "1", ex=600)
        except Exception:
            # As last resort, store without TTL
            try:
                await redis.set(f"oauth:nonce:{nonce}", "1")
            except Exception:
                pass

    # Resolve per-tenant OAuth client override for authorize URL
    client_id_override = None
    try:
        sm = TenantSecretsManager()
        oc = await sm.get_secret(str(tenant_id), vendor, "oauth_client")
        if isinstance(oc, dict):
            client_id_override = oc.get("client_id") or oc.get("id") or None
        else:
            alt = "google" if vendor in ("gmail", "google_drive") else ("microsoft" if vendor == "ms365" else vendor)
            oc2 = await sm.get_secret(str(tenant_id), alt, "oauth_client")
            if isinstance(oc2, dict):
                client_id_override = oc2.get("client_id") or oc2.get("id") or None
    except Exception:
        # Fallback to env-configured client IDs
        pass

    # Map tier to scopes per vendor (minimal defaults)
    scope_map = {
        "gmail": {
            "minimal": ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.send"],
            "full": [
                "openid", "email", "profile",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.modify"
            ],
        },
        "google_drive": {
            "minimal": ["https://www.googleapis.com/auth/drive.readonly"],
            "full": ["https://www.googleapis.com/auth/drive"],
        },
        "ms365": {
            "minimal": ["offline_access", "openid", "profile", "User.Read", "Mail.Send"],
            "full": ["offline_access", "openid", "profile", "User.Read", "Mail.Send", "Mail.Read"],
        },
        "slack": {
            "minimal": ["chat:write", "channels:read", "channels:history", "files:write", "users:read"],
            "full": ["chat:write", "channels:read", "channels:history", "files:write", "users:read"],
        },
        "shopify": {"minimal": [], "full": []},
        "jira": {"minimal": ["read:jira-work"], "full": ["read:jira-work", "write:jira-work"]},
        "notion": {"minimal": ["read"], "full": ["read", "update"]},
        "salesforce": {"minimal": ["refresh_token", "api", "openid"], "full": ["refresh_token", "api", "openid"]},
    }

    scopes = scope_map.get(vendor, {}).get("full" if tier == "full" else "minimal", [])

    # Build vendor authorize URL
    base_url = os.environ.get("MCP_BASE_URL", os.environ.get("AUTH_BASE_URL", "http://localhost:8000")).rstrip("/")
    redirect_uri = f"{base_url}/oauth/{vendor}"

    if vendor == "gmail" or vendor == "google_drive":
        client_id = client_id_override or os.environ.get("GOOGLE_CLIENT_ID", "")
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "state": state,
            "prompt": "consent",
        }
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return JSONResponse({"authorize_url": url, "state": state})

    if vendor == "ms365":
        tenant = os.environ.get("MICROSOFT_TENANT_ID", "common")
        client_id = client_id_override or os.environ.get("MICROSOFT_CLIENT_ID", "")
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "prompt": "consent",
        }
        url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urlencode(params)}"
        return JSONResponse({"authorize_url": url, "state": state})

    if vendor == "slack":
        client_id = client_id_override or os.environ.get("SLACK_CLIENT_ID", "")
        # Slack expects space-delimited scopes
        url = (
            "https://slack.com/oauth/v2/authorize?"
            + urlencode(
                {
                    "client_id": client_id,
                    "scope": " ".join(scopes),
                    "redirect_uri": redirect_uri,
                    "state": state,
                }
            )
        )
        return JSONResponse({"authorize_url": url, "state": state})

    if vendor == "notion":
        client_id = client_id_override or os.environ.get("NOTION_CLIENT_ID", "")
        params = {
            "client_id": client_id,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        url = f"https://api.notion.com/v1/oauth/authorize?{urlencode(params)}"
        return JSONResponse({"authorize_url": url, "state": state})

    if vendor == "shopify":
        # Require shop or shop_url
        target_shop = shop or shop_url
        if not target_shop:
            raise HTTPException(status_code=400, detail="Missing shop or shop_url for Shopify OAuth")
        # Normalize shop_url
        if not target_shop.startswith("http"):
            target_shop = f"https://{target_shop.strip().rstrip('/')}"
        client_id = client_id_override or os.environ.get("SHOPIFY_CLIENT_ID", "")
        params = {
            "client_id": client_id,
            "scope": ",".join(scopes),  # Shopify expects comma-separated scopes
            "redirect_uri": redirect_uri,
            "state": state,
        }
        url = f"{target_shop.rstrip('/')}/admin/oauth/authorize?{urlencode(params)}"
        return JSONResponse({"authorize_url": url, "state": state})

    if vendor == "jira":
        client_id = client_id_override or os.environ.get("JIRA_CLIENT_ID", "")
        params = {
            "audience": "api.atlassian.com",
            "client_id": client_id,
            "scope": " ".join(scopes) or "read:jira-work offline_access",
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
        url = f"https://auth.atlassian.com/authorize?{urlencode(params)}"
        return JSONResponse({"authorize_url": url, "state": state})

    if vendor == "salesforce":
        client_id = client_id_override or os.environ.get("SALESFORCE_CLIENT_ID", "")
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes) or "refresh_token api openid",
            "state": state,
        }
        url = f"https://login.salesforce.com/services/oauth2/authorize?{urlencode(params)}"
        return JSONResponse({"authorize_url": url, "state": state})

    # Jira 3LO can be added here; current MCP tool uses API token. For now, return state only.
    return JSONResponse({"authorize_url": "", "state": state})


@app.get("/oauth/{vendor}")
async def oauth_callback_vendor(
    vendor: str,
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    shop: Optional[str] = None,
    shop_url: Optional[str] = None,
):
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    secret = os.environ.get("OAUTH_STATE_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Server missing OAUTH_STATE_SECRET")

    data = _decode_state(state, secret)
    nonce = data.get("nonce")
    if not nonce:
        raise HTTPException(status_code=400, detail="Invalid state")
    redis = get_redis_client()
    if not await redis.exists(f"oauth:nonce:{nonce}"):
        raise HTTPException(status_code=400, detail="State expired or replayed")
    await redis.delete(f"oauth:nonce:{nonce}")

    tenant_id = data.get("tenant_id")
    tier = data.get("tier", "minimal")

    # Exchange code for tokens per vendor
    token_data: Dict[str, Any] = {}
    redirect_uri = f"{os.environ.get('MCP_BASE_URL', os.environ.get('AUTH_BASE_URL', 'http://localhost:8000')).rstrip('/')}/oauth/{vendor}"

    # Resolve per-tenant OAuth client credentials for token exchange
    client_id_override = None
    client_secret_override = None
    try:
        sm = TenantSecretsManager()
        oc = await sm.get_secret(str(tenant_id), vendor, "oauth_client")
        if not isinstance(oc, dict):
            alt = "google" if vendor in ("gmail", "google_drive") else ("microsoft" if vendor == "ms365" else vendor)
            oc = await sm.get_secret(str(tenant_id), alt, "oauth_client")
        if isinstance(oc, dict):
            client_id_override = oc.get("client_id") or oc.get("id") or None
            client_secret_override = oc.get("client_secret") or oc.get("secret") or None
    except Exception:
        pass

    if vendor in ("gmail", "google_drive"):
        async with AsyncOAuth2Client(
            client_id=client_id_override or os.environ.get("GOOGLE_CLIENT_ID", ""),
            client_secret=client_secret_override or os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            redirect_uri=redirect_uri,
        ) as client:
            token_data = await client.fetch_token("https://oauth2.googleapis.com/token", code=code, redirect_uri=redirect_uri)
            # Build and persist full oauth_credentials
            try:
                access_token = token_data.get("access_token")
                refresh_token = token_data.get("refresh_token")
                expires_in = int(token_data.get("expires_in", 3600))
                expires_at = (datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)).isoformat()
                base_creds = {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": client_id_override or os.environ.get("GOOGLE_CLIENT_ID", ""),
                    "client_secret": client_secret_override or os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                    "scopes": token_data.get("scope", "").split(),
                }
                # Gmail tool expects 'expiry'; Google Drive expects 'expires_at' (+ optional expires_in)
                if vendor == "gmail":
                    creds = {**base_creds, "expiry": expires_at}
                else:  # google_drive
                    creds = {**base_creds, "expires_at": expires_at, "expires_in": expires_in}
                sm = TenantSecretsManager()
                await sm.set_secret(str(tenant_id), vendor, "oauth_credentials", secret_value=creds)
            except Exception:
                pass

    elif vendor == "ms365":
        tenant = os.environ.get("MICROSOFT_TENANT_ID", "common")
        async with AsyncOAuth2Client(
            client_id=client_id_override or os.environ.get("MICROSOFT_CLIENT_ID", ""),
            client_secret=client_secret_override or os.environ.get("MICROSOFT_CLIENT_SECRET", ""),
            redirect_uri=redirect_uri,
        ) as client:
            token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            token_data = await client.fetch_token(token_url, code=code, redirect_uri=redirect_uri)
            try:
                access_token = token_data.get("access_token")
                refresh_token = token_data.get("refresh_token")
                token_type = token_data.get("token_type", "Bearer")
                scope = token_data.get("scope", "")
                expires_in = int(token_data.get("expires_in", 3600))
                expires_at = (datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)).isoformat()
                creds = {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": token_type,
                    "expires_in": expires_in,
                    "expires_at": expires_at,
                    "scope": scope,
                    "client_id": client_id_override or os.environ.get("MICROSOFT_CLIENT_ID", ""),
                    "client_secret": client_secret_override or os.environ.get("MICROSOFT_CLIENT_SECRET", ""),
                    "tenant_id": os.environ.get("MICROSOFT_TENANT_ID", ""),
                }
                sm = TenantSecretsManager()
                await sm.set_secret(str(tenant_id), "ms365", "oauth_credentials", secret_value=creds)
            except Exception:
                pass

    elif vendor == "slack":
        # Exchange code for bot and user tokens
        async with AsyncClient() as http:
            resp = await http.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "code": code,
                    "client_id": client_id_override or os.environ.get("SLACK_CLIENT_ID", ""),
                    "client_secret": client_secret_override or os.environ.get("SLACK_CLIENT_SECRET", ""),
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_data = resp.json()
        if not token_data.get("ok"):
            raise HTTPException(status_code=400, detail=token_data.get("error", "slack_oauth_failed"))
        sm = TenantSecretsManager()
        # Bot token
        bot_token = token_data.get("access_token")
        if bot_token:
            await sm.set_secret(str(tenant_id), "slack", "bot_token", value=bot_token)
        # User token credentials (if present)
        authed_user = token_data.get("authed_user") or {}
        if authed_user.get("access_token"):
            expires_in = authed_user.get("expires_in") or 43200
            expires_at = (datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in))).isoformat()
            await sm.set_secret(
                str(tenant_id),
                "slack",
                "user_token_credentials",
                value={
                    "access_token": authed_user.get("access_token"),
                    "refresh_token": authed_user.get("refresh_token"),
                    "expires_at": expires_at,
                    "client_id": os.environ.get("SLACK_CLIENT_ID", ""),
                    "client_secret": os.environ.get("SLACK_CLIENT_SECRET", ""),
                },
            )

    elif vendor == "notion":
        # Notion requires Basic auth with client creds
        client_id = client_id_override or os.environ.get("NOTION_CLIENT_ID", "")
        client_secret = client_secret_override or os.environ.get("NOTION_CLIENT_SECRET", "")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        async with AsyncClient() as http:
            resp = await http.post(
                "https://api.notion.com/v1/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=await resp.aread())
            token_data = resp.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        expires_at = (
            (datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in))).isoformat()
            if expires_in
            else None
        )
        owner = token_data.get("owner")
        bot_id = token_data.get("bot_id")
        workspace_id = token_data.get("workspace_id")
        creds = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "workspace_id": workspace_id,
            "bot_id": bot_id,
            "owner": owner,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        sm = TenantSecretsManager()
        await sm.set_secret(str(tenant_id), "notion", "credentials", secret_value=creds)

    elif vendor == "shopify":
        target_shop = shop or shop_url
        if not target_shop:
            raise HTTPException(status_code=400, detail="Missing shop or shop_url for Shopify OAuth")
        if not target_shop.startswith("http"):
            target_shop = f"https://{target_shop.strip().rstrip('/')}"
        async with AsyncClient() as http:
            resp = await http.post(
                f"{target_shop.rstrip('/')}/admin/oauth/access_token",
                json={
                    "client_id": os.environ.get("SHOPIFY_CLIENT_ID", ""),
                    "client_secret": os.environ.get("SHOPIFY_CLIENT_SECRET", ""),
                    "code": code,
                },
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=await resp.aread())
            token_data = resp.json()
        access_token = token_data.get("access_token")
        # Shopify tokens typically don't expire; store minimal credentials
        creds = {
            "shop_url": target_shop.rstrip("/"),
            "access_token": access_token,
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": None,
            "refresh_token": token_data.get("refresh_token"),
            "scopes": (token_data.get("scope") or "").split(",") if token_data.get("scope") else [],
        }
        sm = TenantSecretsManager()
        await sm.set_secret(str(tenant_id), "shopify", "credentials", secret_value=creds)

    elif vendor == "jira":
        client_id = os.environ.get("JIRA_CLIENT_ID", "")
        client_secret = os.environ.get("JIRA_CLIENT_SECRET", "")
        async with AsyncClient() as http:
            # Exchange code for tokens
            resp = await http.post(
                "https://auth.atlassian.com/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=await resp.aread())
            token_data = resp.json()

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = int(token_data.get("expires_in", 3600))
            expires_at = (datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)).isoformat()

            # Fetch accessible resources to obtain cloud_id
            resp2 = await http.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            cloud_id = None
            domain = None
            try:
                resources = resp2.json()
                if isinstance(resources, list) and resources:
                    # pick first Jira resource
                    for r in resources:
                        if r.get("scopes") and any("jira" in s for s in r.get("scopes", [])):
                            cloud_id = r.get("id")
                            url = r.get("url")
                            if url and ".atlassian.net" in url:
                                try:
                                    domain = url.split("https://")[1].split(".atlassian.net")[0]
                                except Exception:
                                    domain = None
                            break
                    if not cloud_id:
                        cloud_id = resources[0].get("id")
            except Exception:
                pass

        creds = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        sm = TenantSecretsManager()
        await sm.set_secret(str(tenant_id), "jira", "oauth_credentials", secret_value=creds)
        if cloud_id:
            await sm.set_secret(str(tenant_id), "jira", "cloud_id", value=str(cloud_id))
        if domain:
            await sm.set_secret(str(tenant_id), "jira", "domain", value=str(domain))

    elif vendor == "salesforce":
        async with AsyncOAuth2Client(
            client_id=os.environ.get("SALESFORCE_CLIENT_ID", ""),
            client_secret=os.environ.get("SALESFORCE_CLIENT_SECRET", ""),
            redirect_uri=redirect_uri,
        ) as client:
            token_url = "https://login.salesforce.com/services/oauth2/token"
            token_data = await client.fetch_token(token_url, code=code, redirect_uri=redirect_uri)
        creds = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "instance_url": token_data.get("instance_url"),
            "id": token_data.get("id"),
            "token_type": token_data.get("token_type", "Bearer"),
            "issued_at": token_data.get("issued_at"),
            "signature": token_data.get("signature"),
            "client_id": os.environ.get("SALESFORCE_CLIENT_ID", ""),
            "client_secret": os.environ.get("SALESFORCE_CLIENT_SECRET", ""),
        }
        sm = TenantSecretsManager()
        await sm.set_secret(str(tenant_id), "salesforce", "oauth_credentials", secret_value=creds)
    else:
        # For other vendors, callback handling will be implemented per provider
        token_data = {}

    # Backward-compat: persist refresh_token if present
    refresh_token = token_data.get("refresh_token")
    if refresh_token and tenant_id is not None:
        sm = TenantSecretsManager()
        try:
            await sm.store_secret(str(tenant_id), vendor, "refresh_token", refresh_token)
        except Exception:
            pass

    # Minimal HTML response to close popup
    html = f"""
<!doctype html>
<html><body>
<script>
  (function() {{
    try {{
      if (window.opener) {{
        window.opener.postMessage({{ type: 'oauth_connected', vendor: '{vendor}' }}, '*');
      }} else if (window.parent) {{
        window.parent.postMessage({{ type: 'oauth_connected', vendor: '{vendor}' }}, '*');
      }}
    }} catch (e) {{}}
    window.close();
  }})();
</script>
Connected. You can close this window.
</body></html>
"""
    return HTMLResponse(content=html, status_code=200)

@app.post("/webhook/slack/{tenant_id}")
async def slack_webhook(tenant_id: int, request: Request):
    try:
        body_bytes = await request.body()
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
        signature = request.headers.get("X-Slack-Signature", "")

        # Quota check: count inbound events as vendor usage to protect pipeline
        await _quota_increment_or_429(tenant_id, "slack")

        from src.tools.mcp.mcp_slack import MCPSlackTool
        tool = MCPSlackTool()
        is_valid = await tool.handle_webhook(
            tenant_id=str(tenant_id),
            timestamp=timestamp,
            body=body_bytes.decode("utf-8"),
            signature=signature,
        )
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

        from src.core.celery import celery_app as _celery
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            payload = {"raw": body_bytes.decode("utf-8", errors="ignore")}
        _celery.send_task(
            "webhooks.process_slack_event",
            args=[tenant_id, payload],
            kwargs={},
            queue="high_priority",
        )

        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/jira/{tenant_id}")
async def jira_webhook(tenant_id: int, request: Request):
    try:
        body_bytes = await request.body()
        signature = request.headers.get("X-Atlassian-Webhook-Signature", "")

        await _quota_increment_or_429(tenant_id, "jira")

        from src.tools.mcp.mcp_jira import MCPJiraTool
        tool = MCPJiraTool()
        result = await tool.handle_webhook(
            tenant_id=str(tenant_id), payload=body_bytes, signature=signature
        )
        if not result.success:
            raise HTTPException(status_code=401, detail=result.error_message or "Invalid signature")

        from src.core.celery import celery_app as _celery
        _celery.send_task(
            "webhooks.process_jira_event",
            args=[tenant_id, json.loads(body_bytes.decode("utf-8"))],
            kwargs={},
            queue="high_priority",
        )
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/notion/{tenant_id}")
async def notion_webhook(tenant_id: int, request: Request):
    try:
        body_bytes = await request.body()
        signature = request.headers.get("X-Notion-Signature", "")

        await _quota_increment_or_429(tenant_id, "notion")

        from src.tools.mcp.mcp_notion import MCPNotionTool
        tool = MCPNotionTool()
        result = await tool.handle_webhook(
            tenant_id=str(tenant_id), payload=body_bytes, signature=signature
        )
        if not result.success:
            raise HTTPException(status_code=401, detail=result.error_message or "Invalid signature")

        from src.core.celery import celery_app as _celery
        _celery.send_task(
            "webhooks.process_notion_event",
            args=[tenant_id, json.loads(body_bytes.decode("utf-8"))],
            kwargs={},
            queue="high_priority",
        )
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/shopify/{tenant_id}")
async def shopify_webhook(tenant_id: int, request: Request):
    try:
        body_bytes = await request.body()
        hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
        topic = request.headers.get("X-Shopify-Topic", "")

        await _quota_increment_or_429(tenant_id, "shopify")

        from src.tools.mcp.mcp_shopify import ShopifyProductionTool
        tool = ShopifyProductionTool()
        result = await tool.handle_webhook(
            tenant_id=str(tenant_id), body=body_bytes, hmac_header=hmac_header, topic=topic
        )
        if not result.success:
            raise HTTPException(status_code=401, detail=result.error_message or "Invalid signature")

        from src.core.celery import celery_app as _celery
        _celery.send_task(
            "webhooks.process_shopify_event",
            args=[tenant_id, json.loads(body_bytes.decode("utf-8"))],
            kwargs={},
            queue="high_priority",
        )
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Assets preview and download endpoints
# =====================

@app.get("/assets/{asset_id}")
async def get_asset_preview(asset_id: str, request: Request):
    try:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Tenant not resolved")
        svc = ContentRepositoryService(tenant_id=str(tenant_id), project_id=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        access = None
        for delay in [0.0, 0.2, 0.5, 1.0, 2.0, 3.0]:
            access = svc.get_access(asset_id)
            if access:
                break
            if delay:
                await asyncio.sleep(delay)
        if not access:
            raise HTTPException(status_code=404, detail="Asset not found")
        return JSONResponse(access)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/assets/{asset_id}/download")
async def get_asset_download(asset_id: str, request: Request):

    try:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            raise HTTPException(status_code=401, detail="Tenant not resolved")
        svc = ContentRepositoryService(tenant_id=str(tenant_id), project_id=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        record = None
        for delay in [0.0, 0.2, 0.5, 1.0, 2.0, 3.0]:
            record = svc.get_asset(asset_id)
            if record:
                break
            if delay:
                await asyncio.sleep(delay)
        if not record:
            raise HTTPException(status_code=404, detail="Asset not found")
        # Generate signed URL using storage client
        from datetime import timedelta
        from google.cloud import storage
        client = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
        bucket_name, blob_name = record.gcs_uri[5:].split("/", 1)
        url = client.bucket(bucket_name).blob(blob_name).generate_signed_url(
            version="v4", expiration=timedelta(minutes=5), method="GET"
        )
        return JSONResponse({"asset_id": record.asset_id, "url": url, "expires_in_seconds": 300})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Quota management
# =====================

QUOTA_DEFAULTS: Dict[str, int] = {
    "gmail": 2000,
    "google_drive": 2000,
    "ms365": 2000,
    "slack": 5000,
    "shopify": 3000,
    "jira": 3000,
    "notion": 3000,
    "salesforce": 2000,
}

# Global limits
GLOBAL_DAILY_API_CALLS: int = 10000
PER_IP_PER_MINUTE: int = 120


async def _quota_increment_or_429(tenant_id: int, vendor: str) -> None:
    vendor = vendor.lower()
    limit = QUOTA_DEFAULTS.get(vendor, 2000)
    now = datetime.datetime.utcnow()
    date_str = now.strftime("%Y%m%d")
    key = f"quota:{tenant_id}:{vendor}:{date_str}"
    redis = get_redis_client()
    client = await redis.get_client()
    # Compute TTL until midnight UTC
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl_seconds = int((midnight - now).total_seconds())

    try:
        # Preferred path: use pipeline if available
        async with client.pipeline(transaction=True) as pipe:  # type: ignore[attr-defined]
            await pipe.incr(key)
            await pipe.expire(key, ttl_seconds)
            results = await pipe.execute()
        current = int(results[0] or 0)
    except Exception:
        # Fallback path for DummyRedis (no pipeline/expire)
        try:
            current = int(await client.incr(key))
        except Exception:
            # If even incr fails, treat as no-op
            current = 0
        # Best-effort expire if supported
        if hasattr(client, "expire"):
            try:
                await client.expire(key, ttl_seconds)  # type: ignore[attr-defined]
            except Exception:
                pass
    if current > limit:
        retry_after = ttl_seconds
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Quota exceeded",
                "vendor": vendor,
                "limit": limit,
                "current": current,
                "reset_in": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(max(0, limit - current)),
            },
        )


# =====================
# Secret rotation endpoint
# =====================

@app.post("/secrets/{tool}/{key}/rotate")
async def rotate_secret(tool: str, key: str, request: Request):
    try:
        payload = await request.json()
        tenant_id = payload.get("tenant_id")
        new_value = payload.get("new_value")
        revoke_old = bool(payload.get("revoke_old", True))
        if tenant_id is None or not new_value:
            raise HTTPException(status_code=400, detail="tenant_id and new_value are required")

        sm = TenantSecretsManager()
        tenant_str = str(tenant_id)

        # Fetch old secret if present
        old_value = await sm.get_secret(tenant_str, tool, key)

        # Store new secret version
        ok = await sm.store_secret(tenant_str, tool, key, new_value)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to store new secret")

        # Attempt revocation for supported vendors
        if revoke_old and old_value:
            try:
                if tool in ("gmail", "google", "google_drive") and key == "refresh_token":
                    async with AsyncClient() as http:
                        await http.post(
                            "https://oauth2.googleapis.com/revoke",
                            data={"token": old_value},
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                        )
                elif tool in ("ms365", "microsoft") and key == "refresh_token":
                    # Microsoft revocation varies; best-effort: no universal endpoint for all apps
                    pass
            except Exception:
                # Non-fatal; rotation succeeded
                pass

        return JSONResponse({"success": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# GDPR delete endpoint (async task)
# =====================

@app.delete("/tenant/{tenant_id}")
async def gdpr_delete(tenant_id: int):
    try:
        # Enqueue Celery job to purge data
        celery_app.send_task("security.gdpr_delete_tenant", args=[tenant_id], kwargs={}, queue="high_priority")
        return JSONResponse({"accepted": True})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health/cache")
async def cache_health() -> Dict[str, Any]:
    try:
        from src.core.redis import get_redis_client
        client = get_redis_client()
        # FT.INFO on semantic index
        info = await client.execute_command("FT.INFO", "semantic_idx")
        return {"status": "ok", "index": "semantic_idx"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.on_event("startup")
async def startup_event():
    logger.info("Running tool initialization...")
    initialize_tools(force_update=True) # Force update to pick up any changes in the config
    logger.info("Tool initialization complete.")


def create_app() -> FastAPI:

    return app
