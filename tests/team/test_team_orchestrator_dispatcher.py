import asyncio
import json
import types
import pytest

from src.services.team_orchestrator import TeamOrchestrator


class StubRuntime:
    def __init__(self, mode: str):
        self.mode = mode

    async def ainvoke(self, payload):
        # THINK returns natural language
        if self.mode == "THINK":
            return {"output": "thinking..."}
        # ACT returns a JSON Plan: run unified_research_tool then finish
        actions = {
            "actions": [
                {"type": "tool", "name": "unified_research_tool", "input": {"query": "hello", "enable_web": False}},
                {"type": "finish"},
            ]
        }
        return {"output": json.dumps(actions)}


@pytest.mark.asyncio
async def test_plan_invalid_falls_back_to_sequential_specialists(monkeypatch):
    orch = TeamOrchestrator(team_id="at_fallback", tenant_id=1, user_id=42)

    async def _fake_load(cfg):
        return {
            "agent_team_id": "at_fallback",
            "max_iterations": 1,
            "specialist_agents": [
                {"agent_id": "ca_1", "name": "Spec1"},
                {"agent_id": "ca_2", "name": "Spec2"},
            ],
            "approved_tools": [],
            **cfg,
        }

    monkeypatch.setattr(orch, "_load_team_config", _fake_load)
    monkeypatch.setattr(orch, "_load_user_personality_context", lambda: {"personality": {}})

    import src.core.redis as core_redis

    emitted = []

    async def _fake_publish(job_id, event_data=None):
        if isinstance(event_data, dict):
            emitted.append(event_data.get("type"))
        return None

    async def _fake_cancel(job_id):
        return False

    monkeypatch.setattr(core_redis, "publish_execution_trace", _fake_publish)
    monkeypatch.setattr(core_redis, "is_job_cancelled", _fake_cancel)

    import src.services.team_orchestrator as tor

    class _BadPlanRuntime:
        def __init__(self, mode: str):
            self.mode = mode

        async def ainvoke(self, payload):
            if self.mode == "THINK":
                return {"output": "thinking"}
            return {"output": "NOT JSON"}

    def _fake_build_runtime_from_config(cfg):
        mode = (cfg.get("execution_context", {}) or {}).get("llm_mode", "THINK")
        return _BadPlanRuntime(mode)

    monkeypatch.setattr(tor, "build_runtime_from_config", _fake_build_runtime_from_config)

    import src.services.team_orchestrator as tor_mod

    class _StubExec:
        async def execute(self, instruction: str):
            return {"output": f"ok:{instruction[:10]}"}

    class _StubLoader:
        def create_agent_executor(self, *args, **kwargs):
            return _StubExec()

        def load_agent_team(self, *args, **kwargs):
            return None

    monkeypatch.setattr(tor_mod, "get_agent_loader", lambda: _StubLoader())

    result = await orch.execute_2n_plus_1_loop(goal="Goal", team_config={"job_id": "job_fallback"})

    assert "PLAN_INVALID" in emitted or "PLAN_EMPTY" in emitted
    obs = result.get("observations") or []
    assert sum(1 for o in obs if o.get("type") == "specialist_result") >= 1


@pytest.mark.asyncio
async def test_dispatcher_executes_tool_and_finishes(monkeypatch):
    # Arrange minimal orchestrator with fake DB/config
    orch = TeamOrchestrator(team_id="at_test", tenant_id=1, user_id=42)

    # Avoid DB: stub _load_team_config to return our config
    async def _fake_load(cfg):
        return {
            "agent_team_id": "at_test",
            "max_iterations": 2,
            # These are injected later by AgentLoader wiring but we bypass with manual entries
            "specialist_agents": [{"agent_id": "ca_1", "name": "Spec1"}],
            "approved_tools": [{"name": "unified_research_tool", "instance": object()}],
            **cfg,
        }

    monkeypatch.setattr(orch, "_load_team_config", _fake_load)

    # Stub user personality context
    async def _fake_user_ctx():
        return {"personality": {"preferred_tone": "test"}}

    monkeypatch.setattr(orch, "_load_user_personality_context", _fake_user_ctx)

    # Patch unified_research_tool to return deterministic counts
    from src import tools as _tools_pkg
    import src.tools.unified_research_tool as urt

    def _fake_unified_research_tool(query: str, tenant_id: str, project_id=None, job_id=None, *, enable_web: bool = False):
        return {
            "project_results": [1, 2],
            "personal_results": [1],
            "web_results": [],
            "vector_results": [1, 2, 3],
        }

    monkeypatch.setattr(urt, "unified_research_tool", _fake_unified_research_tool)

    # Patch publish_execution_trace and is_job_cancelled to be no-ops
    import src.core.redis as core_redis

    async def _fake_publish(job_id, event_data=None):
        return None

    async def _fake_cancel(job_id):
        return False

    monkeypatch.setattr(core_redis, "publish_execution_trace", _fake_publish)
    monkeypatch.setattr(core_redis, "is_job_cancelled", _fake_cancel)

    # Patch build_runtime_from_config to provide StubRuntime depending on mode
    import src.services.team_orchestrator as tor

    def _fake_build_runtime_from_config(cfg):
        mode = (cfg.get("execution_context", {}) or {}).get("llm_mode", "THINK")
        return StubRuntime(mode)

    monkeypatch.setattr(tor, "build_runtime_from_config", _fake_build_runtime_from_config)

    # Act
    result = await orch.execute_2n_plus_1_loop(goal="Do research", team_config={"job_id": "job_test"})

    # Assert
    assert isinstance(result, dict)
    obs = result.get("observations") or []
    # Expect at least one tool_result and a finish observation
    kinds = [o.get("type") for o in obs]
    assert "tool_result" in kinds
    assert "finish" in kinds


@pytest.mark.asyncio
async def test_team_orchestrator_injects_llm_hints_from_job_metadata(monkeypatch):
    from src.database.db import session_scope
    from src.database.models import Tenant, User, Job, JobStatus

    provider = "vertex"
    model = "gemini-1.5-pro"
    job_id = "job_llm_meta"

    with session_scope() as session:
        tenant = Tenant(name="LLM Test", tenant_id="llm_tenant_1", subdomain="llm", admin_email="llm@example.com")
        session.add(tenant)
        session.commit(); session.refresh(tenant)

        user = User(user_id="llm-user", tenant_id=tenant.id, email="llm@example.com")
        session.add(user)
        session.commit(); session.refresh(user)

        job = Job(
            job_id=job_id,
            tenant_id=tenant.id,
            user_id=user.id,
            status=JobStatus.QUEUED,
            job_type="execute_goal",
        )
        job.set_job_metadata({"provider": provider, "model": model})
        session.add(job)
        session.commit()

    orch = TeamOrchestrator(team_id="at_hints", tenant_id=tenant.id, user_id=user.id)

    async def _fake_load(cfg):
        return {
            "agent_team_id": "at_hints",
            "max_iterations": 1,
            "approved_tools": [],
            "specialist_agents": [],
            **cfg,
        }

    monkeypatch.setattr(orch, "_load_team_config", _fake_load)

    async def _fake_user_ctx():
        return {"personality": {"preferred_tone": "test"}}

    monkeypatch.setattr(orch, "_load_user_personality_context", _fake_user_ctx)

    import src.services.team_orchestrator as tor

    captured_cfgs = []

    def _fake_build_runtime_from_config(cfg):
        captured_cfgs.append(cfg)
        mode = (cfg.get("execution_context", {}) or {}).get("llm_mode", "THINK")
        return StubRuntime(mode)

    monkeypatch.setattr(tor, "build_runtime_from_config", _fake_build_runtime_from_config)

    await orch.execute_2n_plus_1_loop(goal="Goal uses hinted model", team_config={"job_id": job_id})

    assert captured_cfgs
    assert any(
        (cfg.get("execution_context", {}) or {}).get("llm_provider") == provider
        and (cfg.get("execution_context", {}) or {}).get("llm_model") == model
        for cfg in captured_cfgs
    )
