import os
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import pytest
from httpx import AsyncClient, ASGITransport
from src.etherion_ai import app as app_module
from src.services.silo_oauth_service import SiloOAuthService


@pytest.mark.asyncio
async def test_pillar05_mcp_tools_quota_oauth_and_secret_rotation(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p5")
    os.environ.setdefault("SECRET_KEY", "test-secret-p5-app")
    os.environ.setdefault("GCP_PROJECT_ID", "pillar05-test")
    # Disable external GCP logging/monitoring for tests to avoid permission errors and network calls
    os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
    os.environ.pop("GCP_PROJECT_ID", None)
    # Allow dev/test master key generation if any credential paths are touched
    os.environ.setdefault("ALLOW_DEV_GENERATED_MASTER_KEY", "true")
    os.environ.setdefault("OAUTH_STATE_SECRET", "pillar05-mcp-state")

    from src.etherion_ai.app import create_app
    app = create_app()

    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token
    from tests.e2e._dummy_redis import setup_dummy_redis
    from src.utils import secrets_manager as secrets_module
    from src.utils.secrets_manager import TenantSecretsManager
    from src.services.mcp_tool_manager import MCPToolManager, MCPToolResult

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dummy_redis = setup_dummy_redis(monkeypatch)

        class _InMemoryCredentialManager:
            def __init__(self):
                self._store: dict[tuple[str, str, str], str] = {}

            def store_secret(self, tenant_id: str, service_name: str, key_type: str, secret_value: str) -> None:
                self._store[(tenant_id, service_name, key_type)] = secret_value

            def get_secret(self, tenant_id: str, service_name: str, key_type: str) -> str | None:
                return self._store.get((tenant_id, service_name, key_type))

            def revoke_secret(self, tenant_id: str, service_name: str, key_type: str) -> None:
                self._store.pop((tenant_id, service_name, key_type), None)

        credential_backend = _InMemoryCredentialManager()
        monkeypatch.setattr(secrets_module, "CredentialManager", lambda: credential_backend)

        # Reinitialize silo OAuth service so it uses the in-memory CredentialManager backend
        app_module.silo_oauth = SiloOAuthService()

        async def _fake_handle_callback(
            *, provider: str, code: str, state: str, request_params: dict | None = None
        ) -> dict:
            payload = await app_module.silo_oauth._state.decode_and_verify(state)
            tenant_id = str(payload.get("tenant_id"))
            token_resp = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "token_type": "Bearer",
                "created_at": int(datetime.utcnow().timestamp()),
            }
            save_payload = dict(token_resp)
            save_payload.update({"client_id": "test-client-id", "client_secret": "test-client-secret"})
            await app_module.silo_oauth._tsm.set_secret(tenant_id, provider, "oauth_tokens", save_payload)
            return {"ok": True, "tenant_id": tenant_id, "provider": provider, "redirect_to": payload.get("redirect_to")}

        monkeypatch.setattr(app_module.silo_oauth, "handle_callback", _fake_handle_callback, raising=False)

        # Tenant + user
        async with get_scoped_session() as session:
            tenant = Tenant(
                tenant_id="pillar05-mcp",
                subdomain="pillar05-mcp",
                name="Pillar05 MCP Tenant",
                admin_email="p5@test.local",
            )
            session.add(tenant); await session.commit(); await session.refresh(tenant)
            user = User(user_id="p5-user", tenant_id=tenant.id, email="p5@test.local")
            session.add(user); await session.commit(); await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        # API rate limit headers present
        root = await client.get("/")
        assert root.headers.get("X-RateLimit-Limit") is not None

        # GraphQL: list available MCP tools
        list_query = (
            "query { getAvailableMCPTools { name description category requiredCredentials capabilities status } }"
        )
        gql_list = await client.post("/graphql", json={"query": list_query}, headers=headers)
        assert gql_list.status_code == 200
        tools = gql_list.json().get("data", {}).get("getAvailableMCPTools")
        assert isinstance(tools, list) and len(tools) >= 1
        # Basic sanity: known tool names should exist in registry
        names = {t.get("name") for t in tools}
        assert any(n in names for n in {"mcp_slack", "mcp_gmail", "mcp_notion"})

        # GraphQL: per-tenant vendor quota remaining
        quota_query = "query($v:String!) { getVendorQuotaRemaining(vendor:$v) }"
        gql_quota = await client.post("/graphql", json={"query": quota_query, "variables": {"v": "slack"}}, headers=headers)
        assert gql_quota.status_code == 200
        remaining = gql_quota.json().get("data", {}).get("getVendorQuotaRemaining")
        assert isinstance(remaining, int) and remaining >= 0

        # OAuth silo flow (start + callback + revoke) using Google provider
        if os.getenv("OAUTH_STATE_SECRET"):
            tenant_str = str(tenant.id)
            # Seed OAuth client credentials in the in-memory credential backend
            credential_backend.store_secret(
                tenant_str,
                "google",
                "oauth_credentials",
                json.dumps({"client_id": "test-google-client", "client_secret": "test-google-secret"}),
            )

            oauth = await client.get(
                "/oauth/silo/google/start?redirect_to=http://localhost/callback",
                headers=headers,
            )
            assert oauth.status_code == 200
            data = oauth.json()
            assert "authorize_url" in data

            parsed = urlparse(data["authorize_url"])
            qs = parse_qs(parsed.query)
            state_values = qs.get("state") or []
            assert state_values
            state = state_values[0]

            callback_resp = await client.get(
                f"/oauth/silo/google/callback?code=fake-code&state={state}",
                headers=headers,
            )
            assert callback_resp.status_code == 200
            cb_json = callback_resp.json()
            assert cb_json.get("ok") is True
            assert cb_json.get("provider") == "google"

            # Verify tokens stored and revoked via GSM-style keying
            assert (tenant_str, "google", "oauth_tokens") in credential_backend._store

            revoke_resp = await client.post("/oauth/silo/google/revoke", headers=headers)
            assert revoke_resp.status_code == 200
            assert (tenant_str, "google", "oauth_tokens") not in credential_backend._store

        # Secret rotation endpoint (requires Authorization header)
        rotate = await client.post(
            "/secrets/gmail/refresh_token/rotate",
            json={"tenant_id": tenant.id, "new_value": "mcp-rotated-token-e2e"},
            headers=headers,
        )
        assert rotate.status_code == 200
        rj = rotate.json()
        assert isinstance(rj, dict) and rj.get("success") is True

        # Pre-seed tenant secrets for all supported MCP tools
        secrets_mgr = TenantSecretsManager()
        tenant_str = str(tenant.id)
        required_secrets: dict[str, dict[str, str]] = {
            "slack": {
                "bot_token": "xoxb-test-token",
                "signing_secret": "signing-secret",
            },
            "jira": {
                "email": "jira@test.local",
                "api_token": "jira-token",
                "cloud_id": "cloud-id",
                "domain": "jira.example.com",
                "webhook_secret": "jira-webhook",
            },
            "hubspot": {
                "api_key": "hubspot-api-key",
            },
            "notion": {
                "credentials": json.dumps({"access_token": "notion-token"}),
                "webhook_secret": "notion-webhook",
            },
            "shopify": {
                "access_token": "shopify-token",
                "shop_domain": "myshop.myshopify.com",
            },
            "gmail": {
                "refresh_token": "gmail-refresh",
            },
            "google_drive": {
                "refresh_token": "drive-refresh",
            },
            "ms365": {
                "refresh_token": "ms365-refresh",
                "tenant_id": "ms365-tenant",
            },
            "google": {
                "client_id": "google-client",
                "client_secret": "google-secret",
            },
        }

        for service, keys in required_secrets.items():
            for key, value in keys.items():
                stored = await secrets_mgr.store_secret(tenant_str, service, key, value)
                assert stored is True

        excluded_tools = {"mcp_twitter", "mcp_reddit", "mcp_salesforce", "mcp_instagram"}
        tool_requirements: dict[str, list[tuple[str, str]]] = {
            "mcp_slack": [("slack", "bot_token")],
            "mcp_jira": [("jira", "api_token"), ("jira", "email"), ("jira", "cloud_id"), ("jira", "domain")],
            "mcp_hubspot": [("hubspot", "api_key")],
            "mcp_notion": [("notion", "credentials")],
            "mcp_shopify": [("shopify", "access_token"), ("shopify", "shop_domain")],
            "mcp_gmail": [("gmail", "refresh_token")],
            "mcp_google_drive": [("google_drive", "refresh_token")],
            "mcp_ms365": [("ms365", "refresh_token")],
        }

        successful_tools: list[str] = []

        async def _fake_execute_tool(self, tool_name: str, params: dict):
            tenant_id = str(params.get("tenant_id"))
            assert tenant_id == tenant_str
            reqs = tool_requirements.get(tool_name, [])
            for service_name, key_name in reqs:
                secret_value = await secrets_mgr.get_secret(tenant_id, service_name, key_name)
                assert secret_value, f"Missing secret {service_name}/{key_name} for {tool_name}"
            successful_tools.append(tool_name)
            return MCPToolResult(
                success=True,
                result=f"Executed {tool_name}",
                executionTime=0.05,
                errorMessage=None,
                toolOutput={"ok": True, "tool": tool_name},
            )

        monkeypatch.setattr(MCPToolManager, "execute_tool", _fake_execute_tool, raising=False)

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

        for tool in names:
            if tool in excluded_tools:
                continue
            params_payload = json.dumps({
                "tenant_id": tenant.id,
                "operation": "ping",
                "params": {"echo": tool},
            })
            exec_resp = await client.post(
                "/graphql",
                json={"query": execute_mut, "variables": {"tool": tool, "payload": params_payload}},
                headers=headers,
            )
            assert exec_resp.status_code == 200
            exec_body = exec_resp.json().get("data", {}).get("executeMCPTool")
            assert exec_body and exec_body.get("success") is True
            assert exec_body.get("toolOutput", {}).get("tool") == tool

        expected_success_tools = sorted([t for t in names if t not in excluded_tools])
        assert sorted(successful_tools) == expected_success_tools

        # Exercise webhook quota increments for Slack, Jira, and Notion
        date_key = datetime.utcnow().strftime("%Y%m%d")
        webhook_headers = {
            "X-Slack-Request-Timestamp": "0",
            "X-Slack-Signature": "v0=test",
        }
        slack_resp = await client.post(f"/webhook/slack/{tenant.id}", content=b"{}", headers=webhook_headers)
        assert slack_resp.status_code in (200, 401, 500)

        jira_resp = await client.post(
            f"/webhook/jira/{tenant.id}",
            content=b"{}",
            headers={"X-Atlassian-Webhook-Signature": "test"},
        )
        assert jira_resp.status_code in (200, 401, 500)

        notion_resp = await client.post(
            f"/webhook/notion/{tenant.id}",
            content=b"{}",
            headers={"X-Notion-Signature": "test"},
        )
        assert notion_resp.status_code in (200, 401, 500)

        for vendor in ("slack", "jira", "notion"):
            quota_key = f"quota:{tenant.id}:{vendor}:{date_key}"
            assert quota_key in dummy_redis.store
            assert int(dummy_redis.store[quota_key]) >= 1
