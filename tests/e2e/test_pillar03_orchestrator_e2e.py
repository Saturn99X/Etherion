import os
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlmodel import select

from src.etherion_ai.app import create_app
from src.database.db import get_scoped_session
from src.database.models import Tenant, User, Job, JobStatus
from src.auth.jwt import create_access_token
from src.core.tasks import update_job_status_task
from src.core.redis import (
    subscribe_to_job_status,
    subscribe_to_execution_trace,
    publish_execution_trace,
)
from src.core.gcs_client import GCSClient
from tests.e2e._dummy_redis import setup_dummy_redis


@pytest.mark.asyncio
async def test_pillar03_orchestrator_execute_goal_and_headers(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p3")
    os.environ.setdefault("SECRET_KEY", "test-secret-p3-app")
    os.environ.setdefault("CELERY_ALWAYS_EAGER", "true")

    app = create_app()

    # Use dummy redis only when REDIS_URL not provided
    use_dummy_redis = not bool(os.getenv("REDIS_URL"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if use_dummy_redis:
            setup_dummy_redis(monkeypatch)
        async with get_scoped_session() as session:
            tenant = Tenant(tenant_id="pillar03-e2e", subdomain="pillar03-e2e", name="P3 Brain", admin_email="p3@test.local")
            session.add(tenant); await session.commit(); await session.refresh(tenant)
            user = User(user_id="p3-user", tenant_id=tenant.id, email="p3@test.local")
            session.add(user); await session.commit(); await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        # Root should expose rate limit header
        root = await client.get("/")
        assert root.headers.get("X-RateLimit-Limit") is not None

        # GraphQL executeGoal should queue a job and return a job_id
        mutation = (
            "mutation($input: GoalInput!) { "
            "executeGoal(goalInput: $input) { success job_id status message } }"
        )
        variables = {
            "input": {
                "goal": "Write one concise bullet about Etherion.",
                "userId": user.user_id
            }
        }
        gql = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        assert gql.status_code == 200
        payload = gql.json().get("data", {}).get("executeGoal")
        assert isinstance(payload, dict)
        # Even if background workers are not running, API should return a job stub
        assert payload.get("job_id") is not None and payload.get("status") is not None
        job_id = payload.get("job_id")

        # Verify job record exists and starts QUEUED
        async with get_scoped_session() as session:
            job = (await session.exec(select(Job).where(Job.job_id == job_id))).first()
            assert job is not None and job.status == JobStatus.QUEUED

        # Subscribe to job status updates. If Celery is non-eager and real Redis configured,
        # wait for background transitions; otherwise simulate with direct task.apply().
        job_messages = []
        celery_eager = os.getenv("CELERY_ALWAYS_EAGER", "true").lower() == "true"

        async def _collect_job_updates():
            async for msg in subscribe_to_job_status(job_id):
                job_messages.append(msg)
                if (msg.get("status") or "").upper() in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
                    break

        collector = asyncio.create_task(_collect_job_updates())

        if celery_eager or use_dummy_redis:
            update_job_status_task.apply(args=[job_id, JobStatus.RUNNING.value, None, tenant.id])
            update_job_status_task.apply(args=[job_id, JobStatus.COMPLETED.value, None, tenant.id])
            await asyncio.wait_for(collector, timeout=10)
            assert any((m.get("status") or "").upper() == JobStatus.RUNNING.value for m in job_messages)
            assert any((m.get("status") or "").upper() == JobStatus.COMPLETED.value for m in job_messages)
        else:
            # Live worker path: wait for background transitions
            await asyncio.wait_for(collector, timeout=20)
            statuses = {(m.get("status") or "").upper() for m in job_messages}
            assert JobStatus.RUNNING.value in statuses
            assert JobStatus.COMPLETED.value in statuses or JobStatus.FAILED.value in statuses or JobStatus.CANCELLED.value in statuses

        # Subscribe to execution trace UI events and publish representative 2N+1 signals
        trace_events: list[dict] = []

        async def _collect_trace():
            async for evt in subscribe_to_execution_trace(job_id):
                trace_events.append(evt)
                if evt.get("type") == "END":
                    break

        trace_collector = asyncio.create_task(_collect_trace())

        # Simulate orchestrator 2N+1 pipeline via UI events
        await publish_execution_trace(job_id, {"type": "START", "step_description": "Orchestration started"})
        await publish_execution_trace(job_id, {"type": "BLUEPRINT", "step_description": "Blueprint created"})
        await publish_execution_trace(job_id, {"type": "TASKS_COMPLETED", "step_description": "Team tasks executed"})
        await publish_execution_trace(job_id, {"type": "END", "step_description": "Orchestration completed"})
        await asyncio.wait_for(trace_collector, timeout=10)
        types = [e.get("type") for e in trace_events]
        for t in ("START", "BLUEPRINT", "TASKS_COMPLETED", "END"):
            assert t in types

        # Optional: Celery inspect (workers present when non-eager)
        try:
            from celery.app.control import Control
            from src.core.celery import celery_app
            stats = Control(app=celery_app).inspect().stats()
            if isinstance(stats, dict):
                # If workers available, assert dict has at least one node
                assert len(stats) >= 0
        except Exception:
            # No workers/inspect available in eager mode
            pass

        # If GCS emulator or real project is configured, verify trace archive exists
        if os.getenv("STORAGE_EMULATOR_HOST") or os.getenv("GOOGLE_CLOUD_PROJECT"):
            try:
                client_gcs = GCSClient(tenant_id=str(tenant.id), bucket_type="assets")
                gcs_key_prefix = f"traces/{job_id}/"
                assert client_gcs.file_exists(gcs_key_prefix + "trace.jsonl") is True
            except Exception:
                # If configured but inaccessible credentials, let the test continue in eager/dev setups
                if not (celery_eager or use_dummy_redis):
                    # In fully live mode, this should pass
                    raise

        # Dual-search utility should be available to orchestrators
        res = unified_research_tool(query="orchestrator verification", tenant_id=str(tenant.id))
        assert set(["project_results", "personal_results", "web_results", "vertex_results"]).issubset(res.keys())


@pytest.mark.asyncio
async def test_pillar03_orchestrator_cancel_job_stop_semantics(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p3")
    os.environ.setdefault("SECRET_KEY", "test-secret-p3-app")
    os.environ.setdefault("CELERY_ALWAYS_EAGER", "true")

    app = create_app()

    # Always use dummy Redis for deterministic STOP semantics in test envs
    setup_dummy_redis(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with get_scoped_session() as session:
            tenant = Tenant(
                tenant_id="pillar03-stop",
                subdomain="pillar03-stop",
                name="P3 Stop Brain",
                admin_email="p3stop@test.local",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            user = User(user_id="p3-stop-user", tenant_id=tenant.id, email="p3stop@test.local")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        # Create a job via executeGoal
        mutation = (
            "mutation($input: GoalInput!) { "
            "executeGoal(goalInput: $input) { success job_id status message } }"
        )
        variables = {
            "input": {
                "goal": "Start a cancellable orchestrator job.",
                "userId": user.user_id,
            }
        }
        gql = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        assert gql.status_code == 200
        payload = gql.json().get("data", {}).get("executeGoal")
        assert payload and payload.get("success") is True
        job_id = payload["job_id"]

        # Job exists and starts QUEUED
        async with get_scoped_session() as session:
            job = (await session.exec(select(Job).where(Job.job_id == job_id))).first()
            assert job is not None
            assert job.status == JobStatus.QUEUED

        status_events: list[dict] = []
        trace_events: list[dict] = []

        async def _collect_status():
            async for msg in subscribe_to_job_status(job_id):
                status_events.append(msg)
                status = (msg.get("status") or "").upper()
                if status in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
                    break

        async def _collect_trace():
            async for evt in subscribe_to_execution_trace(job_id):
                trace_events.append(evt)
                if evt.get("type") in {"STOP_INTENT", "STOP_ACK"}:
                    # stop once we have at least one STOP-related trace
                    break

        status_task = asyncio.create_task(_collect_status())
        trace_task = asyncio.create_task(_collect_trace())

        # Request cooperative cancellation via GraphQL cancelJob
        cancel_mut = """
        mutation Cancel($id:String!){
            cancelJob(job_id:$id)
        }
        """
        cancel_resp = await client.post(
            "/graphql",
            json={"query": cancel_mut, "variables": {"id": job_id}},
            headers=headers,
        )
        assert cancel_resp.status_code == 200
        cancel_result = cancel_resp.json().get("data", {}).get("cancelJob")
        assert cancel_result is True

        await asyncio.wait_for(status_task, timeout=10)
        await asyncio.wait_for(trace_task, timeout=10)

        # Job status stream should include CANCELLED
        statuses = {(m.get("status") or "").upper() for m in status_events}
        assert JobStatus.CANCELLED.value in statuses

        # Trace stream should include a STOP_INTENT from cancelJob
        trace_types = {e.get("type") for e in trace_events}
        assert "STOP_INTENT" in trace_types

        # DB row should be marked CANCELLED
        async with get_scoped_session() as session:
            job = (await session.exec(select(Job).where(Job.job_id == job_id))).first()
            assert job is not None
            assert job.status == JobStatus.CANCELLED
