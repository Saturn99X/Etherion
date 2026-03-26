import os
import sys
from pathlib import Path
import asyncio
import json
from typing import Optional

from httpx import AsyncClient, ASGITransport
from google.cloud import secretmanager

# Ensure project root is on sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load secrets from GSM before importing app modules (they require them at import time)
def _ensure_jwt_secret_loaded():
    if os.getenv("JWT_SECRET_KEY"):
        return
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        # Let the import fail loudly with clear instructions if project is missing
        raise RuntimeError("Set GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT to load JWT_SECRET_KEY from GSM")
    client = secretmanager.SecretManagerServiceClient()
    name = client.secret_version_path(project_id, "JWT_SECRET_KEY", "latest")
    response = client.access_secret_version(request={"name": name})
    os.environ["JWT_SECRET_KEY"] = response.payload.data.decode("utf-8")


def _ensure_secret_key_loaded():
    if os.getenv("SECRET_KEY"):
        return
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise RuntimeError("Set GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT to load SECRET_KEY from GSM")
    client = secretmanager.SecretManagerServiceClient()
    name = client.secret_version_path(project_id, "SECRET_KEY", "latest")
    response = client.access_secret_version(request={"name": name})
    os.environ["SECRET_KEY"] = response.payload.data.decode("utf-8")


_ensure_jwt_secret_loaded()
_ensure_secret_key_loaded()

from src.etherion_ai.app import create_app
from src.database.db import get_scoped_session
from src.database.models import Tenant, User
from sqlalchemy import select
from src.auth.jwt import create_access_token
from src.utils.secrets_manager import TenantSecretsManager


async def ensure_tenant_and_user() -> tuple[int, str]:
    async with get_scoped_session() as session:
        # Try to find existing tenant by subdomain
        result = await session.execute(select(Tenant).where(Tenant.subdomain == "prod-mcp-test"))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                tenant_id="prod-mcp-test",
                subdomain="prod-mcp-test",
                name="Prod MCP Test Tenant",
                admin_email="mcp-test@example.local",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

        # Try to find existing user by user_id
        result = await session.execute(select(User).where(User.user_id == "mcp-test-user"))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(user_id="mcp-test-user", tenant_id=tenant.id, email="mcp-test@example.local")
            session.add(user)
            await session.commit()
            await session.refresh(user)

    return tenant.id, user.user_id


def access_global_secret(project_id: str, secret_name: str) -> Optional[str]:
    client = secretmanager.SecretManagerServiceClient()
    name = client.secret_version_path(project_id, secret_name, "latest")
    try:
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")
    except Exception as e:
        print(f"[ERROR] Failed to access global secret {secret_name}: {e}")
        return None


async def get_per_tenant_secret(tenant_id: int, service: str, key: str) -> Optional[str]:
    sm = TenantSecretsManager()
    return await sm.get_secret(str(tenant_id), service, key)


async def run_real_slack_list_users_test():
    # Required envs
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT must be set for GSM access")

    os.environ.setdefault("SECRET_KEY", "prod-mcp-test-secret-key")

    app = create_app()

    tenant_id, user_id = await ensure_tenant_and_user()

    # Ensure per-tenant Slack bot token is available. We do not attempt to WRITE to GSM here.
    tenant_bot = await get_per_tenant_secret(tenant_id, "slack", "bot_token")
    if not tenant_bot:
        raise RuntimeError(
            f"Missing per-tenant secret '{tenant_id}--slack--bot_token'. "
            f"Create it in Google Secret Manager and grant read access to your Application Default Credentials, then retry."
        )

    # Build auth token
    token = create_access_token({"sub": user_id, "email": "mcp-test@example.local", "tenant_id": tenant_id})
    headers = {"Authorization": f"Bearer {token}"}

    # Execute real Slack MCP tool using a safe read operation
    execute_mut = """
    mutation Execute($tool:String!, $payload:String!){
        executeMCPTool(toolName:$tool, params:$payload){
            success
            result
            errorMessage
            toolOutput
        }
    }
    """

    # Use get_users_list with minimal limit to avoid heavy usage
    params_payload = json.dumps({
        "tenant_id": tenant_id,
        "operation": "get_users_list",
        "params": {"limit": 5}
    })

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/graphql",
            json={"query": execute_mut, "variables": {"tool": "mcp_slack", "payload": params_payload}},
            headers=headers,
        )
        print("Status:", resp.status_code)
        body = resp.json()
        print(json.dumps(body, indent=2))

        data = body.get("data", {}).get("executeMCPTool")
        if not data or not data.get("success"):
            raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(run_real_slack_list_users_test())
