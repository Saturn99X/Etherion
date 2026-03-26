"""
Unit tests for Reddit MCP Tool.
"""

import pytest
from unittest.mock import patch

from src.tools.mcp.mcp_reddit import MCPRedditTool
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
        self._json = json_body or {"name": "u/test"}
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
    return MCPRedditTool()


@pytest.mark.asyncio
async def test_get_user_info_success(tool: MCPRedditTool):
    with patch.object(tool, '_get_reddit_headers', return_value={"Authorization": "bearer x", "User-Agent": "ua"}):
        resp = _Resp(200, json_body={"name": "u/etherion"})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._execute_operation("t1", "get_user_info", {})
            assert isinstance(result, MCPToolResult)
            assert result.success is True
            assert result.data["name"] == "u/etherion"


@pytest.mark.asyncio
async def test_submit_post_success(tool: MCPRedditTool):
    with patch.object(tool, '_get_reddit_headers', return_value={"Authorization": "bearer x", "User-Agent": "ua"}):
        resp = _Resp(200, json_body={"json": {"data": {"url": "https://reddit.com/r/test"}}})
        with patch.object(tool, '_get_session', return_value=_Session(resp)):
            result = await tool._execute_operation("t1", "submit_post", {"subreddit": "test", "title": "hello", "kind": "self", "text": "body"})
            assert result.success is True


@pytest.mark.asyncio
async def test_unauthorized_raises(tool: MCPRedditTool):
    with patch.object(tool, '_get_reddit_headers', return_value={"Authorization": "bearer x", "User-Agent": "ua"}):
        # Simulate _make_request raising InvalidCredentialsError
        with patch.object(tool, '_make_request', side_effect=InvalidCredentialsError("Unauthorized")):
            with pytest.raises(InvalidCredentialsError):
                await tool._execute_operation("t1", "get_user_info", {})


