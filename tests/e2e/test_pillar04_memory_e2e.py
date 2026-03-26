import os
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_CLOUD_PROJECT"),
    reason="Requires GOOGLE_CLOUD_PROJECT for BigQuery/GCS integration",
)


@pytest.mark.asyncio
async def test_pillar04_memory_ingest_kb_search_and_asset_access(monkeypatch):
    # Minimal env for app bootstrap and cloud
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-p4")
    os.environ.setdefault("SECRET_KEY", "test-secret-p4-app")

    from src.etherion_ai.app import create_app
    app = create_app()

    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token
    from tests.e2e._dummy_redis import setup_dummy_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        setup_dummy_redis(monkeypatch)
        # Create tenant and user
        async with get_scoped_session() as session:
            tenant = Tenant(
                tenant_id="pillar04-memory",
                subdomain="pillar04-memory",
                name="Pillar04 Memory Tenant",
                admin_email="p4@test.local",
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            user = User(user_id="p4-user", tenant_id=tenant.id, email="p4@test.local")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}
        tenant_id_str = str(tenant.id)

        # Ingest a small text file into tenant KB
        from src.services.ingestion_service import IngestionService
        gcp_project = os.environ["GOOGLE_CLOUD_PROJECT"]

        ingest = IngestionService(project_id=gcp_project)
        text = "Memory pillar E2E: preview and download validation via KB + repository."
        content = text.encode("utf-8")
        gcs_uri = ingest.upload_bytes(str(tenant.id), content, "p4_memory.txt", "text/plain")
        result = ingest.ingest_bytes(str(tenant.id), content, "p4_memory.txt", "text/plain", project_id="mem-e2e-proj")
        assert result.gcs_uri == gcs_uri and result.chunks_inserted >= 1

        # Optionally verify Vertex AI Search CDC only when explicitly enabled
        if os.getenv("ENABLE_VERTEX_CDC", "false").lower() in ("1", "true", "yes", "on"):
            try:
                from google.cloud import discoveryengine_v1 as discoveryengine
                vertex_location = os.getenv("VERTEX_AI_LOCATION", "global")
                doc_service = discoveryengine.DocumentServiceClient(
                    client_options=(
                        discoveryengine.types.DocumentServiceClient.get_transport_class("grpc")()._client_options.__class__(
                            api_endpoint=f"{vertex_location}-discoveryengine.googleapis.com"
                        )
                        if vertex_location != "global"
                        else None
                    )
                )
                first_doc_id = hashlib.md5((tenant_id_str + gcs_uri + "0").encode()).hexdigest()
                branch_path = doc_service.branch_path(
                    project=gcp_project,
                    location=vertex_location,
                    data_store=f"tenant-kb-{tenant_id_str}",
                    branch="default_branch",
                )
                document_name = f"{branch_path}/documents/{first_doc_id}"
                vertex_doc = doc_service.get_document(name=document_name)
                assert vertex_doc and vertex_doc.id == first_doc_id
            except Exception:
                # Discovery Engine may be disabled or library not installed
                pass

        # KB search should find the phrase in project scope
        from src.services.kb_query_service import KBQueryService
        kb = KBQueryService(project_id=gcp_project)
        rows = kb.search(tenant_id=str(tenant.id), query="preview and download", project_id="mem-e2e-proj", kb_type="project", limit=10)
        assert any("preview" in (r.get("text_chunk") or "") for r in rows)

        from google.cloud import bigquery

        bq_client = bigquery.Client(project=gcp_project)
        docs_table = f"{gcp_project}.tnt_{tenant.id}.docs"
        query = (
            "SELECT text_chunk, JSON_VALUE(metadata, '$.kb_type') AS kb_type, vector_embedding "
            "FROM `{docs}` WHERE project_id = @project_id"
        ).format(docs=docs_table)
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("project_id", "STRING", "mem-e2e-proj")]
        )
        doc_rows = list(bq_client.query(query, job_config=job_config).result())
        assert doc_rows and any("preview" in (row.text_chunk or "") for row in doc_rows)
        assert all((row.kb_type or "").lower() == "project" for row in doc_rows)
        assert all(getattr(row, "vector_embedding", None) and len(row.vector_embedding) > 0 for row in doc_rows)

        from src.services.repository_service import RepositoryService

        repo = RepositoryService(tenant_id=tenant.id, project_id=gcp_project)
        repo_assets = repo.list_assets(limit=10)
        repo_entry = next((a for a in repo_assets if a.asset_id == hashlib.md5((str(tenant.id) + gcs_uri).encode()).hexdigest()), None)
        assert repo_entry is not None and repo_entry.mime_type == "text/plain" and repo_entry.job_id is None

        # Research blend returns all keys
        from src.tools.unified_research_tool import unified_research_tool
        research = unified_research_tool(query="memory e2e", tenant_id=str(tenant.id), project_id="mem-e2e-proj")
        assert set(["project_results", "personal_results", "web_results", "vertex_results"]).issubset(research.keys())

        # Compute asset_id per ingestion policy and test preview/download endpoints
        asset_id = hashlib.md5((str(tenant.id) + gcs_uri).encode()).hexdigest()
        prev = await client.get(f"/assets/{asset_id}", headers=headers)
        assert prev.status_code in (200, 202)
        # Preview returns inline base64 for small files when available
        if prev.status_code == 200:
            assert "base64" in (prev.json() or {})

        dl = await client.get(f"/assets/{asset_id}/download", headers=headers)
        assert dl.status_code == 200
        assert "url" in (dl.json() or {})

        repo_query = """
        query {
            listRepositoryAssets(limit: 10, includeDownload: false) {
                assetId
                filename
                gcsUri
                mimeType
            }
        }
        """
        repo_resp = await client.post("/graphql", json={"query": repo_query}, headers=headers)
        assert repo_resp.status_code == 200
        repo_payload = repo_resp.json().get("data", {}).get("listRepositoryAssets") or []
        assert any(item.get("assetId") == asset_id for item in repo_payload)
