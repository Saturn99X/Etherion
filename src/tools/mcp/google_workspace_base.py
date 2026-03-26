"""
Google Workspace Base for MCP tools.

Provides shared OAuth token resolution/refresh, scope validation, and HTTP helpers
for Google Workspace tools that extend EnhancedMCPTool.

Assumptions:
- Unified tokens are stored under provider "google" with key_type "oauth_tokens":
  await TenantSecretsManager().get_secret(tenant_id, "google", "oauth_tokens") -> dict
- Legacy fallbacks per-service (e.g., gmail, google_drive, calendar, docs, sheets, slides, forms, tasks, chat)
  are checked when unified provider creds are not found.

WHY: Centralize token handling and reduce duplication across Google Workspace tools.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from .base_mcp_tool import (
    EnhancedMCPTool,
    MCPToolResult,
    InvalidCredentialsError,
    RateLimitError,
    NetworkError,
)
from src.utils.secrets_manager import TenantSecretsManager
from src.services.silo_oauth_service import SiloOAuthService

logger = logging.getLogger(__name__)


@dataclass
class GoogleOAuthTokens:
    access_token: str
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    expires_in: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoogleOAuthTokens":
        exp = data.get("expires_at") or data.get("expiry")
        exp_dt: Optional[datetime]
        if isinstance(exp, str):
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            except Exception:
                exp_dt = None
        elif isinstance(exp, datetime):
            exp_dt = exp
        else:
            exp_dt = None
        scopes = data.get("scopes")
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            scopes=scopes,
            expires_at=exp_dt,
            expires_in=data.get("expires_in"),
        )

    def needs_refresh(self) -> bool:
        if not self.expires_at:
            return False  # If unknown, try using it and let API tell us; tools can refresh on 401
        # Refresh 5 minutes before expiry
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))


class GoogleWorkspaceBase(EnhancedMCPTool):
    """Base class for Google Workspace MCP tools."""

    # Default minimal Google vendor quota (overridden per tool if needed)
    _VENDOR_KEY = "google"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tsm = TenantSecretsManager()
        self._oauth = SiloOAuthService()
        # in-memory token cache per tenant
        self._token_cache: Dict[str, GoogleOAuthTokens] = {}

    # ------------------------ OAuth helpers ------------------------
    async def _get_google_tokens(self, tenant_id: str) -> Optional[GoogleOAuthTokens]:
        # Prefer unified provider creds
        try:
            data = await self.secrets_manager.get_secret(tenant_id, "google", "oauth_tokens")
            if isinstance(data, dict) and data.get("access_token"):
                return GoogleOAuthTokens.from_dict(data)
        except Exception:
            pass

        # Fallback to legacy per-service stores for backward compatibility
        legacy_services = [
            "gmail",
            "google_drive",
            "google_calendar",
            "google_docs",
            "google_sheets",
            "google_slides",
            "google_forms",
            "google_tasks",
            "google_chat",
        ]
        for svc in legacy_services:
            for key in ("oauth_tokens", "oauth_credentials"):
                try:
                    data = await self.secrets_manager.get_secret(tenant_id, svc, key)
                    if isinstance(data, dict) and data.get("access_token"):
                        return GoogleOAuthTokens.from_dict(data)
                except Exception:
                    continue
        return None

    async def _refresh_google_tokens(self, tenant_id: str, tokens: GoogleOAuthTokens) -> GoogleOAuthTokens:
        if not tokens.refresh_token or not tokens.client_id or not tokens.client_secret:
            # Cannot refresh; surface invalid creds
            raise InvalidCredentialsError("Missing refresh prerequisites for Google OAuth token")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "client_id": tokens.client_id,
            "client_secret": tokens.client_secret,
        }
        session = await self._get_session()
        async with session.post(tokens.token_uri, data=payload) as resp:
            if resp.status >= 400:
                txt = await resp.text()
                raise InvalidCredentialsError(f"Token refresh failed: HTTP {resp.status} {txt[:200]}")
            j = await resp.json()
            tokens.access_token = j.get("access_token", tokens.access_token)
            exp_in = int(j.get("expires_in", tokens.expires_in or 3600))
            tokens.expires_in = exp_in
            tokens.expires_at = datetime.utcnow() + timedelta(seconds=exp_in)
            if j.get("refresh_token"):
                tokens.refresh_token = j["refresh_token"]

        # Persist back to unified provider store
        try:
            await self.secrets_manager.set_secret(
                tenant_id=tenant_id,
                service_name="google",
                key_type="oauth_tokens",
                secret_value={
                    "access_token": tokens.access_token,
                    "refresh_token": tokens.refresh_token,
                    "client_id": tokens.client_id,
                    "client_secret": tokens.client_secret,
                    "token_uri": tokens.token_uri,
                    "scopes": tokens.scopes,
                    "expires_in": tokens.expires_in,
                    "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
                },
            )
        except Exception:
            # Best-effort persist
            pass
        return tokens

    async def _ensure_access_token(self, tenant_id: str, required_scopes: Optional[List[str]] = None) -> GoogleOAuthTokens:
        # Cache first
        t = self._token_cache.get(tenant_id)
        if not t:
            t = await self._get_google_tokens(tenant_id)
            if not t:
                # Offer one-click OAuth link with requested scopes
                url = await self._build_google_oauth_url(tenant_id, required_scopes or [])
                raise InvalidCredentialsError(
                    f"Google OAuth not configured for tenant; authorize: {url}")
            self._token_cache[tenant_id] = t

        # Scope preflight (best-effort; Google rarely returns granted scopes)
        if required_scopes:
            have = set((t.scopes or []))
            need = set(required_scopes)
            if need - have:
                url = await self._build_google_oauth_url(tenant_id, required_scopes)
                raise InvalidCredentialsError(
                    f"Missing Google scopes {sorted(list(need - have))}; authorize: {url}")

        # Refresh if expiring
        if t.needs_refresh():
            try:
                t = await self._refresh_google_tokens(tenant_id, t)
                self._token_cache[tenant_id] = t
            except InvalidCredentialsError:
                # Provide authorize URL as guidance
                url = await self._build_google_oauth_url(tenant_id, required_scopes or t.scopes or [])
                raise InvalidCredentialsError(
                    f"Google OAuth refresh failed; re-authorize: {url}")
        return t

    async def _auth_headers(self, tenant_id: str, required_scopes: Optional[List[str]] = None) -> Dict[str, str]:
        t = await self._ensure_access_token(tenant_id, required_scopes)
        return {"Authorization": f"Bearer {t.access_token}"}

    async def _build_google_oauth_url(self, tenant_id: str, scopes: List[str]) -> str:
        try:
            return await self._oauth.build_authorize_url(
                tenant_id=str(tenant_id), provider="google", scopes_override=scopes or None
            )
        except Exception:
            # Fallback to generic path if service unavailable
            return f"/oauth/silo/google/start?tenant_id={tenant_id}"

    # ------------------------ HTTP helper ------------------------
    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        session = await self._get_session()
        async with session.request(method, url, headers=headers, params=params, json=json_body, timeout=timeout or self.timeout) as resp:
            if resp.status == 401:
                raise InvalidCredentialsError("Google API authentication failed (401)")
            if resp.status == 429:
                ra = int(resp.headers.get("Retry-After", "60"))
                raise RateLimitError("Google API rate limit exceeded", retry_after=ra)
            if resp.status >= 500:
                raise NetworkError(f"Google API server error: HTTP {resp.status}")
            if resp.status >= 400:
                text = await resp.text()
                raise InvalidCredentialsError(f"Google API error: HTTP {resp.status} {text[:200]}")
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return await resp.json()
            return {"text": await resp.text()}
