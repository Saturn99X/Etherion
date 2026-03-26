from unittest.mock import MagicMock


def test_tool_manager_on_demand_loading_function_tool(monkeypatch):
    from src.tools.tool_manager import ToolManager
    from src.database.models import ToolStatus

    tm = ToolManager()

    # Simulate a tool present in DB but not in in-memory registry
    tool_name = "fake_tool"
    tm._tool_registry.pop(tool_name, None)

    fake_tool_record = MagicMock()
    fake_tool_record.name = tool_name
    fake_tool_record.status = ToolStatus.STABLE
    fake_tool_record.is_custom_agent_executor = False

    fake_session = MagicMock()
    fake_session.query.return_value.filter.return_value.first.return_value = fake_tool_record

    class _FakeSessionScope:
        def __enter__(self):
            return fake_session

        def __exit__(self, exc_type, exc, tb):
            return False

    import src.tools.tool_manager as tm_mod

    monkeypatch.setattr(tm_mod, "session_scope", lambda: _FakeSessionScope())

    # Patch importlib for on-demand registration + instantiation
    calls = {"imported": []}

    def _fake_tool_fn(input_data):
        return {"ok": True, "input": input_data}

    class _FakeModule:
        fake_tool = staticmethod(_fake_tool_fn)

    real_import = tm_mod.importlib.import_module

    def _fake_import_module(name: str):
        calls["imported"].append(name)
        if name == "src.tools.fake_tool":
            return _FakeModule
        return real_import(name)

    monkeypatch.setattr(tm_mod.importlib, "import_module", _fake_import_module)

    inst = tm.get_tool_instance(tool_name=tool_name, tenant_id=1, job_id="job_1")
    assert callable(inst)
    assert inst({"x": 1})["ok"] is True
    assert "src.tools.fake_tool" in calls["imported"]
