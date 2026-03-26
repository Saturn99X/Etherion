import os
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport

from google.cloud import bigquery

pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="Requires GOOGLE_CLOUD_PROJECT for cloud-backed integration",
)


@pytest.mark.asyncio
async def test_pillar13_architecture_ingest_kb_vertex_and_repository_endpoints(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p13")
    os.environ.setdefault("SECRET_KEY", "test-secret-p13-app")

    from src.etherion_ai.app import create_app
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create tenant + user
        async with get_scoped_session() as session:
            tenant = Tenant(
                tenant_id="pillar13-arch",
                subdomain="pillar13-arch",
                name="P13 Tenant",
                admin_email="p13@test.local",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            user = User(user_id="p13-user", tenant_id=tenant.id, email="p13@test.local")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        # Ingest sample content
        from src.services.ingestion_service import IngestionService
        from src.services.bq_schema_manager import ensure_tenant_kb
        import src.services.vertex_cache_cdc as vertex_cdc_module
        GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
        # Ensure tenant dataset/tables exist prior to ingest (schema provisioning)
        ensure_tenant_kb(bigquery.Client(project=GCP_PROJECT), str(tenant.id))
        isvc = IngestionService(project_id=GCP_PROJECT)
        # Capture CDC pushes
        captured_docs = []

        def _capture_push(self, tenant_id: str, rows):  # type: ignore[override]
            captured_docs.extend(rows)

        monkeypatch.setattr(vertex_cdc_module.VertexSearchCacheCDC, "push_rows", _capture_push, raising=False)
        content_text = "Hello architecture pillar with BigQuery and Vertex CDC"
        content_bytes = content_text.encode("utf-8")
        gcs_uri = isvc.upload_bytes(str(tenant.id), content_bytes, "arch_p13.txt", "text/plain")
        result = isvc.ingest_bytes(str(tenant.id), content_bytes, "arch_p13.txt", "text/plain", project_id="p13-proj")
        assert result.gcs_uri == gcs_uri
        assert result.chunks_inserted >= 1
        assert captured_docs, "Expected Vertex CDC rows to be pushed"

        # Confirm dataset and table exist with expected schema
        bq_client = bigquery.Client(project=GCP_PROJECT)
        dataset_ref = f"{GCP_PROJECT}.tnt_{tenant.id}"
        assets_table = bq_client.get_table(f"{dataset_ref}.assets")
        field_names = [field.name for field in assets_table.schema]
        assert {"asset_id", "tenant_id", "metadata"}.issubset(field_names)

        # Compute asset_id
        asset_id = hashlib.md5((str(tenant.id) + gcs_uri).encode()).hexdigest()

        # Preview (base64) and download (signed URL)
        prev = await client.get(f"/assets/{asset_id}", headers=headers)
        assert prev.status_code == 200
        assert "base64" in prev.json()

        dl = await client.get(f"/assets/{asset_id}/download", headers=headers)
        assert dl.status_code == 200
        assert "url" in dl.json()

        # KB query should find the chunk
        from src.services.kb_query_service import KBQueryService
        kb = KBQueryService(project_id=GCP_PROJECT)
        results = kb.search(tenant_id=str(tenant.id), query="architecture", project_id="p13-proj", kb_type="project", limit=5)
        assert isinstance(results, list)

        # Root has rate-limit headers
        root = await client.get("/")
        assert root.headers.get("X-RateLimit-Limit") is not None
