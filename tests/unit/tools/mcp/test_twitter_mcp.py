"""
Unit tests for Twitter (X) MCP Tool.
"""

import pytest
from unittest.mock import patch

from src.tools.mcp.mcp_twitter import MCPTwitterTool
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
        self._json = json_body or {"data": {"id": "1", "text": "hi"}}
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


@pytest.fixture
def tool():
    return MCPTwitterTool()


@pytest.mark.asyncio
async def test_get_tweet_success(tool: MCPTwitterTool):
    with patch.object(tool, '_get_twitter_headers', return_value={"Authorization": "Bearer x"}):
        resp = _Resp(200, json_body={"data": {"id": "123", "text": "hello"}})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._execute_operation("t1", "get_tweet", {"tweet_id": "123"})
            assert isinstance(result, MCPToolResult)
            assert result.success is True
            assert result.data["data"]["id"] == "123"


@pytest.mark.asyncio
async def test_create_tweet_success(tool: MCPTwitterTool):
    with patch.object(tool, '_get_twitter_headers', return_value={"Authorization": "Bearer x"}):
        resp = _Resp(200, json_body={"data": {"id": "999", "text": "posted"}})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._execute_operation("t1", "create_tweet", {"text": "posted"})
            assert result.success is True
            assert result.data["data"]["id"] == "999"


@pytest.mark.asyncio
async def test_unauthorized_raises(tool: MCPTwitterTool):
    with patch.object(tool, '_get_twitter_headers', return_value={"Authorization": "Bearer x"}):
        with patch.object(tool, '_make_request', side_effect=InvalidCredentialsError("Unauthorized")):
            with pytest.raises(InvalidCredentialsError):
                await tool._execute_operation("t1", "get_tweet", {"tweet_id": "123"})


