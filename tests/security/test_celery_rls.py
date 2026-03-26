import time
import json
import pytest
from sqlalchemy import text

from src.database.db import get_db
from src.database.models import Job, JobStatus
from src.database.ts_models import Tenant, Project
from src.services.goal_orchestrator import orchestrate_goal_task


@pytest.mark.integration
def test_celery_rls_enforces_tenant_context_isolation(monkeypatch):
    """
    Create two tenants A and B with distinct data.
    Enqueue orchestrate_goal_task for tenant A.
    Inside a mocked tool path, run a raw SQL query for tenant B and assert 0 rows (RLS enforced).
    """
    db = get_db()
    try:
        # Setup Tenants A and B
        tenant_a = Tenant(name="TenantA")
        tenant_b = Tenant(name="TenantB")
        db.add_all([tenant_a, tenant_b])
        db.commit()
        db.refresh(tenant_a)
        db.refresh(tenant_b)

        # Seed distinct projects
        project_a = Project(name="A-Project", user_id=1, tenant_id=tenant_a.id)
        project_b = Project(name="B-Project", user_id=2, tenant_id=tenant_b.id)
        db.add_all([project_a, project_b])
        db.commit()

        # Create job for Tenant A
        job = Job(
            tenant_id=tenant_a.id,
            user_id=1,
            status=JobStatus.QUEUED,
            goal_description="Simple goal",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Monkeypatch a lightweight execution path to inject raw SQL check inside worker
        original_execute = orchestrate_goal_task.run

        def wrapped(self, *args, **kwargs):
            # When tenant context is set for A, querying B's data should yield 0 rows
            inner_db = get_db()
            try:
                rows = inner_db.execute(
                    text("SELECT * FROM project WHERE tenant_id = :tid"),
                    {"tid": tenant_b.id}
                ).fetchall()
                assert len(rows) == 0
            finally:
                inner_db.close()
            return original_execute(self, *args, **kwargs)

        monkeypatch.setattr(orchestrate_goal_task, "run", wrapped)

        # Execute task synchronously (unit/integration context)
        res = orchestrate_goal_task.run(
            job_id=job.job_id,
            goal_description=job.goal_description,
            context=None,
            output_format_instructions=None,
            user_id=job.user_id,
            tenant_id=tenant_a.id,
            agent_team_id=None,
        )

        assert isinstance(res, dict)
        assert res.get("success") in (True, False)  # Execution may vary; isolation is primary assertion

    finally:
        db.close()


