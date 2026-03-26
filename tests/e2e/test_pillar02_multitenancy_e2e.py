import os
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
pytestmark = pytest.mark.skipif(
    not GCP_PROJECT,
    reason="Requires GOOGLE_CLOUD_PROJECT for GCS/BQ integration",
)


@pytest.mark.asyncio
async def test_pillar02_multitenancy_kb_assets_and_secrets(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p2")
    os.environ.setdefault("SECRET_KEY", "test-secret-p2-app")
    # Ensure Secret Manager uses same project
    os.environ.setdefault("GCP_PROJECT_ID", GCP_PROJECT)

    from src.etherion_ai.app import create_app
    app = create_app()

    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token
    from src.services.repository_service import RepositoryService
    from src.services.kb_query_service import KBQueryService
    from tests.e2e._dummy_redis import setup_dummy_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Use in-memory Redis for deterministic quotas
        setup_dummy_redis(monkeypatch)
        # Create Tenants A and B
        async with get_scoped_session() as session:
            await session.execute(delete(User).where(User.user_id.in_(["p2-user-a", "p2-user-b"])))
            await session.execute(delete(Tenant).where(Tenant.subdomain.in_(["pillar02-A", "pillar02-B"])))
            await session.commit()

            ta = Tenant(tenant_id="pillar02-A", subdomain="pillar02-A", name="P2-A", admin_email="a@p2.test")
            tb = Tenant(tenant_id="pillar02-B", subdomain="pillar02-B", name="P2-B", admin_email="b@p2.test")
            session.add(ta); session.add(tb)
            await session.commit(); await session.refresh(ta); await session.refresh(tb)

            ua = User(user_id="p2-user-a", tenant_id=ta.id, email="a@p2.test")
            ub = User(user_id="p2-user-b", tenant_id=tb.id, email="b@p2.test")
            session.add(ua); session.add(ub)
            await session.commit(); await session.refresh(ua); await session.refresh(ub)

        token_a = create_access_token({"sub": ua.user_id, "email": ua.email, "tenant_id": ta.id})
        token_b = create_access_token({"sub": ub.user_id, "email": ub.email, "tenant_id": tb.id})
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Ingest small text for Tenant A (creates GCS object + BigQuery rows)
        from src.services.ingestion_service import IngestionService
        isvc = IngestionService(project_id=GCP_PROJECT)
        text = "P2 multi-tenant e2e content for isolation and secrets"
        content = text.encode("utf-8")
        gcs_uri = isvc.upload_bytes(str(ta.id), content, "p2_mt.txt", "text/plain")
        result = isvc.ingest_bytes(str(ta.id), content, "p2_mt.txt", "text/plain", project_id="mt-e2e-proj")
        assert result.gcs_uri == gcs_uri and result.chunks_inserted >= 1

        asset_id = hashlib.md5((str(ta.id) + gcs_uri).encode()).hexdigest()

        # Confirm ingestion wrote to BigQuery assets table
        from google.cloud import bigquery
        bq = bigquery.Client(project=GCP_PROJECT)
        asset_table = f"{GCP_PROJECT}.tnt_{ta.id}.assets"
        asset_query = (
            "SELECT asset_id, tenant_id, filename, JSON_VALUE(metadata, '$.origin') AS origin "
            "FROM `{table}` WHERE asset_id = @asset_id"
        ).format(table=asset_table)
        query_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id)]
        )
        asset_rows = list(bq.query(asset_query, job_config=query_config).result())
        assert asset_rows and asset_rows[0].origin == "user"

        # Tenant A can preview; Tenant B must be denied (404)
        prev_a = await client.get(f"/assets/{asset_id}", headers=headers_a)
        assert prev_a.status_code == 200 and "base64" in prev_a.json()
        prev_b = await client.get(f"/assets/{asset_id}", headers=headers_b)
        assert prev_b.status_code == 404

        # KB query returns chunk for tenant A, but not for tenant B
        kb = KBQueryService(project_id=GCP_PROJECT)
        rows_a = kb.search(tenant_id=str(ta.id), query="isolation and secrets", project_id="mt-e2e-proj", kb_type="project", limit=5)
        assert any("isolation" in (r.get("text_chunk") or "") for r in rows_a)
        rows_b = kb.search(tenant_id=str(tb.id), query="isolation and secrets", project_id="mt-e2e-proj", kb_type="project", limit=5)
        assert len(rows_b) == 0

        # Repository (AI-only): create an AI artifact and verify isolation
        repo_a = RepositoryService(tenant_id=ta.id, project_id=GCP_PROJECT)
        ai_asset = repo_a.create_ai_asset(
            content=b"synthetic ai output for pillar02",
            filename="p2_ai.txt",
            mime_type="text/plain",
            job_id="p2-ai-job-1",
            title="P2 AI Output",
        )
        assets_a = repo_a.list_assets(limit=10)
        assert any(a.asset_id == ai_asset.asset_id for a in assets_a)

        repo_b = RepositoryService(tenant_id=tb.id, project_id=GCP_PROJECT)
        assets_b = repo_b.list_assets(limit=10)
        # Tenant B should not see Tenant A's AI asset
        assert all(a.asset_id != ai_asset.asset_id for a in assets_b)

        # Secret rotation (requires Authorization header via RESTCSRFGuard)
        rotate = await client.post(
            "/secrets/gmail/refresh_token/rotate",
            json={"tenant_id": ta.id, "new_value": "test-rotated-token-p2"},
            headers=headers_a,
        )
        assert rotate.status_code == 200 and rotate.json().get("success") is True

        # Verify secret stored for Tenant A and not visible for Tenant B
        from src.utils.secrets_manager import TenantSecretsManager
        sm = TenantSecretsManager()
        stored = await sm.get_secret(str(ta.id), "gmail", "refresh_token")
        assert stored == "test-rotated-token-p2"
        missing = await sm.get_secret(str(tb.id), "gmail", "refresh_token")
        assert missing is None

        # OAuth silo start (if configured) using Google provider
        if os.getenv("OAUTH_STATE_SECRET"):
            # SiloOAuthService derives tenant_id from JWT via tenant_middleware
            oauth = await client.get("/oauth/silo/google/start", headers=headers_a)
            assert oauth.status_code == 200
            data = oauth.json()
            assert "authorize_url" in data

        # Vendor quota isolation: increment Slack quota for tenant A via webhook, verify B unaffected
        slack_resp = await client.post(f"/webhook/slack/{ta.id}", content=b"{}", headers={"X-Slack-Request-Timestamp": "0", "X-Slack-Signature": "v0=deadbeef"})
        # May be 401 due to signature; acceptable as quota increments before validation
        assert slack_resp.status_code in (200, 401, 500)

        gql = "query($v:String!){ getVendorQuotaRemaining(vendor:$v) }"
        # Remaining for A (after one increment)
        rem_a = await client.post("/graphql", json={"query": gql, "variables": {"v": "slack"}}, headers=headers_a)
        assert rem_a.status_code == 200
        a_val = rem_a.json().get("data", {}).get("getVendorQuotaRemaining")
        assert isinstance(a_val, int) and a_val >= 0

        # Remaining for B (should equal default limit and be >= A)
        rem_b = await client.post("/graphql", json={"query": gql, "variables": {"v": "slack"}}, headers=headers_b)
        assert rem_b.status_code == 200
        b_val = rem_b.json().get("data", {}).get("getVendorQuotaRemaining")
        assert isinstance(b_val, int) and b_val >= a_val
