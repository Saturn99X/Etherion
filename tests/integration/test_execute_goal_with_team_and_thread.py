import os
import json
import pytest
from httpx import AsyncClient

from src.auth.jwt import create_access_token
from src.database.db import get_session
from src.database.models import Tenant, User, Job


@pytest.mark.asyncio
async def test_execute_goal_with_team_and_thread_metadata(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "jwt-test-secret")
    os.environ.setdefault("SECRET_KEY", "server-secret")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "dev-proj")

    from src.etherion_ai.app import create_app

    # Seed tenant+user
    sess = get_session()
    try:
        tenant = Tenant(name="T2", subdomain="t2", admin_email="t2@example.com")
        sess.add(tenant)
        sess.commit(); sess.refresh(tenant)
        user = User(user_id="u-2", tenant_id=tenant.id, email="u2@example.com")
        sess.add(user); sess.commit(); sess.refresh(user)
    finally:
        sess.close()

    token = create_access_token({"sub": "u-2", "email": "u2@example.com", "tenant_id": tenant.id})
    app = create_app()

    mutation = """
    mutation Exec($input: GoalInput!) {
      executeGoal(goal_input: $input) { success job_id status message }
    }
    """
    thread_id = "thread-abc123"
    team_id = "team_marketing"

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": mutation,
                "variables": {
                    "input": {
                        "goal": "Draft a welcome email",
                        "userId": "u-2",
                        "agentTeamId": team_id,
                        "threadId": thread_id,
                        "plan_mode": True,
                        "search_force": False,
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]["executeGoal"]
        assert data["success"] is True
        job_id = data["job_id"]
        assert job_id

    # Verify job metadata retained fields
    sess = get_session()
    try:
        job = sess.query(Job).filter(Job.job_id == job_id).first()
        assert job is not None
        md = job.get_job_metadata() if hasattr(job, "get_job_metadata") else (job.job_metadata or {})
        assert isinstance(md, dict)
        assert md.get("agent_team_id") == team_id
        assert md.get("thread_id") == thread_id
    finally:
        sess.close()


@pytest.mark.asyncio
async def test_execute_goal_with_provider_model_metadata(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "jwt-test-secret")
    os.environ.setdefault("SECRET_KEY", "server-secret")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "dev-proj")

    from src.etherion_ai.app import create_app
    from src.etherion_ai.graphql_schema import mutations as gql_mutations

    # Seed tenant+user
    sess = get_session()
    try:
        tenant = Tenant(name="T3", subdomain="t3", admin_email="t3@example.com")
        sess.add(tenant)
        sess.commit(); sess.refresh(tenant)
        user = User(user_id="u-3", tenant_id=tenant.id, email="u3@example.com")
        sess.add(user); sess.commit(); sess.refresh(user)
    finally:
        sess.close()

    # Avoid spinning up real orchestration/LLM in background task
    async def _noop_run(job_id: str, goal_description: str, user_id: int, tenant_id: int) -> None:
        return None

    monkeypatch.setattr(gql_mutations, "_run_orchestration_with_error_handling", _noop_run, raising=False)

    token = create_access_token({"sub": "u-3", "email": "u3@example.com", "tenant_id": tenant.id})
    app = create_app()

    mutation = """
    mutation Exec($input: GoalInput!) {
      executeGoal(goal_input: $input) { success job_id status message }
    }
    """
    provider = "vertex"
    model = "gemini-1.5-flash"

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": mutation,
                "variables": {
                    "input": {
                        "goal": "Draft a summary",
                        "userId": "u-3",
                        "provider": provider,
                        "model": model,
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]["executeGoal"]
        assert data["success"] is True
        job_id = data["job_id"]
        assert job_id

    # Verify provider/model preserved in job metadata and input_data
    sess = get_session()
    try:
        job = sess.query(Job).filter(Job.job_id == job_id).first()
        assert job is not None

        md = job.get_job_metadata() if hasattr(job, "get_job_metadata") else (job.job_metadata or {})
        assert isinstance(md, dict)
        assert md.get("provider") == provider
        assert md.get("model") == model

        try:
            input_data = job.get_input_data() if hasattr(job, "get_input_data") else (job.input_data or {})
        except Exception:
            input_data = job.input_data if hasattr(job, "input_data") else {}
        if isinstance(input_data, dict):
            assert input_data.get("provider") == provider
            assert input_data.get("model") == model
    finally:
        sess.close()
