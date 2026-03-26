import os
import pytest
import asyncio
from httpx import AsyncClient

from src.auth.jwt import create_access_token
from src.database.db import get_session
from src.database.models import Tenant, User, Job, JobStatus


@pytest.mark.asyncio
async def test_cancel_job_marks_cancelled(monkeypatch):
    # Ensure required secrets
    os.environ.setdefault("JWT_SECRET_KEY", "jwt-test-secret")
    os.environ.setdefault("SECRET_KEY", "server-secret")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "dev-proj")

    # Import app lazily after env is set
    from src.etherion_ai.app import create_app

    # Seed tenant, user, job
    sess = get_session()
    try:
        tenant = Tenant(name="T", subdomain="t", admin_email="t@example.com")
        sess.add(tenant)
        sess.commit()
        sess.refresh(tenant)

        user = User(user_id="u-1", tenant_id=tenant.id, email="u@example.com")
        sess.add(user)
        sess.commit()
        sess.refresh(user)

        job = Job(job_id="job_test_cancel", tenant_id=tenant.id, user_id=user.id, status=JobStatus.RUNNING, job_type="execute_goal")
        sess.add(job)
        sess.commit()
    finally:
        sess.close()

    token = create_access_token({"sub": "u-1", "email": "u@example.com", "tenant_id": tenant.id})

    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": "mutation($id: String!){ cancelJob(job_id: $id) }",
                "variables": {"id": "job_test_cancel"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["cancelJob"] is True

    # Verify DB status
    sess = get_session()
    try:
        row = sess.exec(Job.select().where(Job.job_id == "job_test_cancel")).first() if hasattr(Job, "select") else sess.query(Job).filter(Job.job_id == "job_test_cancel").first()
        assert row is not None
        assert str(row.status).upper().endswith("CANCELLED") or getattr(row.status, "value", str(row.status)).upper() == "CANCELLED"
    finally:
        sess.close()
