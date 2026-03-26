import os
import asyncio
import pytest
from httpx import AsyncClient
from httpx import ASGITransport

from sqlmodel import select

from src.etherion_ai.app import create_app
from src.database.db import get_scoped_session
from src.database.models import Tenant, User, Job, JobStatus
from src.auth.jwt import create_access_token
from src.core.redis import (
    publish_job_status,
    subscribe_to_job_status,
    publish_execution_trace,
    subscribe_to_execution_trace,
)
from src.core.gcs_client import GCSClient


pytestmark = pytest.mark.asyncio


def _skip_unless_env(var_names):
    missing = [v for v in var_names if not os.getenv(v)]
    if missing:
        pytest.skip(f"Missing required env: {', '.join(missing)}")


@pytest.mark.timeout(20)
async def test_live_redis_pubsub_end_to_end():
    """
    Validates real Redis pub/sub using job_status and job_trace channels.
    Requires REDIS_URL to be set and reachable.
    """
    _skip_unless_env(["REDIS_URL"])  # ensure not using dummy

    app = create_app()

    # Create tenant and user
    async with get_scoped_session() as s:
        t = Tenant(tenant_id="live-redis", subdomain="live-redis", name="Live Redis", admin_email="live@redis.test")
        s.add(t); await s.commit(); await s.refresh(t)
        u = User(user_id="live-redis-user", tenant_id=t.id, email="live@redis.test")
        s.add(u); await s.commit(); await s.refresh(u)

    token = create_access_token({"sub": u.user_id, "email": u.email, "tenant_id": t.id})
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Trigger a goal to create a job
        mutation = "mutation($input: GoalInput!) { executeGoal(goalInput: $input) { success job_id status message } }"
        variables = {"input": {"goal": "Ping live Redis", "userId": u.user_id}}
        rsp = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        payload = rsp.json()["data"]["executeGoal"]
        assert payload["success"] is True
        job_id = payload["job_id"]

        # Verify job exists
        async with get_scoped_session() as s:
            job = (await s.exec(select(Job).where(Job.job_id == job_id))).first()
            assert job is not None

        # Validate pub/sub on job_status
        status_msgs = []

        async def _collect_status():
            async for m in subscribe_to_job_status(job_id):
                status_msgs.append(m)
                if (m.get("status") or "").upper() == "DONE":
                    break

        collector = asyncio.create_task(_collect_status())
        await publish_job_status(job_id, {"status": "START"})
        await publish_job_status(job_id, {"status": "DONE"})
        await asyncio.wait_for(collector, timeout=5)
        statuses = [str(m.get("status")).upper() for m in status_msgs]
        assert "START" in statuses and "DONE" in statuses

        # Validate execution trace pub/sub
        trace_msgs = []

        async def _collect_trace():
            async for e in subscribe_to_execution_trace(job_id):
                trace_msgs.append(e)
                if e.get("type") == "END":
                    break

        tcollector = asyncio.create_task(_collect_trace())
        await publish_execution_trace(job_id, {"type": "START", "step_description": "begin"})
        await publish_execution_trace(job_id, {"type": "END", "step_description": "done"})
        await asyncio.wait_for(tcollector, timeout=5)
        types = [e.get("type") for e in trace_msgs]
        assert "START" in types and "END" in types


@pytest.mark.timeout(30)
async def test_celery_background_worker_job_lifecycle():
    """
    Validates Celery background processing updates job status end-to-end.
    Requires CELERY_ALWAYS_EAGER=false and a running Celery worker.
    Also requires REDIS_URL for broker/backend.
    """
    # Ensure non-eager Celery and Redis present
    _skip_unless_env(["REDIS_URL"])
    if os.getenv("CELERY_ALWAYS_EAGER", "true").lower() == "true":
        pytest.skip("CELERY_ALWAYS_EAGER must be false with a running worker")

    app = create_app()

    # Create tenant and user
    async with get_scoped_session() as s:
        t = Tenant(tenant_id="celery-live", subdomain="celery-live", name="Celery Live", admin_email="celery@live.test")
        s.add(t); await s.commit(); await s.refresh(t)
        u = User(user_id="celery-live-user", tenant_id=t.id, email="celery@live.test")
        s.add(u); await s.commit(); await s.refresh(u)

    token = create_access_token({"sub": u.user_id, "email": u.email, "tenant_id": t.id})
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        mutation = "mutation($input: GoalInput!) { executeGoal(goalInput: $input) { success job_id status message } }"
        variables = {"input": {"goal": "Run via Celery", "userId": u.user_id}}
        rsp = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        payload = rsp.json()["data"]["executeGoal"]
        assert payload["success"] is True
        job_id = payload["job_id"]

        # Wait for background transitions
        statuses = []

        async def _collect():
            async for m in subscribe_to_job_status(job_id):
                s = (m.get("status") or "").upper()
                statuses.append(s)
                if s in {"COMPLETED", "FAILED", "CANCELLED"}:
                    break

        await asyncio.wait_for(_collect(), timeout=20)
        # We expect RUNNING then COMPLETED in the stream
        assert "RUNNING" in statuses and ("COMPLETED" in statuses or "FAILED" in statuses)

        # Verify final status in DB
        async with get_scoped_session() as s:
            job = (await s.exec(select(Job).where(Job.job_id == job_id))).first()
            assert job is not None
            assert job.status in {JobStatus.COMPLETED, JobStatus.FAILED}


@pytest.mark.timeout(40)
async def test_gcs_trace_archiving_with_emulator():
    """
    Validates execution trace archiving to GCS emulator.
    Requires STORAGE_EMULATOR_HOST and GOOGLE_CLOUD_PROJECT set, plus a running emulator.
    Also requires non-eager Celery and Redis.
    """
    _skip_unless_env(["STORAGE_EMULATOR_HOST", "GOOGLE_CLOUD_PROJECT", "REDIS_URL"])
    if os.getenv("CELERY_ALWAYS_EAGER", "true").lower() == "true":
        pytest.skip("CELERY_ALWAYS_EAGER must be false with a running worker for archiving task")

    app = create_app()

    # Create tenant and user
    async with get_scoped_session() as s:
        t = Tenant(tenant_id="gcs-emul", subdomain="gcs-emul", name="GCS Emul", admin_email="gcs@emul.test")
        s.add(t); await s.commit(); await s.refresh(t)
        u = User(user_id="gcs-emul-user", tenant_id=t.id, email="gcs@emul.test")
        s.add(u); await s.commit(); await s.refresh(u)

    token = create_access_token({"sub": u.user_id, "email": u.email, "tenant_id": t.id})
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        mutation = "mutation($input: GoalInput!) { executeGoal(goalInput: $input) { success job_id status message } }"
        variables = {"input": {"goal": "Archive trace to emulator", "userId": u.user_id}}
        rsp = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        payload = rsp.json()["data"]["executeGoal"]
        assert payload["success"] is True
        job_id = payload["job_id"]

        # Wait for COMPLETED to ensure archive task fired
        async def _await_completed():
            async for m in subscribe_to_job_status(job_id):
                if (m.get("status") or "").upper() == "COMPLETED":
                    return
        await asyncio.wait_for(_await_completed(), timeout=30)

        # Verify trace object exists in emulator
        client_gcs = GCSClient(tenant_id=str(t.id), bucket_type="assets")
        gcs_key_prefix = f"traces/{job_id}/"
        # The task writes trace.jsonl
        assert client_gcs.file_exists(gcs_key_prefix + "trace.jsonl") is True
