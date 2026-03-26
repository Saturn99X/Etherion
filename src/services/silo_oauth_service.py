import os
import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

from src.services.oauth_state import OAuthStateManager
from src.utils.secrets_manager import TenantSecretsManager


@dataclass
class ProviderConfig:
    name: str
    auth_url: str
    token_url: Optional[str]
    scopes: List[str]
    client_id_envs: List[str]
    client_secret_envs: List[str]


class SiloOAuthService:
    """
    Unified OAuth for silos and MCP tools: Google, Jira, HubSpot, Slack, Notion, Shopify.

    - Builds provider authorization URLs with HMAC-signed state
    - Exchanges codes for tokens
    - Stores tokens per-tenant in TenantSecretsManager under
      {tenant}--{provider}--oauth_tokens (JSON)
    - For Slack, also writes {tenant}--slack--user_token_credentials for MCP tool compatibility
    """

    def __init__(self):
        self._state = OAuthStateManager(ttl_seconds=900)
        self._tsm = TenantSecretsManager()
        base = os.getenv("AUTH_BASE_URL", "http://localhost:8000").rstrip("/")
        self._base = base
        self._redirect_base = f"{base}/oauth/silo"

        self._providers: Dict[str, ProviderConfig] = {
            # Google (Drive/Gmail scopes can be extended)
            "google": ProviderConfig(
                name="google",
                auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
                scopes=[
                    "https://www.googleapis.com/auth/userinfo.email",
                    "https://www.googleapis.com/auth/userinfo.profile",
                    "https://www.googleapis.com/auth/drive.readonly",
                    "offline_access",
                ],
                client_id_envs=["OAUTH_GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_ID"],
                client_secret_envs=["OAUTH_GOOGLE_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"],
            ),
            # Jira (Atlassian)
            "jira": ProviderConfig(
                name="jira",
                auth_url="https://auth.atlassian.com/authorize",
                token_url="https://auth.atlassian.com/oauth/token",
                scopes=[
                    "read:jira-user",
                    "read:jira-work",
                    "offline_access",
                ],
                client_id_envs=["OAUTH_JIRA_CLIENT_ID"],
                client_secret_envs=["OAUTH_JIRA_CLIENT_SECRET"],
            ),
            # HubSpot
            "hubspot": ProviderConfig(
                name="hubspot",
                auth_url="https://app.hubspot.com/oauth/authorize",
                token_url="https://api.hubapi.com/oauth/v1/token",
                scopes=[
                    "crm.objects.contacts.read",
                    "crm.objects.companies.read",
                    "oauth",
                ],
                client_id_envs=["HUBSPOT_OAUTH_CLIENT_ID"],
                client_secret_envs=["HUBSPOT_OAUTH_CLIENT_SECRET"],
            ),
            # Slack
            "slack": ProviderConfig(
                name="slack",
                auth_url="https://slack.com/oauth/v2/authorize",
                token_url="https://slack.com/api/oauth.v2.access",
                scopes=[
                    "users:read",
                    "channels:read",
                    "channels:history",
                    "files:read",
                ],
                client_id_envs=["SLACK_USER_OAUTH_CLIENT_ID", "SLACK_CLIENT_ID"],
                client_secret_envs=["SLACK_USER_OAUTH_CLIENT_SECRET", "SLACK_CLIENT_SECRET"],
            ),
            # Notion
            "notion": ProviderConfig(
                name="notion",
                auth_url="https://api.notion.com/v1/oauth/authorize",
                token_url="https://api.notion.com/v1/oauth/token",
                scopes=["read", "databases.read", "pages.read"],
                client_id_envs=["NOTION_OAUTH_CLIENT_ID"],
                client_secret_envs=["NOTION_OAUTH_CLIENT_SECRET"],
            ),
            # Microsoft 365 (Graph API — Mail, Files, Calendar)
            "microsoft": ProviderConfig(
                name="microsoft",
                auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
                scopes=[
                    "https://graph.microsoft.com/Mail.Read",
                    "https://graph.microsoft.com/Files.Read",
                    "https://graph.microsoft.com/User.Read",
                    "offline_access",
                ],
                client_id_envs=["MICROSOFT_OAUTH_CLIENT_ID", "MICROSOFT_CLIENT_ID"],
                client_secret_envs=["MICROSOFT_OAUTH_CLIENT_SECRET", "MICROSOFT_CLIENT_SECRET"],
            ),
            # Shopify (shop-specific host required)
            "shopify": ProviderConfig(
                name="shopify",
                auth_url="https://{shop}/admin/oauth/authorize",  # requires shop host
                token_url=None,  # computed per-shop
                scopes=["read_products", "read_customers", "read_orders"],
                client_id_envs=["SHOPIFY_OAUTH_CLIENT_ID"],
                client_secret_envs=["SHOPIFY_OAUTH_CLIENT_SECRET"],
            ),
        }

    def _env(self, keys: List[str]) -> Optional[str]:
        for k in keys:
            v = os.getenv(k)
            if v and v.strip():
                return v
        return None

    def _redirect_uri(self, provider: str) -> str:
        return f"{self._redirect_base}/{provider}/callback"

    async def _resolve_client_creds(self, tenant_id: str, p: ProviderConfig) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve client_id/client_secret using per-tenant override when available,
        else fallback to environment variables configured from GSM.
        """
        client_id: Optional[str] = None
        client_secret: Optional[str] = None
        # Try tenant-scoped override
        try:
            creds = await self._tsm.get_secret(str(tenant_id), p.name, "oauth_credentials")
            if isinstance(creds, dict):
                client_id = (creds.get("client_id") or creds.get("id") or None)
                client_secret = (creds.get("client_secret") or creds.get("secret") or None)
        except Exception:
            pass
        # Fallback to env if missing
        client_id = client_id or self._env(p.client_id_envs)
        client_secret = client_secret or self._env(p.client_secret_envs)
        return client_id, client_secret

    async def build_authorize_url(
        self,
        *,
        tenant_id: str,
        provider: str,
        redirect_to: Optional[str] = None,
        shop: Optional[str] = None,
        scopes_override: Optional[List[str]] = None,
    ) -> str:
        p = self._providers.get(provider)
        if not p:
            raise ValueError("unsupported_provider")

        client_id, client_secret = await self._resolve_client_creds(tenant_id, p)
        if not client_id or not client_secret:
            # Credentials must exist in env via GSM secret refs
            raise RuntimeError(f"missing_oauth_client_env:{p.client_id_envs[0]}")

        state = await self._state.encode(
            tenant_id=str(tenant_id), provider=provider, extra={"redirect_to": redirect_to, "shop": shop}
        )
        redirect_uri = self._redirect_uri(provider)
        scopes = scopes_override or p.scopes
        scope_str = " ".join(scopes)

        # Shopify special case (needs shop hostname)
        if provider == "shopify":
            if not shop:
                raise ValueError("shopify_shop_required")
            # Normalize shop domain
            shop_host = shop
            if "." not in shop_host:
                shop_host = f"{shop_host}.myshopify.com"
            auth_url = p.auth_url.format(shop=shop_host)
            params = {
                "client_id": client_id,
                "scope": ",".join(scopes),  # Shopify expects comma-separated
                "redirect_uri": redirect_uri,
                "state": state,
                "response_type": "code",
            }
            # httpx.URL has no human_repr(); cast to string for encoded URL
            return str(httpx.URL(auth_url, params=params))

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
        }
        # Provider-specific additions
        if provider == "google":
            params.update({"access_type": "offline", "prompt": "consent"})
        elif provider == "jira":
            params.update({"audience": "api.atlassian.com", "prompt": "consent"})
        elif provider == "slack":
            # Slack v2: use "user_scope" for user tokens; treat our scopes as user scopes
            params.pop("scope", None)
            params["user_scope"] = scope_str

        # httpx.URL has no human_repr(); cast to string for encoded URL
        return str(httpx.URL(p.auth_url, params=params))

    async def handle_callback(
        self,
        *,
        provider: str,
        code: str,
        state: str,
        request_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = await self._state.decode_and_verify(state)
        tenant_id = str(payload.get("tenant_id"))
        if not tenant_id:
            raise ValueError("missing_tenant_id_in_state")

        p = self._providers.get(provider)
        if not p:
            raise ValueError("unsupported_provider")

        client_id, client_secret = await self._resolve_client_creds(tenant_id, p)
        redirect_uri = self._redirect_uri(provider)

        token_resp: Dict[str, Any]

        if provider == "shopify":
            shop = payload.get("shop") or (request_params or {}).get("shop")
            if not shop:
                raise ValueError("shopify_shop_required")
            shop_host = shop
            if "." not in shop_host:
                shop_host = f"{shop_host}.myshopify.com"
            token_url = f"https://{shop_host}/admin/oauth/access_token"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    token_url,
                    json={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                    },
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                # Shopify returns long-lived access_token
                token_resp = {
                    "access_token": data.get("access_token"),
                    "token_type": "bearer",
                    "scope": data.get("scope"),
                    "created_at": int(time.time()),
                }
        elif provider == "notion":
            basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    p.token_url,
                    json={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Content-Type": "application/json",
                        "Notion-Version": "2022-06-28",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                token_resp = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "token_type": data.get("token_type"),
                    "workspace_id": (data.get("workspace_id") or (data.get("owner") or {}).get("workspace_id")),
                    "created_at": int(time.time()),
                }
        elif provider == "slack":
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    p.token_url,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"slack_token_exchange_failed:{data}")
                authed_user = (data.get("authed_user") or {})
                token_resp = {
                    "access_token": data.get("access_token"),
                    "refresh_token": authed_user.get("refresh_token") or data.get("refresh_token"),
                    "token_type": data.get("token_type"),
                    "scope": data.get("scope"),
                    "team": data.get("team"),
                    "authed_user": authed_user,
                    "created_at": int(time.time()),
                }
        elif provider == "hubspot":
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    p.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": redirect_uri,
                        "code": code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                data = resp.json()
                token_resp = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": data.get("expires_in"),
                    "token_type": data.get("token_type"),
                    "created_at": int(time.time()),
                }
        elif provider == "jira":
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    p.token_url,
                    json={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                token_resp = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": data.get("expires_in"),
                    "token_type": data.get("token_type"),
                    "created_at": int(time.time()),
                }
        elif provider == "google":
            async with AsyncOAuth2Client(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            ) as client:
                data = await client.fetch_token(
                    "https://oauth2.googleapis.com/token",
                    code=code,
                    grant_type="authorization_code",
                )
                token_resp = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": data.get("expires_in"),
                    "id_token": data.get("id_token"),
                    "token_type": data.get("token_type"),
                    "created_at": int(time.time()),
                }
        elif provider == "microsoft":
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    p.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                data = resp.json()
                token_resp = {
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": data.get("expires_in"),
                    "token_type": data.get("token_type"),
                    "created_at": int(time.time()),
                }
        else:
            raise ValueError("unsupported_provider")

        # Persist tokens per-tenant
        # Common format
        save_payload = dict(token_resp)
        save_payload.update({
            "client_id": client_id,
            "client_secret": client_secret,
        })
        await self._tsm.set_secret(tenant_id, provider, "oauth_tokens", save_payload)

        # Slack MCP tool compatibility
        if provider == "slack":
            creds = {
                "access_token": token_resp.get("access_token"),
                "refresh_token": token_resp.get("refresh_token"),
                "expires_at": None,
                "client_id": client_id,
                "client_secret": client_secret,
            }
            await self._tsm.set_secret(tenant_id, "slack", "user_token_credentials", creds)

        return {"ok": True, "tenant_id": tenant_id, "provider": provider, "redirect_to": payload.get("redirect_to")}

    async def revoke(self, *, tenant_id: str, provider: str) -> Dict[str, Any]:
        """Best-effort revoke: delete stored oauth tokens and notify provider if supported."""
        prov = (provider or "").lower()
        if prov not in self._providers:
            raise ValueError("unsupported_provider")
        # Delete stored tokens for this provider
        try:
            await self._tsm.delete_secret(tenant_id, prov, "oauth_tokens")
        except Exception:
            pass
        # Provider-specific additional cleanup
        try:
            if prov == "slack":
                # Also clear user token credentials to force re-consent
                try:
                    await self._tsm.delete_secret(tenant_id, "slack", "user_token_credentials")
                except Exception:
                    pass
            elif prov == "shopify":
                # Clear generic credentials blob used by Shopify tool
                try:
                    await self._tsm.delete_secret(tenant_id, "shopify", "credentials")
                except Exception:
                    pass
        except Exception:
            pass
        # Optional: Call provider revoke endpoints if they exist (best-effort, not required)
        # For now we just return ok
        return {"ok": True}
