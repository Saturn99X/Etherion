"""
Unit tests for HubSpot MCP Tool (contacts operations).

Covers:
- get_contact success
- create_contact success
- search_contacts success
- update_contact success
- delete_contact success
- validation errors
- unauthorized handling
"""

import asyncio
import json
from typing import Any

import pytest
from unittest.mock import patch

from src.tools.mcp.mcp_hubspot import MCPHubSpotTool
from src.tools.mcp.base_mcp_tool import (
    MCPToolResult,
    ValidationError,
    InvalidCredentialsError,
)


class _AsyncCtx:
    def __init__(self, resp: Any) -> None:
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Resp:
    def __init__(self, status: int = 200, headers: dict | None = None, json_body: dict | None = None):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._json = json_body or {"id": "123"}

    async def json(self):
        return self._json

    async def text(self):
        return json.dumps(self._json)


class _Session:
    def __init__(self, resp: _Resp):
        self._resp = resp

    def request(self, *args, **kwargs):
        return _AsyncCtx(self._resp)


@pytest.fixture
def tool() -> MCPHubSpotTool:
    return MCPHubSpotTool()


@pytest.mark.asyncio
async def test_get_contact_success(tool: MCPHubSpotTool):
    with patch.object(tool, '_get_hubspot_headers', return_value={"Authorization": "Bearer x"}):
        # Use base helper directly by mocking request pipeline
        resp = _Resp(200, json_body={"id": "1", "properties": {"email": "a@b.com"}})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._handle_get_contact({"Authorization": "Bearer x"}, {"contact_id": "1"})
            assert isinstance(result, MCPToolResult)
            assert result.success is True
            assert result.data["id"] == "1"


@pytest.mark.asyncio
async def test_create_contact_success(tool: MCPHubSpotTool):
    with patch.object(tool, '_get_hubspot_headers', return_value={"Authorization": "Bearer x"}):
        resp = _Resp(200, json_body={"id": "2"})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._handle_create_contact({"Authorization": "Bearer x"}, {"properties": {"email": "a@b.com"}})
            assert result.success is True
            assert result.data["id"] == "2"


@pytest.mark.asyncio
async def test_search_contacts_success(tool: MCPHubSpotTool):
    with patch.object(tool, '_get_hubspot_headers', return_value={"Authorization": "Bearer x"}):
        resp = _Resp(200, json_body={"results": [{"id": "1"}]})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._handle_search_contacts({"Authorization": "Bearer x"}, {"filters": [], "limit": 5})
            assert result.success is True
            assert "results" in result.data


@pytest.mark.asyncio
async def test_update_contact_success(tool: MCPHubSpotTool):
    with patch.object(tool, '_get_hubspot_headers', return_value={"Authorization": "Bearer x"}):
        resp = _Resp(200, json_body={"id": "1", "updated": True})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._handle_update_contact({"Authorization": "Bearer x"}, {"contact_id": "1", "properties": {"firstname": "A"}})
            assert result.success is True
            assert result.data["id"] == "1"


@pytest.mark.asyncio
async def test_delete_contact_success(tool: MCPHubSpotTool):
    with patch.object(tool, '_get_hubspot_headers', return_value={"Authorization": "Bearer x"}):
        resp = _Resp(200, json_body={"archived": True})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._handle_delete_contact({"Authorization": "Bearer x"}, {"contact_id": "1"})
            assert result.success is True
            assert result.data["archived"] is True


def test_validation_missing_contact_id(tool: MCPHubSpotTool):
    with pytest.raises(ValidationError):
        asyncio.get_event_loop().run_until_complete(
            tool._handle_get_contact({"Authorization": "x"}, {})
        )


@pytest.mark.asyncio
async def test_unauthorized_raises(tool: MCPHubSpotTool):
    with patch.object(tool, '_get_hubspot_headers', return_value={"Authorization": "Bearer x"}):
        # direct handler bypasses base error mapping; simulate via _make_request to trigger 401 mapping path
        # Here we simulate by patching _make_request to raise InvalidCredentialsError
        with patch.object(tool, '_make_request', side_effect=InvalidCredentialsError("Unauthorized")):
            with pytest.raises(InvalidCredentialsError):
                await tool._handle_get_contact({"Authorization": "Bearer x"}, {"contact_id": "1"})


