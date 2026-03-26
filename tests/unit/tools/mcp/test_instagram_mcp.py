"""
Unit tests for Instagram MCP Tool.
"""

import pytest
from unittest.mock import patch

from src.tools.mcp.mcp_instagram import MCPInstagramTool, InstagramCredentials
from src.tools.mcp.base_mcp_tool import MCPToolResult, InvalidCredentialsError


class _Ctx:
    def __init__(self, resp):
        self._resp = resp
    async def __aenter__(self):
        return self._resp
    async def __aexit__(self, *args):
        return False


class _Resp:
    def __init__(self, status=200, headers=None, json_body=None):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._json = json_body or {"id": "1784", "username": "acct"}
    async def json(self):
        return self._json
    async def text(self):
        import json
        return json.dumps(self._json)


class _Session:
    def __init__(self, resp):
        self._resp = resp
    def request(self, *args, **kwargs):
        return _Ctx(self._resp)
    def get(self, *args, **kwargs):
        return _Ctx(self._resp)


@pytest.fixture
def tool():
    return MCPInstagramTool()


@pytest.mark.asyncio
async def test_get_user_profile_success(tool: MCPInstagramTool):
    # Patch token retrieval
    with patch.object(tool, '_get_valid_access_token', return_value="token"):
        resp = _Resp(200, json_body={"id": "1", "username": "test"})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._execute_operation("t1", "get_user_profile", {"user_id": "1"})
            assert isinstance(result, MCPToolResult)
            assert result.success is True
            assert result.data["username"] == "test"


@pytest.mark.asyncio
async def test_create_media_container_success(tool: MCPInstagramTool):
    with patch.object(tool, '_get_valid_access_token', return_value="token"):
        resp = _Resp(200, json_body={"id": "creation_1"})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._execute_operation("t1", "create_media_container", {"user_id": "1", "image_url": "https://example.com/i.jpg", "caption": "hi"})
            assert result.success is True
            assert result.data["id"] == "creation_1"


@pytest.mark.asyncio
async def test_refresh_failure_raises(tool: MCPInstagramTool):
    creds = InstagramCredentials(access_token="bad", expires_in=5184000)
    with patch.object(tool, '_refresh_long_lived_token', side_effect=InvalidCredentialsError("bad token")):
        with patch.object(tool.secrets_manager, 'get_secret', return_value=creds.to_dict()):
            with pytest.raises(InvalidCredentialsError):
                await tool._get_valid_access_token("t1")


