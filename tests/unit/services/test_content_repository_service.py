import os
import pytest
from unittest.mock import MagicMock, patch

from src.services.content_repository_service import ContentRepositoryService, MAX_INLINE_BYTES


PROJECT_ID = "test-project"


@pytest.fixture(autouse=True)
def set_env():
    with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": PROJECT_ID}):
        yield


def _make_row(data: dict):
    class R(dict):
        def get(self, k, default=None):
            return super().get(k, default)
    return R(data)


def test_list_assets_basic():
    svc = ContentRepositoryService(tenant_id="t1", project_id=PROJECT_ID)

    rows = [
        _make_row({
            "asset_id": "a1",
            "job_id": "job_1",
            "tenant_id": "t1",
            "agent_name": "agent_X",
            "agent_id": "X",
            "user_id": "u1",
            "mime_type": "application/pdf",
            "gcs_uri": "gs://tnt-t1-assets/X/job_1/doc.pdf",
            "filename": "doc.pdf",
            "size_bytes": 100,
            "created_at": "2025-10-04T00:00:00Z",
            "metadata": {"origin": "ai"}
        })
    ]

    with patch.object(svc.bq, "query") as q:
        q.return_value.result.return_value = rows
        assets, next_token = svc.list_assets(job_id="job_1", page_size=50)

    assert len(assets) == 1
    assert assets[0].asset_id == "a1"
    assert next_token is None


def test_get_access_inline_base64():
    svc = ContentRepositoryService(tenant_id="t1", project_id=PROJECT_ID)

    row = _make_row({
        "asset_id": "a1",
        "job_id": "job_1",
        "tenant_id": "t1",
        "agent_name": "agent_X",
        "agent_id": "X",
        "user_id": "u1",
        "mime_type": "text/plain",
        "gcs_uri": "gs://tnt-t1-assets/X/job_1/hello.txt",
        "filename": "hello.txt",
        "size_bytes": MAX_INLINE_BYTES,
        "created_at": "2025-10-04T00:00:00Z",
        "metadata": {"origin": "ai"}
    })

    # Mock BQ get
    with patch.object(svc, "get_asset", return_value=svc._row_to_asset(row)):
        # Mock GCS
        bucket = MagicMock()
        blob = MagicMock()
        blob.download_as_bytes.return_value = b"hello"
        bucket.blob.return_value = blob
        with patch.object(svc.storage, "bucket", return_value=bucket):
            access = svc.get_access("a1")

    assert access is not None
    assert "base64" in access
    assert access["mime_type"] == "text/plain"


def test_get_access_signed_url():
    svc = ContentRepositoryService(tenant_id="t1", project_id=PROJECT_ID)

    row = _make_row({
        "asset_id": "a2",
        "job_id": "job_2",
        "tenant_id": "t1",
        "agent_name": "agent_X",
        "agent_id": "X",
        "user_id": "u1",
        "mime_type": "application/pdf",
        "gcs_uri": "gs://tnt-t1-assets/X/job_2/big.pdf",
        "filename": "big.pdf",
        "size_bytes": MAX_INLINE_BYTES + 1,
        "created_at": "2025-10-04T00:00:00Z",
        "metadata": {"origin": "ai"}
    })

    with patch.object(svc, "get_asset", return_value=svc._row_to_asset(row)):
        bucket = MagicMock()
        blob = MagicMock()
        blob.generate_signed_url.return_value = "https://signed"
        bucket.blob.return_value = blob
        with patch.object(svc.storage, "bucket", return_value=bucket):
            access = svc.get_access("a2")

    assert access is not None
    assert access["url"] == "https://signed"
    assert access["expires_in_seconds"] == 300


