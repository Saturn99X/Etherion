"""
Unit tests for Google Drive MCP Tool (upload only).

Covers:
- Upload from raw bytes with provided name/mime_type
- Upload from file_path with derived name and guessed mime_type
- Validation errors: both file_path and content, missing name for bytes
- HTTP error handling (401 → InvalidCredentialsError)
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from unittest.mock import MagicMock, patch

from src.tools.mcp.mcp_google_drive import MCPGoogleDriveTool
from src.tools.mcp.base_mcp_tool import (
    MCPToolResult,
    InvalidCredentialsError,
    ValidationError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def drive_tool() -> MCPGoogleDriveTool:
    return MCPGoogleDriveTool()


class _AsyncContext:
    def __init__(self, resp: Any) -> None:
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _MockResponse:
    def __init__(self, status: int = 200, headers: dict | None = None, json_body: dict | None = None, text_body: str | None = None) -> None:
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._json = json_body or {"id": "file_123", "name": "upload.txt"}
        self._text = text_body or json.dumps(self._json)

    async def json(self):
        return self._json

    async def text(self):
        return self._text


class _MockSession:
    def __init__(self, response: _MockResponse) -> None:
        self._response = response

    def post(self, *args, **kwargs):
        return _AsyncContext(self._response)


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.asyncio
async def test_upload_file_from_bytes_success(drive_tool: MCPGoogleDriveTool):
    with patch.object(drive_tool, '_get_drive_headers', return_value={"Authorization": "Bearer token"}):
        mock_resp = _MockResponse(status=200, json_body={"id": "file_abc", "name": "report.pdf"})
        with patch.object(drive_tool, '_get_session', return_value=_MockSession(mock_resp)):
            result = await drive_tool._handle_upload_file(
                {"Authorization": "Bearer token"},
                {
                    "name": "report.pdf",
                    "mime_type": "application/pdf",
                    "content": b"%PDF-1.4...",
                },
            )
            assert isinstance(result, MCPToolResult)
            assert result.success is True
            assert result.data["id"] == "file_abc"
            assert result.data["name"] == "report.pdf"


@pytest.mark.asyncio
async def test_upload_file_from_path_success(tmp_path: Path, drive_tool: MCPGoogleDriveTool):
    file_path = tmp_path / "hello.txt"
    file_path.write_text("hello world")

    with patch.object(drive_tool, '_get_drive_headers', return_value={"Authorization": "Bearer token"}):
        mock_resp = _MockResponse(status=200, json_body={"id": "file_xyz", "name": "hello.txt"})
        with patch.object(drive_tool, '_get_session', return_value=_MockSession(mock_resp)):
            result = await drive_tool._handle_upload_file(
                {"Authorization": "Bearer token"},
                {
                    "file_path": str(file_path),
                    # name omitted to test derivation from path
                },
            )
            assert result.success is True
            assert result.data["id"] == "file_xyz"
            assert result.data["name"] == "hello.txt"


def test_upload_file_validation_both_params(drive_tool: MCPGoogleDriveTool):
    with pytest.raises(ValidationError):
        # Call handler directly to validate mutual exclusivity
        asyncio.get_event_loop().run_until_complete(
            drive_tool._handle_upload_file(
                {"Authorization": "Bearer token"},
                {"file_path": "/tmp/a.txt", "content": b"abc"},
            )
        )


def test_upload_file_validation_missing_name_for_bytes(drive_tool: MCPGoogleDriveTool):
    with pytest.raises(ValidationError):
        asyncio.get_event_loop().run_until_complete(
            drive_tool._handle_upload_file(
                {"Authorization": "Bearer token"},
                {"content": b"abc"},
            )
        )


@pytest.mark.asyncio
async def test_upload_file_unauthorized_raises(drive_tool: MCPGoogleDriveTool):
    with patch.object(drive_tool, '_get_drive_headers', return_value={"Authorization": "Bearer token"}):
        mock_resp = _MockResponse(status=401, headers={"Content-Type": "application/json"}, json_body={"error": {"message": "Invalid Credentials"}})
        with patch.object(drive_tool, '_get_session', return_value=_MockSession(mock_resp)):
            with pytest.raises(InvalidCredentialsError):
                await drive_tool._handle_upload_file(
                    {"Authorization": "Bearer token"},
                    {"name": "x.txt", "content": b"x"},
                )


