"""
Google Workspace Vendor Adapter

Bridges vendored Google Workspace MCP modules with Etherion's security model:
- Uses TenantSecretsManager and SiloOAuthService for tenant-scoped OAuth tokens
- Builds googleapiclient service objects for vendor functions without writing secrets to disk
- Enforces Etherion invariants: confirm_action (at tool layer), quotas, rate limits, and audit will still come from EnhancedMCPTool users

This adapter intentionally avoids importing vendor modules at import time to prevent hard deps
on FastMCP. It only provides primitives for Etherion tools to gain full API coverage.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.utils.secrets_manager import TenantSecretsManager
from src.services.silo_oauth_service import SiloOAuthService

logger = logging.getLogger(__name__)


class MissingGoogleAuthorization(Exception):
    def __init__(self, authorize_url: str, message: str = "Google OAuth required"):
        self.authorize_url = authorize_url
        super().__init__(f"{message}. Authorize: {authorize_url}")


class GoogleWorkspaceVendorAdapter:
    TOKEN_URI = "https://oauth2.googleapis.com/token"

    def __init__(self, tenant_id: str):
        self.tenant_id = str(tenant_id)
        self._tsm = TenantSecretsManager()
        self._oauth = SiloOAuthService()

    async def _load_tokens(self) -> Optional[Dict[str, Any]]:
        # Prefer unified provider
        data = await self._tsm.get_secret(self.tenant_id, "google", "oauth_tokens")
        if isinstance(data, dict) and data.get("access_token"):
            return data
        # Legacy locations
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
                    d = await self._tsm.get_secret(self.tenant_id, svc, key)
                    if isinstance(d, dict) and d.get("access_token"):
                        return d
                except Exception:
                    continue
        return None

    async def _authorize_url(self, scopes: List[str]) -> str:
        try:
            return await self._oauth.build_authorize_url(
                tenant_id=self.tenant_id, provider="google", scopes_override=scopes or None
            )
        except Exception:
            return f"/oauth/silo/google/start?tenant_id={self.tenant_id}"

    async def get_service(self, service_name: str, version: str, required_scopes: List[str]) -> Any:
        tokens = await self._load_tokens()
        if not tokens or not tokens.get("access_token"):
            url = await self._authorize_url(required_scopes)
            raise MissingGoogleAuthorization(url)

        # Scope preflight (best-effort)
        token_scopes = tokens.get("scopes")
        if isinstance(token_scopes, str):
            token_scopes = [s.strip() for s in token_scopes.split() if s.strip()]
        if required_scopes and token_scopes:
            need = set(required_scopes) - set(token_scopes)
            if need:
                url = await self._authorize_url(required_scopes)
                raise MissingGoogleAuthorization(url, message=f"Missing scopes: {sorted(list(need))}")

        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri") or self.TOKEN_URI,
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            scopes=token_scopes or required_scopes or None,
        )
        # Note: googleapiclient handles refresh lazily; our tools also provide refresh flows
        service = build(service_name, version, credentials=creds, cache_discovery=False)
        return service

    # Convenience wrappers matching vendor service configs
    async def get_sheets(self, scopes: List[str]) -> Any:
        return await self.get_service("sheets", "v4", scopes)

    async def get_drive(self, scopes: List[str]) -> Any:
        return await self.get_service("drive", "v3", scopes)

    async def get_docs(self, scopes: List[str]) -> Any:
        return await self.get_service("docs", "v1", scopes)

    async def get_calendar(self, scopes: List[str]) -> Any:
        return await self.get_service("calendar", "v3", scopes)

    async def get_slides(self, scopes: List[str]) -> Any:
        return await self.get_service("slides", "v1", scopes)

    async def get_forms(self, scopes: List[str]) -> Any:
        return await self.get_service("forms", "v1", scopes)

    async def get_tasks(self, scopes: List[str]) -> Any:
        return await self.get_service("tasks", "v1", scopes)

    async def get_chat(self, scopes: List[str]) -> Any:
        return await self.get_service("chat", "v1", scopes)
