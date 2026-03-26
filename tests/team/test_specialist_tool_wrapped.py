import json
import pytest

from src.services.team_orchestrator import TeamOrchestrator


class StubRuntime:
    def __init__(self, mode: str):
        self.mode = mode

    async def ainvoke(self, payload):
        if self.mode == "THINK":
            return {"output": "thinking specialist..."}
        actions = {
            "actions": [
                {"type": "tool", "name": "Spec1", "input": {"instruction": "do X"}},
                {"type": "finish"},
            ]
        }
        return {"output": json.dumps(actions)}


@pytest.mark.asyncio
async def test_specialist_wrapped_as_tool_executes(monkeypatch):
    orch = TeamOrchestrator(team_id="at_wrap", tenant_id=1, user_id=7)

    async def _fake_load(cfg):
        return {
            "agent_team_id": "at_wrap",
            "max_iterations": 2,
            "specialist_agents": [{"agent_id": "ca_1", "name": "Spec1", "description": "Spec"}],
            "approved_tools": [],
            **cfg,
        }

    monkeypatch.setattr(orch, "_load_team_config", _fake_load)

    async def _fake_user_ctx():
        return {"personality": {"preferred_tone": "test"}}

    monkeypatch.setattr(orch, "_load_user_personality_context", _fake_user_ctx)

    class FakeExec:
        async def execute(self, instruction: str):
            return {"output": f"Ran: {instruction}", "success": True}

    class FakeLoader:
        def create_agent_executor(self, agent_config, tenant_id, job_id):
            return FakeExec()

    import src.services.team_orchestrator as tor
    monkeypatch.setattr(tor, "get_agent_loader", lambda: FakeLoader())

    import src.core.redis as core_redis

    async def _fake_publish(job_id, event_data=None):
        return None

    async def _fake_cancel(job_id):
        return False

    monkeypatch.setattr(core_redis, "publish_execution_trace", _fake_publish)
    monkeypatch.setattr(core_redis, "is_job_cancelled", _fake_cancel)

    def _fake_build_runtime_from_config(cfg):
        mode = (cfg.get("execution_context", {}) or {}).get("llm_mode", "THINK")
        return StubRuntime(mode)

    monkeypatch.setattr(tor, "build_runtime_from_config", _fake_build_runtime_from_config)

    result = await orch.execute_2n_plus_1_loop(goal="Do specialist work", team_config={"job_id": "job_sw"})
    obs = result.get("observations") or []
    kinds = [o.get("type") for o in obs]
    assert "tool_result" in kinds
    assert "finish" in kinds
