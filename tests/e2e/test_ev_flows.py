import os
import hashlib
import asyncio
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

# Ensure required envs for GCP-backed flows
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

pytestmark = pytest.mark.skipif(
    not GCP_PROJECT,
    reason="Requires GOOGLE_CLOUD_PROJECT for GCS/BQ integration",
)


@pytest.mark.asyncio
async def test_drive_cf_bq_vertex_preview_download_and_rate_limit(monkeypatch):
    """Validate the critical ingest → preview/download → query → research flow.

    Caveats for this scenario:
    - Uses `IngestionService.upload_bytes()` directly instead of a Google Drive connector.
    - Processes a small text file so non-text ingestion behavior is not exercised.
    - Vertex AI Search responses depend on existing data; the assertion only checks
      that the unified research tool returns the expected keys.
    """
    # Create app client
    # Ensure JWT secret before importing app (jwt loads at import time)
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-ev")
    os.environ.setdefault("SECRET_KEY", "test-secret-ev-app")
    from src.etherion_ai.app import create_app
    app = create_app()

    # Create tenant and user in DB
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        suffix = uuid.uuid4().hex[:8]
        tenant_slug = f"tenant-ev-{suffix}"
        user_slug = f"user-ev-{suffix}"

        async with get_scoped_session() as session:
            tenant = Tenant(
                tenant_id=tenant_slug,
                subdomain=tenant_slug,
                name="EV Flow Tenant",
                admin_email="admin@ev.test",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            user = User(
                user_id=user_slug,
                tenant_id=tenant.id,
                email="user@ev.test",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Build auth token
        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        # Ingest small text file via service (text-only) and ensure base64 preview path
        # (Drive connectors are covered elsewhere; this test targets the ingest pipeline)
        from src.services.ingestion_service import IngestionService
        isvc = IngestionService(project_id=GCP_PROJECT)
        content_text = "EV-flow e2e sample text about preview and download"
        content_bytes = content_text.encode("utf-8")
        gcs_uri = isvc.upload_bytes(str(tenant.id), content_bytes, "ev_e2e.txt", "text/plain")
        # Run full ingest to create BigQuery docs and assets rows (Vertex CDC best-effort)
        result = isvc.ingest_bytes(str(tenant.id), content_bytes, "ev_e2e.txt", "text/plain", project_id="ev-e2e-proj")
        assert result.gcs_uri == gcs_uri
        assert result.chunks_inserted >= 1

        # Compute asset_id as used by IngestionService
        asset_id = hashlib.md5((str(tenant.id) + gcs_uri).encode()).hexdigest()

        # Ensure an AI-origin asset row exists for preview/download APIs
        from google.cloud import bigquery
        bq = bigquery.Client(project=GCP_PROJECT)
        table_ref = f"{GCP_PROJECT}.tnt_{tenant.id}.assets"
        ai_row = {
            "asset_id": asset_id,
            "job_id": None,
            "tenant_id": str(tenant.id),
            "agent_name": "ev-agent",
            "agent_id": "ev-agent-1",
            "user_id": user.user_id,
            "mime_type": "text/plain",
            "gcs_uri": gcs_uri,
            "filename": "ev_e2e.txt",
            "size_bytes": len(content_bytes),
            "text_extract": content_text,
            "description": "ev flow test",
            "created_at": "2025-01-01T00:00:00Z",
            "metadata": {"origin": "ai", "kb_type": "project"},
        }
        bq.insert_rows_json(table_ref, [ai_row])

        docs_ref = f"{GCP_PROJECT}.tnt_{tenant.id}.docs"
        docs_query = (
            "SELECT text_chunk, vector_embedding "
            "FROM `{docs}` WHERE project_id = @project_id"
        ).format(docs=docs_ref)
        docs_job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("project_id", "STRING", "ev-e2e-proj")]
        )
        docs_rows = list(bq.query(docs_query, job_config=docs_job_config).result())
        assert docs_rows and any("preview and download" in (row.text_chunk or "") for row in docs_rows)
        assert all(getattr(row, "vector_embedding", None) and len(row.vector_embedding) > 0 for row in docs_rows)

        # Preview endpoint should return base64 for small files
        prev_resp = await client.get(f"/assets/{asset_id}", headers=headers)
        assert prev_resp.status_code == 200
        prev_json = prev_resp.json()
        assert prev_json.get("asset_id") == asset_id
        assert "base64" in prev_json  # small file → inline base64

        # Download endpoint should always return a signed URL
        dl_resp = await client.get(f"/assets/{asset_id}/download", headers=headers)
        assert dl_resp.status_code == 200
        dl_json = dl_resp.json()
        assert dl_json.get("asset_id") == asset_id
        assert "url" in dl_json and isinstance(dl_json["url"], str)

        # KB search should return our ingested text chunk from BigQuery
        # (Verifies project KB path; personal KB is minimally exercised below)
        from src.services.kb_query_service import KBQueryService
        kb = KBQueryService(project_id=GCP_PROJECT)
        results = kb.search(tenant_id=str(tenant.id), query="preview and download", project_id="ev-e2e-proj", kb_type="project", limit=5)
        assert isinstance(results, list)
        assert any("preview and download" in (r.get("text_chunk") or "") for r in results)

        # Rate limit headers should be present on responses
        root_resp = await client.get("/")
        assert root_resp.headers.get("X-RateLimit-Limit") is not None

        # Unified research tool should return required keys (may be empty depending on env)
        # Vertex AI / web search integration is environment-sensitive, so we only
        # confirm the response structure rather than specific content.
        from src.tools.unified_research_tool import unified_research_tool
        res = unified_research_tool(query="preview and download", tenant_id=str(tenant.id), project_id="ev-e2e-proj")
        assert set(["project_results", "personal_results", "web_results", "vertex_results"]).issubset(res.keys())
