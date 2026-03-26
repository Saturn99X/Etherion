import os
import json
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from src.tools.unified_research_tool import unified_research_tool

pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="Requires GOOGLE_CLOUD_PROJECT for BigQuery/GCS integration",
)


@pytest.mark.asyncio
async def test_pillar09_repository_listing_and_signed_urls():
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p9")
    os.environ.setdefault("SECRET_KEY", "test-secret-p9-app")

    from src.etherion_ai.app import create_app
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token
    from src.services.ingestion_service import IngestionService
    from src.services.repository_service import RepositoryService
    from src.services.bigquery_service import BigQueryService

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with get_scoped_session() as session:
            tenant = Tenant(
                tenant_id="pillar09-repo",
                subdomain="pillar09-repo",
                name="Pillar09 Repo Tenant",
                admin_email="p9@test.local",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            user = User(user_id="p9-user", tenant_id=tenant.id, email="p9@test.local")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        project_id = os.environ["GOOGLE_CLOUD_PROJECT"]
        ingest = IngestionService(project_id=project_id)
        content = b"Repository pillar asset sample for vertex-check"
        gcs_uri = ingest.upload_bytes(str(tenant.id), content, "pillar09.txt", "text/plain")
        ingest.ingest_bytes(str(tenant.id), content, "pillar09.txt", "text/plain", project_id="p9-proj")

        asset_id = hashlib.md5((str(tenant.id) + gcs_uri).encode()).hexdigest()

        bq = BigQueryService(project_id=project_id)
        dataset_id = f"tnt_{tenant.id}"
        row = {
            "asset_id": asset_id,
            "job_id": None,
            "tenant_id": str(tenant.id),
            "agent_name": "repo-tester",
            "agent_id": "repo-agent-1",
            "user_id": user.user_id,
            "mime_type": "text/plain",
            "gcs_uri": gcs_uri,
            "filename": "pillar09.txt",
            "size_bytes": len(content),
            "text_extract": "Pillar09 repo content",
            "description": "Repo coverage",
            "created_at": "2025-01-01T00:00:00Z",
            "metadata": json.dumps({"origin": "ai", "kb_type": "project"}),
        }
        bq.insert_rows_json(dataset_id, "assets", [row])

        service = RepositoryService(tenant_id=tenant.id, project_id=project_id)
        assets = service.list_assets(limit=5)
        assert any(a.asset_id == asset_id for a in assets)

        # GraphQL repository listing with jobId filter (metadata filtering simulated via jobId path)
        gql_query = (
            "query($job:String){ listRepositoryAssets(limit:5, jobId:$job){ assetId filename mimeType gcsUri downloadUrl } }"
        )
        gql_resp = await client.post("/graphql", json={"query": gql_query, "variables": {"job": None}}, headers=headers)
        assert gql_resp.status_code == 200
        data = gql_resp.json().get("data", {}).get("listRepositoryAssets", [])
        match = next((item for item in data if item["assetId"] == asset_id), None)
        assert match is not None
        assert match["filename"] == "pillar09.txt"
        assert match["downloadUrl"]

        preview = await client.get(f"/assets/{asset_id}", headers=headers)
        assert preview.status_code == 200
        assert "base64" in preview.json()

        download = await client.get(f"/assets/{asset_id}/download", headers=headers)
        assert download.status_code == 200
        assert "url" in download.json()

        # Verify Vertex AI Search received CDC by checking unified_research_tool results
        research = unified_research_tool(query="vertex-check", tenant_id=str(tenant.id), project_id="p9-proj")
        # We expect either project_results or vertex_results to include our file_uri
        assert isinstance(research, dict)
        any_list = (research.get("vertex_results") or []) + (research.get("project_results") or [])
        assert any(isinstance(item, dict) and (item.get("file_uri") == gcs_uri or item.get("gcs_uri") == gcs_uri) for item in any_list)

        # Ingest a large file (>5MB) and ensure signed URL behavior
        big_bytes = b"A" * (6 * 1024 * 1024)
        big_uri = ingest.upload_bytes(str(tenant.id), big_bytes, "pillar09_big.bin", "application/octet-stream")
        ingest.ingest_bytes(str(tenant.id), big_bytes, "pillar09_big.bin", "application/octet-stream", project_id="p9-proj")
        big_id = hashlib.md5((str(tenant.id) + big_uri).encode()).hexdigest()
        prev_big = await client.get(f"/assets/{big_id}", headers=headers)
        # Large assets should not inline base64; service may return 202 for async preview generation
        assert prev_big.status_code in (200, 202)
        if prev_big.status_code == 200:
            assert "base64" not in (prev_big.json() or {})
        big_dl = await client.get(f"/assets/{big_id}/download", headers=headers)
        assert big_dl.status_code == 200 and "url" in (big_dl.json() or {})
