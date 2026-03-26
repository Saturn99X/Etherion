import os
import base64
import pytest

from src.services.content_repository_service import ContentRepositoryService, AssetRecord, MAX_INLINE_BYTES


class DummyBlob:
    def __init__(self, data: bytes):
        self._data = data

    def download_as_bytes(self):
        return self._data

    def generate_signed_url(self, version: str, expiration, method: str):
        return "https://signed.example/url"


class DummyBucket:
    def __init__(self, blob: DummyBlob):
        self._blob = blob

    def blob(self, name: str):
        return self._blob


class DummyStorage:
    def __init__(self, blob: DummyBlob):
        self._bucket = DummyBucket(blob)

    def bucket(self, name: str):
        return self._bucket


def make_record(size: int) -> AssetRecord:
    return AssetRecord(
        asset_id="a1",
        job_id="job1",
        tenant_id="1",
        agent_name=None,
        agent_id=None,
        user_id=None,
        mime_type="image/png",
        gcs_uri="gs://bucket/path/file.png",
        filename="file.png",
        size_bytes=size,
        created_at="2025-11-06T00:00:00Z",
        metadata={"origin": "ai"},
    )


@pytest.mark.asyncio
async def test_get_access_inline_base64(monkeypatch):
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "proj")
    svc = ContentRepositoryService(tenant_id="1", project_id="proj")

    # Patch get_asset and storage
    small = make_record(size=1024)
    monkeypatch.setattr(svc, "get_asset", lambda asset_id: small, raising=False)
    data = b"hello world"
    svc.storage = DummyStorage(DummyBlob(data))  # type: ignore[attr-defined]

    access = svc.get_access("a1")
    assert access is not None
    assert "base64" in access
    assert access["mime_type"] == "image/png"
    assert access["filename"] == "file.png"
    b64 = access["base64"].split(",")[-1]
    assert base64.b64decode(b64.encode("utf-8")) == data


@pytest.mark.asyncio
async def test_get_access_signed_url(monkeypatch):
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "proj")
    svc = ContentRepositoryService(tenant_id="1", project_id="proj")

    large = make_record(size=MAX_INLINE_BYTES + 1)
    monkeypatch.setattr(svc, "get_asset", lambda asset_id: large, raising=False)
    svc.storage = DummyStorage(DummyBlob(b"ignored"))  # type: ignore[attr-defined]

    access = svc.get_access("a1")
    assert access is not None
    assert "url" in access
    assert access["expires_in_seconds"] == 300
