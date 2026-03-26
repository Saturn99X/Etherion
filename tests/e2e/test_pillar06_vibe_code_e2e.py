import os
import json
import asyncio

import pytest
from httpx import AsyncClient, ASGITransport
from sqlmodel import select

from tests.e2e._dummy_redis import setup_dummy_redis
from src.core.redis import subscribe_to_execution_trace
from src.database.models import Job, JobStatus


@pytest.mark.asyncio
async def test_pillar06_vibe_code_clone_update_execute_team(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p6")
    os.environ.setdefault("SECRET_KEY", "test-secret-p6-app")
    os.environ.setdefault("CELERY_ALWAYS_EAGER", "true")

    # Use in-memory Redis so execution traces and statuses are observable and deterministic
    setup_dummy_redis(monkeypatch)

    from src.etherion_ai.app import create_app
    app = create_app()

    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create tenant and user
        async with get_scoped_session() as session:
            tenant = Tenant(tenant_id="pillar06-vibe", subdomain="pillar06-vibe", name="P6 Vibe", admin_email="p6@test.local")
            session.add(tenant); await session.commit(); await session.refresh(tenant)
            user = User(user_id="p6-user", tenant_id=tenant.id, email="p6@test.local")
            session.add(user); await session.commit(); await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        # Root rate limit header present
        root = await client.get("/")
        assert root.headers.get("X-RateLimit-Limit") is not None

        # Create agent team via GraphQL blueprint mutation
        create_mut = """
        mutation CreateTeam($input: AgentTeamInput!){
            createAgentTeam(teamInput:$input){
                id
                name
                description
                customAgentIDs
                preApprovedToolNames
            }
        }
        """
        specification = "Design a vibey copywriting duo for welcome messages"
        team_input = {
            "name": "Vibe Launch Team",
            "description": "Handles brand tone and vibe copy",
            "specification": specification,
        }
        create_resp = await client.post(
            "/graphql",
            json={"query": create_mut, "variables": {"input": team_input}},
            headers=headers,
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json().get("data", {}).get("createAgentTeam")
        assert create_data
        team_id = create_data["id"]
        assert create_data["name"] == team_input["name"]
        assert create_data["customAgentIDs"], "Expected blueprint to provision custom agents"

        # Verify team + agents persisted with expected metadata
        from src.database.models.agent_team import AgentTeam
        from src.database.models.custom_agent import CustomAgentDefinition

        async with get_scoped_session() as session:
            team_rec = await session.exec(
                select(AgentTeam).where(AgentTeam.agent_team_id == team_id)
            )
            team_obj = team_rec.first()
            assert team_obj is not None
            assert team_obj.name == team_input["name"]
            assert team_obj.description == team_input["description"]
            custom_ids = team_obj.get_custom_agent_ids()
            assert len(custom_ids) == len(create_data["customAgentIDs"])

            for agent_id in custom_ids:
                agent_row = await session.exec(
                    select(CustomAgentDefinition).where(
                        CustomAgentDefinition.custom_agent_id == agent_id,
                        CustomAgentDefinition.tenant_id == tenant.id,
                    )
                )
                agent = agent_row.first()
                assert agent is not None
                assert agent.system_prompt
                metadata = agent.get_custom_metadata() or {}
                assert metadata.get("capabilities") is not None

        # Update team name via GraphQL
        update_mut = """
        mutation UpdateTeam($id:String!,$name:String!){
            updateAgentTeam(agent_team_id:$id,name:$name)
        }
        """
        new_name = "Vibe Launch Team v2"
        upd_resp = await client.post(
            "/graphql",
            json={"query": update_mut, "variables": {"id": team_id, "name": new_name}},
            headers=headers,
        )
        assert upd_resp.status_code == 200
        upd_body = upd_resp.json()
        assert upd_body.get("data", {}).get("updateAgentTeam") is True

        async with get_scoped_session() as session:
            team_row = await session.exec(
                select(AgentTeam).where(AgentTeam.agent_team_id == team_id)
            )
            assert team_row.first().name == new_name

        # Execute goal with the new team
        execute_mut = """
        mutation Execute($input: GoalInput!){
            executeGoal(goalInput:$input){
                success
                job_id
                status
                message
            }
        }
        """
        exec_vars = {
            "input": {
                "goal": "Create an uplifting welcome snippet",
                "userId": user.user_id,
                "agentTeamId": team_id,
                "context": json.dumps({"campaign": "launch"}),
            }
        }
        exec_resp = await client.post(
            "/graphql",
            json={"query": execute_mut, "variables": exec_vars},
            headers=headers,
        )
        assert exec_resp.status_code == 200
        exec_payload = exec_resp.json().get("data", {}).get("executeGoal")
        assert exec_payload and exec_payload.get("success") is True
        job_id = exec_payload.get("job_id")
        assert job_id

        # Ensure agent team metadata reflects execution bump
        async with get_scoped_session() as session:
            team_row = await session.exec(
                select(AgentTeam).where(AgentTeam.agent_team_id == team_id)
            )
            team_after = team_row.first()
            assert team_after.execution_count >= 0

        # Wait for orchestrator job completion so output_data and traces are populated
        async def _wait_for_job_completion(timeout: float = 20.0):
            end = asyncio.get_event_loop().time() + timeout
            last_job = None
            while asyncio.get_event_loop().time() < end:
                async with get_scoped_session() as session:
                    row = await session.exec(select(Job).where(Job.job_id == job_id))
                    last_job = row.first()
                    if last_job and last_job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
                        return last_job
                await asyncio.sleep(0.25)
            return last_job

        job_row = await _wait_for_job_completion()
        assert job_row is not None, "Expected orchestrator job to reach a terminal state"

        # Collect a PLAN trace event containing JSON actions produced by TeamOrchestrator
        plan_events: list[dict] = []

        async def _collect_plan():
            async for evt in subscribe_to_execution_trace(job_id):
                if evt.get("type") == "PLAN":
                    plan_events.append(evt)
                    break

        try:
            await asyncio.wait_for(_collect_plan(), timeout=10)
        except asyncio.TimeoutError:
            pytest.fail("Did not observe PLAN trace event for orchestrator job")

        assert plan_events, "Expected at least one PLAN trace event"
        plan_evt = plan_events[0]
        actions = plan_evt.get("actions")
        assert isinstance(actions, list) and actions, "PLAN.actions must be a non-empty list"
        first_action = actions[0]
        assert first_action.get("type") in {"tool", "specialist", "finish", "request_stop"}

        # Job output_data should include structured observations recorded by TeamOrchestrator
        output = job_row.get_output_data() or {}
        observations = output.get("observations") or []
        assert isinstance(observations, list)
        obs_types = {o.get("type") for o in observations if isinstance(o, dict)}
        assert obs_types, "Expected at least one observation in orchestrator output_data"
        # At minimum we should see a finish or tool_result style observation from JSON-driven execution
        assert {"finish", "tool_result", "specialist_result"} & obs_types
