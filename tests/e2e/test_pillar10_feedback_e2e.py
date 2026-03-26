import os
import asyncio
from datetime import datetime
import pytest
from sqlmodel import select
from httpx import AsyncClient, ASGITransport
from google.cloud import bigquery, storage
from tests.e2e._dummy_redis import setup_dummy_redis

from src.core.redis import get_redis_client

pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="Requires GOOGLE_CLOUD_PROJECT for BigQuery integration",
)


@pytest.mark.asyncio
async def test_pillar10_feedback_submission_rate_limit_and_sanitization(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p10")
    os.environ.setdefault("SECRET_KEY", "test-secret-p10-app")

    from src.etherion_ai.app import create_app
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User, Job, JobStatus
    from src.auth.jwt import create_access_token

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Use in-memory Redis for deterministic rate limiting
        setup_dummy_redis(monkeypatch)
        async with get_scoped_session() as session:
            tenant = Tenant(
                tenant_id="pillar10-feedback",
                subdomain="pillar10-feedback",
                name="Pillar10 Feedback Tenant",
                admin_email="p10@test.local",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            user = User(user_id="p10-user", tenant_id=tenant.id, email="p10@test.local")
            session.add(user)
            await session.commit()
            await session.refresh(user)

            job = Job(
                job_id=Job.generate_job_id(),
                tenant_id=tenant.id,
                user_id=user.id,
                status=JobStatus.COMPLETED,
                job_type="execute_goal",
            )
            job.set_output_data({"output": "Sample job output"})
            session.add(job)
            await session.commit()
            await session.refresh(job)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        mutation = (
            "mutation($input: FeedbackInput!){ submitFeedback(feedback_input:$input) }"
        )
        variables = {
            "input": {
                "jobId": job.job_id,
                "userId": user.user_id,
                "goal": "Redesign homepage for https://example.com",
                "finalOutput": "User email is user@example.com",
                "feedbackScore": 5,
                "feedbackComment": "Great job handling PII!",
            }
        }
        resp = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        assert resp.status_code == 200
        assert resp.json().get("data", {}).get("submitFeedback") is True

        redis_client = get_redis_client()
        redis_cli = await redis_client.get_client()
        keys = [key async for key in _iter_keys(redis_cli, "feedback:")]
        assert keys, "Expected feedback rate limit key in Redis"
        rate_key = keys[0]
        assert int(await redis_cli.get(rate_key) or 0) == 2

        async with get_scoped_session() as session:
            from src.database.models import Feedback
            fb = session.exec(select(Feedback).where(Feedback.job_id == job.job_id)).first()
            assert fb is not None
            assert "[redacted_url]" in fb.goal_text
            assert "[redacted_email]" in fb.final_output_text

        # Verify BigQuery feedback row exists
        gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        assert gcp_project, "GOOGLE_CLOUD_PROJECT required"
        bq = bigquery.Client(project=gcp_project)
        table = f"{gcp_project}.tnt_{tenant.id}.feedback"
        q = (
            "SELECT job_id, score, goal_text, final_output_text, comment_text "
            "FROM `{table}` WHERE job_id = @job_id"
        ).format(table=table)
        job_cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("job_id", "STRING", job.job_id)])
        rows = list(bq.query(q, job_config=job_cfg).result())
        assert rows, "Expected feedback row in BigQuery"
        # Ensure sanitized strings made it to analytics
        assert "example.com" not in rows[0].final_output_text
        assert "@" not in rows[0].final_output_text or "[redacted_email]" in rows[0].final_output_text

        # Verify anonymized GCS copy exists for SFT
        storage_client = storage.Client(project=gcp_project)
        bucket_name = f"tnt-{tenant.id}-feedback"
        bucket = storage_client.bucket(bucket_name)
        # Allow for eventual consistency
        date_prefix = datetime.utcnow().strftime("%Y/%m/%d")
        found_blob = None
        for _ in range(30):
            blobs = list(storage_client.list_blobs(bucket, prefix=f"{date_prefix}/{job.job_id}_"))
            if blobs:
                found_blob = blobs[0]
                break;
            await asyncio.sleep(1)
        assert found_blob is not None, "Expected anonymized GCS copy for feedback"
        payload = found_blob.download_as_text()
        assert "example.com" not in payload
        assert "@" not in payload

        resp2 = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert "errors" in body2
        assert any("RATE_LIMIT_EXCEEDED" in err.get("message", "") for err in body2["errors"])


async def _iter_keys(client, prefix: str):
    cursor = "0"
    while True:
        cursor, keys = await client.scan(cursor=cursor, match=f"{prefix}*")
        for key in keys:
            yield key
        if cursor == "0":
            break
