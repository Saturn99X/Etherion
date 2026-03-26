"""
Google Drive MCP Tool - Upload Only (Production-Ready)

Implements secure file upload to Google Drive using OAuth 2.0 access tokens
with automatic refresh via refresh_token. Uses multipart/related upload type
for small-to-medium files. Designed to align with EnhancedMCPTool patterns
for rate limiting, retries, and structured error handling.

References (official docs):
- Drive API: https://developers.google.com/drive/api/v3/reference/files/create
- Upload types: https://developers.google.com/drive/api/guides/manage-uploads
- OAuth2 token refresh: https://developers.google.com/identity/protocols/oauth2

Author: Etherion AI Platform Team
Version: 1.0.0
"""

import asyncio
import json
import logging
import mimetypes
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aiohttp

from .base_mcp_tool import (
    EnhancedMCPTool,
    MCPToolResult,
    RateLimitConfig,
    RetryConfig,
    CircuitBreakerConfig,
    InvalidCredentialsError,
    ValidationError,
    RateLimitError,
    NetworkError,
    AuthType,
    HttpMethod,
    MCPToolError,
)


logger = logging.getLogger(__name__)


# =====================================================================================
# CREDENTIALS MODEL
# =====================================================================================


@dataclass
class GoogleDriveCredentials:
    """Google Drive OAuth 2.0 credentials with refresh support."""

    access_token: str
    refresh_token: str
    client_id: str
    client_secret: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: Optional[Any] = None
    expires_at: Optional[datetime] = None
    expires_in: int = 3600

    def needs_refresh(self) -> bool:
        """Refresh if within 5 minutes of expiration or missing expiry."""
        if not self.expires_at:
            return True
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        return datetime.utcnow() >= self.expires_at

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoogleDriveCredentials":
        exp = data.get("expires_at")
        expires_at: Optional[datetime]
        if isinstance(exp, str) and exp:
            # ISO8601
            expires_at = datetime.fromisoformat(exp)
        elif isinstance(exp, datetime):
            expires_at = exp
        else:
            expires_at = None

        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            scopes=data.get("scopes"),
            expires_at=expires_at,
            expires_in=int(data.get("expires_in", 3600)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token_uri": self.token_uri,
            "scopes": self.scopes,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "expires_in": self.expires_in,
        }


# =====================================================================================
# GOOGLE DRIVE MCP TOOL (UPLOAD ONLY)
# =====================================================================================


class MCPGoogleDriveTool(EnhancedMCPTool):
    """
    Production-ready Google Drive MCP Tool with upload capability.

    Operations:
      - upload_file: Upload a file (from bytes or file_path) to Drive.

    Usage:
        tool = MCPGoogleDriveTool()
        result = await tool.execute(
            tenant_id="tenant_123",
            operation="upload_file",
            params={
                "name": "report.pdf",
                "mime_type": "application/pdf",
                "content": b"...bytes...",
                # or "file_path": "/path/to/report.pdf",
                # optional "parent_folder_id": "<folderId>",
            },
        )
    """

    # API endpoints
    DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
    UPLOAD_ENDPOINT = (
        "https://www.googleapis.com/upload/drive/v3/files"
    )  # add params: uploadType=multipart

    # Conservative defaults
    DEFAULT_RATE_LIMIT_CONFIG = RateLimitConfig(
        requests_per_second=8.0,
        requests_per_minute=400.0,
        requests_per_hour=20000.0,
        burst_size=10,
    )

    DEFAULT_RETRY_CONFIG = RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
    )

    DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=2,
        timeout=60.0,
        half_open_max_calls=1,
    )

    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ) -> None:
        super().__init__(
            name="mcp_google_drive",
            description="Google Drive upload tool (multipart upload)",
            auth_type=AuthType.OAUTH2_AUTHORIZATION_CODE,
            base_url=self.DRIVE_API_BASE,
            rate_limit_config=rate_limit_config or self.DEFAULT_RATE_LIMIT_CONFIG,
            retry_config=retry_config or self.DEFAULT_RETRY_CONFIG,
            circuit_breaker_config=circuit_breaker_config or self.DEFAULT_CIRCUIT_BREAKER_CONFIG,
            timeout=60.0,
        )

        # Credential caches per tenant
        self._credentials_cache: Dict[str, GoogleDriveCredentials] = {}

    # =============================== Validation ===============================
    def _get_operation_schema(self, operation: str) -> Optional[Dict[str, Dict[str, Any]]]:
        if operation == "upload_file":
            return {
                "name": {"required": False, "type": str, "max_length": 255},
                "mime_type": {"required": False, "type": str, "max_length": 200},
                "file_path": {"required": False, "type": str, "max_length": 4096},
                "content": {"required": False, "type": (bytes,)},
                "parent_folder_id": {"required": False, "type": str, "max_length": 256},
            }
        return None

    def _is_write_operation(self, operation: str, params: Dict[str, Any]) -> bool:
        op = (operation or "").lower()
        return (op == "upload_file") or super()._is_write_operation(operation, params)

    # =============================== Exec Router ===============================
    async def _execute_operation(self, tenant_id: str, operation: str, params: Dict[str, Any]) -> MCPToolResult:
        try:
            if operation == "upload_file":
                headers = await self._get_drive_headers(tenant_id)
                return await self._handle_upload_file(headers, params)

            raise ValidationError(f"Unsupported operation: {operation}")

        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise InvalidCredentialsError(f"Google Drive authentication failed: {e}")
            elif e.status == 429:
                retry_after = int(e.headers.get("Retry-After", "60"))
                raise RateLimitError("Google Drive rate limit exceeded", retry_after=retry_after)
            elif e.status >= 500:
                raise NetworkError(f"Google Drive server error: {e}")
            else:
                raise MCPToolError(f"Google Drive API error: HTTP {e.status}")
        except Exception as e:
            logger.error(f"Google Drive operation {operation} failed: {e}")
            raise

    # =============================== Credentials ===============================
    async def _get_drive_headers(self, tenant_id: str) -> Dict[str, str]:
        creds = await self._get_credentials_with_refresh(tenant_id)
        return {"Authorization": f"Bearer {creds.access_token}"}

    async def _get_credentials_with_refresh(self, tenant_id: str) -> GoogleDriveCredentials:
        # Cache first
        creds = self._credentials_cache.get(tenant_id)
        if creds and not creds.needs_refresh():
            return creds

        # Load from secrets
        try:
            creds_data = await self.secrets_manager.get_secret(
                tenant_id=tenant_id,
                service_name="google_drive",
                key_type="oauth_tokens",
            )
            if not creds_data or not isinstance(creds_data, dict) or not creds_data.get("access_token"):
                creds_data = await self.secrets_manager.get_secret(
                    tenant_id=tenant_id,
                    service_name="google_drive",
                    key_type="oauth_credentials",
                )
        except Exception as e:
            raise InvalidCredentialsError(f"Google Drive credentials not found: {e}")

        creds = GoogleDriveCredentials.from_dict(creds_data)

        # Refresh if needed
        if creds.needs_refresh():
            creds = await self._refresh_google_token(tenant_id, creds)
            # Persist
            await self.secrets_manager.set_secret(
                tenant_id=tenant_id,
                service_name="google_drive",
                key_type="oauth_tokens",
                secret_value=creds.to_dict(),
            )

        self._credentials_cache[tenant_id] = creds
        return creds

    async def _refresh_google_token(self, tenant_id: str, creds: GoogleDriveCredentials) -> GoogleDriveCredentials:
        """Refresh OAuth token using refresh_token."""
        if not creds.refresh_token:
            raise InvalidCredentialsError("Missing refresh_token for Google Drive")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }

        session = await self._get_session()
        try:
            async with session.post(creds.token_uri, data=payload) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise InvalidCredentialsError(f"Token refresh failed: HTTP {response.status} {text[:200]}")

                token_json = await response.json()
                new_access = token_json.get("access_token")
                expires_in = int(token_json.get("expires_in", 3600))
                if not new_access:
                    raise InvalidCredentialsError("Token refresh did not return access_token")

                creds.access_token = new_access
                creds.expires_in = expires_in
                creds.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                # refresh_token may be omitted; if present update
                if token_json.get("refresh_token"):
                    creds.refresh_token = token_json["refresh_token"]

                logger.info(f"Refreshed Google Drive token for tenant {tenant_id}")
                return creds
        except aiohttp.ClientError as e:
            raise NetworkError(f"Network error refreshing token: {e}")

    # =============================== Handlers ===============================
    async def _handle_upload_file(self, headers: Dict[str, str], params: Dict[str, Any]) -> MCPToolResult:
        """
        Upload a file to Google Drive using multipart/related.

        Required:
          - Either 'file_path' or 'content' (bytes)
        Optional:
          - 'name': file name (derived from file_path if not provided)
          - 'mime_type': MIME type (auto-guessed if not provided)
          - 'parent_folder_id': parent folder ID
        """
        # Validate exclusive input
        has_path = bool(params.get("file_path"))
        has_bytes = params.get("content") is not None
        if has_path == has_bytes:
            # either both provided or none
            raise ValidationError("Provide exactly one of 'file_path' or 'content'")

        file_name: Optional[str] = params.get("name")
        file_path: Optional[str] = params.get("file_path")
        mime_type: Optional[str] = params.get("mime_type")
        parent_folder_id: Optional[str] = params.get("parent_folder_id")

        # Derive name and mime type if needed
        content_bytes: bytes
        if has_path:
            if not os.path.isfile(file_path):  # type: ignore[arg-type]
                raise ValidationError("'file_path' does not point to a file")
            if file_name is None:
                file_name = os.path.basename(file_path)  # type: ignore[arg-type]
            if not mime_type:
                mime_guess, _ = mimetypes.guess_type(file_name)
                mime_type = mime_guess or "application/octet-stream"
            with open(file_path, "rb") as f:  # deterministic resource mgmt
                content_bytes = f.read()
        else:
            content_bytes = params["content"]  # type: ignore[assignment]
            if not isinstance(content_bytes, (bytes, bytearray)):
                raise ValidationError("'content' must be bytes")
            if not file_name:
                raise ValidationError("'name' is required when using 'content'")
            if not mime_type:
                mime_guess, _ = mimetypes.guess_type(file_name)
                mime_type = mime_guess or "application/octet-stream"

        # Build metadata JSON
        metadata: Dict[str, Any] = {"name": file_name}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]

        # Build multipart body
        boundary = f"mcpdrive_{uuid.uuid4().hex}"
        delimiter = f"--{boundary}\r\n".encode()
        close_delim = f"--{boundary}--\r\n".encode()

        # Part 1: metadata
        meta_headers = (
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        )
        meta_payload = json.dumps(metadata, separators=(",", ":")).encode()

        # Part 2: file content
        file_headers = (
            f"Content-Type: {mime_type}\r\n\r\n".encode()
        )

        body = (
            delimiter
            + meta_headers
            + meta_payload
            + b"\r\n"
            + delimiter
            + file_headers
            + content_bytes
            + b"\r\n"
            + close_delim
        )

        url = f"{self.UPLOAD_ENDPOINT}?uploadType=multipart&fields=id,name,mimeType,parents,webViewLink"
        upload_headers = {
            **headers,
            "Content-Type": f"multipart/related; boundary={boundary}",
        }

        # Execute request
        session = await self._get_session()
        async with session.post(url, headers=upload_headers, data=body) as resp:
            # Handle common errors explicitly
            if resp.status == 401:
                raise InvalidCredentialsError("Invalid or expired Google Drive access token")
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                raise RateLimitError("Google Drive rate limit exceeded", retry_after=retry_after)
            if resp.status >= 400:
                text = await resp.text()
                raise MCPToolError(
                    f"Google Drive upload failed: HTTP {resp.status} {text[:200]}",
                    error_code=f"HTTP_{resp.status}",
                )

            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                data = await resp.json()
            else:
                # Drive should return JSON; fallback to text for diagnostics
                data = {"text": await resp.text()}

            return MCPToolResult(success=True, data=data)


