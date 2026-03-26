import asyncio
import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlmodel import select

from celery.contrib.testing.worker import start_worker
from src.core.redis import subscribe_to_job_status


@pytest.mark.asyncio
async def test_pillar07_async_engine_job_status_and_celery(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p7")
    os.environ.setdefault("SECRET_KEY", "test-secret-p7-app")
    # Ensure sync and async DB use a shared file across app and Celery worker
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_e2e_shared.db")
    # Ensure non-eager execution with hermetic in-memory broker/backends
    os.environ["CELERY_ALWAYS_EAGER"] = "false"
    os.environ["CELERY_BROKER_URL"] = "memory://"
    os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"

    from src.etherion_ai.app import create_app
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User, Job, JobStatus
    from src.auth.jwt import create_access_token
    from src.core.tasks import update_job_status_task
    from src.core.celery import health_check_task
    # Import celery_app AFTER configuring env so broker/backends are memory://
    from src.core.celery import celery_app
    from tests.e2e._dummy_redis import setup_dummy_redis

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Use in-memory Redis stub so pub/sub assertions are deterministic
        setup_dummy_redis(monkeypatch)

        # Define a retrying Celery task to exercise broker/worker flow
        @celery_app.task(bind=True, name="e2e.fail_once_then_succeed", autoretry_for=(RuntimeError,), retry_kwargs={"max_retries": 1, "countdown": 0})
        def fail_once_then_succeed(self):
            # First run raises → autoretry, second returns ok
            if getattr(self.request, "retries", 0) == 0:
                raise RuntimeError("transient")
            return {"ok": True}

        # Start a real worker bound to the in-memory broker
        with start_worker(celery_app, perform_ping_check=False, pool="solo"):
            # Create tenant and user for this test run
            async with get_scoped_session() as session:
                tenant = Tenant(
                    tenant_id="pillar07-async",
                    subdomain="pillar07-async",
                    name="Pillar07 Async Tenant",
                    admin_email="p7@test.local",
                )
                session.add(tenant)
                await session.commit()
                await session.refresh(tenant)

                user = User(user_id="p7-user", tenant_id=tenant.id, email="p7@test.local")
                session.add(user)
                await session.commit()
                await session.refresh(user)

            token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
            headers = {"Authorization": f"Bearer {token}"}

            mutation = (
                "mutation($input: GoalInput!) { "
                "executeGoal(goalInput: $input) { success job_id status message } }"
            )
            variables = {
                "input": {
                    "goal": "Produce a quick async readiness summary.",
                    "userId": user.user_id,
                }
            }
            response = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
            assert response.status_code == 200
            payload = response.json().get("data", {}).get("executeGoal")
            assert payload and payload.get("success") is True
            job_id = payload["job_id"]

            async with get_scoped_session() as session:
                job = (await session.exec(select(Job).where(Job.job_id == job_id))).first()
                assert job is not None
                assert job.status == JobStatus.QUEUED

            job_messages = []

            async def _collect_status_updates():
                async for message in subscribe_to_job_status(job_id):
                    job_messages.append(message)
                    if message.get("status") in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
                        break

            collector = asyncio.create_task(_collect_status_updates())

            # Health task should execute on worker (non-eager)
            result = health_check_task.delay()
            assert result.get(timeout=10)["status"] == "healthy"

            # Drive RUNNING then FAILED via Celery (queue handling path)
            res_run = update_job_status_task.apply_async(args=[job_id, JobStatus.RUNNING.value, None, tenant.id])
            # Wait for the task to be processed by the worker
            res_run.get(timeout=10)
            async with get_scoped_session() as session:
                job = (await session.exec(select(Job).where(Job.job_id == job_id))).first()
                assert job.status == JobStatus.RUNNING

            res_fail = update_job_status_task.apply_async(args=[job_id, JobStatus.FAILED.value, "simulated error", tenant.id])
            res_fail.get(timeout=10)
            async with get_scoped_session() as session:
                job = (await session.exec(select(Job).where(Job.job_id == job_id))).first()
                assert job.status == JobStatus.FAILED

            # Subscription stream should terminate on FAILED and collector finish
            await asyncio.wait_for(collector, timeout=10)
            assert any(msg.get("status") == JobStatus.RUNNING.value for msg in job_messages)
            assert any(msg.get("status") == JobStatus.FAILED.value for msg in job_messages)

            # Verify retrying task behavior (fail once → succeed)
            retry_res = celery_app.send_task("e2e.fail_once_then_succeed")
            assert retry_res.get(timeout=10).get("ok") is True
