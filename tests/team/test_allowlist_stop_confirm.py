import json
import pytest

from src.services.team_orchestrator import TeamOrchestrator


class StubRuntime:
    def __init__(self, mode: str, plan_actions):
        self.mode = mode
        self._plan_actions = plan_actions

    async def ainvoke(self, payload):
        if self.mode == "THINK":
            return {"output": "thinking..."}
        return {"output": json.dumps({"actions": self._plan_actions})}


@pytest.mark.asyncio
async def test_allowlist_denial_for_tool_and_specialist(monkeypatch):
    orch = TeamOrchestrator(team_id="at_acl", tenant_id=1, user_id=9)

    # Team has no approved tool and no specialists
    async def _fake_load(cfg):
        return {"agent_team_id": "at_acl", "max_iterations": 1, "approved_tools": [], "specialist_agents": [], **cfg}

    monkeypatch.setattr(orch, "_load_team_config", _fake_load)
    monkeypatch.setattr(orch, "_load_user_personality_context", lambda: {"personality": {}})

    import src.core.redis as core_redis

    async def _fake_publish(job_id, event_data=None):
        return None

    async def _fake_cancel(job_id):
        return False

    monkeypatch.setattr(core_redis, "publish_execution_trace", _fake_publish)
    monkeypatch.setattr(core_redis, "is_job_cancelled", _fake_cancel)

    actions = [
        {"type": "tool", "name": "not_allowed_tool", "input": {}},
        {"type": "specialist", "target_specialist_id": "ca_x", "input": {"instruction": "noop"}},
        {"type": "finish"},
    ]

    import src.services.team_orchestrator as tor
    monkeypatch.setattr(tor, "build_runtime_from_config", lambda cfg: StubRuntime(cfg.get("execution_context", {}).get("llm_mode", "THINK"), actions))

    result = await orch.execute_2n_plus_1_loop(goal="Test", team_config={"job_id": "job_acl"})
    obs = result.get("observations") or []
    msgs = [o.get("message") for o in obs if o.get("type") in ("error", "finish")]
    assert any("Tool 'not_allowed_tool' not allowed" in (m or "") for m in msgs)
    assert any("Specialist 'ca_x' not allowed" in (m or "") for m in msgs)
    assert any(o.get("type") == "finish" for o in obs)


@pytest.mark.asyncio
async def test_stop_mid_step(monkeypatch):
    orch = TeamOrchestrator(team_id="at_stop", tenant_id=1, user_id=9)

    async def _fake_load(cfg):
        return {"agent_team_id": "at_stop", "max_iterations": 1, "approved_tools": [{"name": "unified_research_tool", "instance": object()}], "specialist_agents": [], **cfg}

    monkeypatch.setattr(orch, "_load_team_config", _fake_load)
    monkeypatch.setattr(orch, "_load_user_personality_context", lambda: {"personality": {}})

    # Two tool actions; we will STOP after the first
    actions = [
        {"type": "tool", "name": "unified_research_tool", "input": {"query": "q", "enable_web": False}},
        {"type": "tool", "name": "unified_research_tool", "input": {"query": "q2", "enable_web": False}},
    ]

    import src.services.team_orchestrator as tor
    monkeypatch.setattr(tor, "build_runtime_from_config", lambda cfg: StubRuntime(cfg.get("execution_context", {}).get("llm_mode", "THINK"), actions))

    import src.tools.unified_research_tool as urt

    def _fake_unified(query: str, tenant_id: str, project_id=None, job_id=None, *, enable_web: bool = False):
        return {"project_results": [1], "personal_results": [], "web_results": [], "vector_results": []}

    monkeypatch.setattr(urt, "unified_research_tool", _fake_unified)

    import src.core.redis as core_redis
    state = {"calls": 0}

    async def _fake_cancel(job_id):
        state["calls"] += 1
        # Return True on second check (i.e., before second action)
        return state["calls"] >= 2

    async def _fake_publish(job_id, event_data=None):
        return None

    monkeypatch.setattr(core_redis, "is_job_cancelled", _fake_cancel)
    monkeypatch.setattr(core_redis, "publish_execution_trace", _fake_publish)

    result = await orch.execute_2n_plus_1_loop(goal="Test stop", team_config={"job_id": "job_stop"})
    obs = result.get("observations") or []
    # Expect only one tool_result before STOP kicks in
    assert sum(1 for o in obs if o.get("type") == "tool_result") == 1


@pytest.mark.asyncio
async def test_mcp_write_requires_confirm(monkeypatch):
    orch = TeamOrchestrator(team_id="at_mcp", tenant_id=1, user_id=9)

    class StubMCP:
        async def execute(self, tenant_id: str, operation: str, params: dict):
            # Treat any op starting with create/update/delete as write and require confirm_action
            if operation.lower().startswith(("create", "update", "delete")) and not params.get("confirm_action"):
                return {"success": False, "error_code": "CONFIRMATION_REQUIRED", "error_message": "Confirmation required for write operation"}
            return {"success": True, "data": {"ok": True}}

    async def _fake_load(cfg):
        return {
            "agent_team_id": "at_mcp",
            "max_iterations": 1,
            "approved_tools": [{"name": "mcp_stub", "instance": StubMCP()}],
            "specialist_agents": [],
            **cfg,
        }

    monkeypatch.setattr(orch, "_load_team_config", _fake_load)
    monkeypatch.setattr(orch, "_load_user_personality_context", lambda: {"personality": {}})

    actions = [
        {"type": "tool", "name": "mcp_stub", "input": {"operation": "create_item", "payload": {"x": 1}}},
        {"type": "finish"},
    ]

    import src.services.team_orchestrator as tor
    monkeypatch.setattr(tor, "build_runtime_from_config", lambda cfg: StubRuntime(cfg.get("execution_context", {}).get("llm_mode", "THINK"), actions))

    import src.core.redis as core_redis

    async def _fake_publish(job_id, event_data=None):
        return None

    async def _fake_cancel(job_id):
        return False

    monkeypatch.setattr(core_redis, "publish_execution_trace", _fake_publish)
    monkeypatch.setattr(core_redis, "is_job_cancelled", _fake_cancel)

    result = await orch.execute_2n_plus_1_loop(goal="Test mcp", team_config={"job_id": "job_mcp"})
    obs = result.get("observations") or []
    # The first observation should include tool_result with error_code CONFIRMATION_REQUIRED
    tr = next((o for o in obs if o.get("type") == "tool_result"), None)
    assert tr is not None
    r = tr.get("result") or {}
    assert (r.get("error_code") == "CONFIRMATION_REQUIRED") or (r.get("success") is False and "CONFIRMATION_REQUIRED" in json.dumps(r))
