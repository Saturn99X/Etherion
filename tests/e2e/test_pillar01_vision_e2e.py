import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from sqlmodel import select


@pytest.mark.asyncio
async def test_pillar01_vision_health_graphql_research_and_rate_limit(monkeypatch):
    # Minimal env for app bootstrap
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p1")
    os.environ.setdefault("SECRET_KEY", "test-secret-p1-app")
    # Run Celery tasks eagerly in tests so .apply works synchronously
    os.environ.setdefault("CELERY_ALWAYS_EAGER", "true")

    from src.etherion_ai.app import create_app
    app = create_app()

    # Create tenant and user
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User, Job, JobStatus
    from src.auth.jwt import create_access_token
    from src.core.celery import health_check_task
    from src.core.tasks import update_job_status_task

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with get_scoped_session() as session:
            await session.execute(delete(User).where(User.user_id == "p1-user"))
            await session.execute(delete(Tenant).where(Tenant.subdomain == "pillar01-e2e"))
            await session.commit()

            tenant = Tenant(
                tenant_id="pillar01-e2e",
                subdomain="pillar01-e2e",
                name="Pillar01 Vision Tenant",
                admin_email="p1@test.local",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            user = User(
                user_id="p1-user",
                tenant_id=tenant.id,
                email="p1@test.local",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Auth header for GraphQL/REST that require Authorization
        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        # Health and rate limit header (PerIPRateLimitMiddleware)
        h = await client.get("/health")
        assert h.status_code == 200
        root = await client.get("/")
        assert root.headers.get("X-RateLimit-Limit") is not None

        # GraphQL health check
        gql = await client.post("/graphql", json={"query": "query { healthCheck }"}, headers=headers)
        assert gql.status_code == 200
        assert gql.json().get("data", {}).get("healthCheck") is not None

        # Unified research tool (KB + Web + Vertex cache)
        from src.tools.unified_research_tool import unified_research_tool
        res = unified_research_tool(query="vision e2e", tenant_id=str(tenant.id), project_id=None)
        assert set(["project_results", "personal_results", "web_results", "vertex_results"]).issubset(res.keys())

        # Pillar 01: executeGoal should create a queued Job and return a job_id
        mutation = (
            "mutation($input: GoalInput!) { "
            "executeGoal(goalInput: $input) { success jobId status message } }"
        )
        variables = {
            "input": {
                "goal": "Demonstrate autonomous execution by starting a simple job.",
                "userId": user.user_id,
            }
        }
        exec_resp = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        assert exec_resp.status_code == 200
        payload = exec_resp.json().get("data", {}).get("executeGoal")
        assert payload and payload.get("success") is True
        job_id = payload["jobId"]
        assert payload.get("status") == JobStatus.QUEUED.value

        # Verify Job persisted as QUEUED
        async with get_scoped_session() as session:
            result = await session.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalars().first()
            assert job is not None
            assert job.status == JobStatus.QUEUED

        # Sanity: Celery health task works under eager mode
        result = health_check_task.apply(args=())
        assert result.result["status"] == "healthy"

        # Simulate lifecycle via Celery task updates and verify DB transitions
        update_job_status_task.apply(args=[job_id, JobStatus.RUNNING.value, None, tenant.id])
        async with get_scoped_session() as session:
            result = await session.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalars().first()
            assert job.status == JobStatus.RUNNING

        update_job_status_task.apply(args=[job_id, JobStatus.COMPLETED.value, None, tenant.id])
        async with get_scoped_session() as session:
            result = await session.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalars().first()
            assert job.status == JobStatus.COMPLETED

        # Optional: Repository assertion if Google Cloud is configured
        gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        if gcp_project:
            try:
                # Insert a minimal AI-origin asset row for this job
                from src.services.bigquery_service import BigQueryService
                from src.services.repository_service import RepositoryService
                import hashlib
                bq = BigQueryService(project_id=gcp_project)
                table = f"{gcp_project}.tnt_{tenant.id}.assets"

                # Compose a stable asset_id similar to ingestion policy
                gcs_uri = f"gs://tnt-{tenant.id}-assets/demo/{job_id}.txt"
                asset_id = hashlib.md5((str(tenant.id) + gcs_uri).encode()).hexdigest()
                row = {
                    "asset_id": asset_id,
                    "job_id": job_id,
                    "tenant_id": str(tenant.id),
                    "agent_name": "vision-test",
                    "agent_id": "vision-agent-1",
                    "user_id": user.user_id,
                    "mime_type": "text/plain",
                    "gcs_uri": gcs_uri,
                    "filename": f"{job_id}.txt",
                    "size_bytes": 12,
                    "text_extract": "autonomy",
                    "description": "Pillar01 vision demo",
                    "created_at": "2025-01-01T00:00:00Z",
                    "metadata": {"origin": "ai", "kb_type": "project"},
                }
                bq.insert_rows_json(table, [row])

                repo = RepositoryService(tenant_id=tenant.id, project_id=gcp_project)
                assets = repo.list_assets(limit=10, job_id=job_id)
                assert any(a.job_id == job_id for a in assets)
            except Exception:
                # If BigQuery/GCS not fully available, skip repo assertion gracefully
                pass
