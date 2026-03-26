def test_tool_registry_tool_lists_tools(monkeypatch):
    import src.tools.tool_registry_tool as tr
    from src.database.models import ToolStatus

    fake_registry = {
        "tool_a": {
            "description": "desc a",
            "status": ToolStatus.STABLE,
            "category": "utility",
            "requires_auth": False,
            "documentation_url": None,
            "version": "1.0",
        },
        "tool_b": {
            "description": "desc b",
            "status": ToolStatus.BETA,
            "category": "research",
            "requires_auth": True,
            "documentation_url": "https://example.com",
            "version": None,
        },
    }

    class _FakeToolManager:
        def get_tool_registry_info(self):
            return {"registry": fake_registry}

    monkeypatch.setattr(tr, "get_tool_manager", lambda: _FakeToolManager())

    # tool_registry_tool is a LangChain StructuredTool; call via invoke()
    res = tr.tool_registry_tool.invoke({"query": "tool", "include_beta": True, "limit": 10})
    assert res["count"] == 2
    assert res["tools"][0]["name"] == "tool_a"
    assert res["tools"][1]["name"] == "tool_b"
