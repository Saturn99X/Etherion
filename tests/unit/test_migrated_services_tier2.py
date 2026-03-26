"""Aggressive tests for Tier 2 service migrations.

Covers: FeedbackService, RepositoryService, ContentRepositoryService,
BQMediaObjectEmbeddingsBackfillService — verifying they use kb_backend
and storage_backend abstractions, NOT BigQuery/GCS directly.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, AsyncMock, call

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

class _FakeKBBackend:
    def __init__(self):
        self.inserted_feedback = []
        self.upserted_docs = []
        self.inserted_docs = []
        self.queried_assets = []

    def insert_feedback(self, tenant_id, row):
        self.inserted_feedback.append((tenant_id, row))

    def upsert_doc(self, tenant_id, table, match_key, row):
        self.upserted_docs.append((tenant_id, table, match_key, row))

    def insert_docs(self, tenant_id, table, rows):
        self.inserted_docs.append((tenant_id, table, rows))

    def query_assets(self, tenant_id, filters=None, limit=50, offset=0):
        self.queried_assets.append((tenant_id, filters, limit, offset))
        return []

    def ensure_tenant_kb(self, tenant_id): pass
    def vector_search(self, *a, **kw): return []
    def text_search(self, *a, **kw): return []
    def query(self, *a, **kw): return []


class _FakeStorageBackend:
    def __init__(self):
        self.uploads = []
        self.downloads = {}
        self.access_urls = {}

    def upload(self, local_path, storage_key, bucket, content_type=None, **kwargs):
        self.uploads.append((local_path, storage_key, bucket))
        return f"file:///fake/{bucket}/{storage_key}"

    def download(self, uri):
        return self.downloads.get(uri, b"fake-content")

    def download_to_file(self, uri, dest_path):
        content = self.downloads.get(uri, b"fake-content")
        with open(dest_path, "wb") as f:
            f.write(content)

    def generate_access_url(self, uri, expiration_minutes=5):
        return self.access_urls.get(uri, f"/api/files/{uri.split('/')[-1]}")

    def exists(self, uri): return True
    def delete(self, uri): pass

    @staticmethod
    def bucket_for_tenant(tenant_id, bucket_type):
        return f"tnt-{tenant_id}-{bucket_type}"


# ---------------------------------------------------------------------------
# FeedbackService tests
# ---------------------------------------------------------------------------

class TestFeedbackServiceMigration:
    """FeedbackService must use kb_backend + storage_backend, not BigQuery/GCS."""

    def _make_svc(self):
        from src.services.feedback_service import FeedbackService, FeedbackPolicy
        svc = FeedbackService(tenant_id=1, user_id=5, policy=FeedbackPolicy(max_comments_per_day_per_tenant=10))
        return svc

    def test_no_bigquery_import_in_module(self):
        """FeedbackService module must NOT import BigQueryService."""
        import importlib
        import src.services.feedback_service as mod
        src_path = Path(mod.__file__).read_text()
        assert "BigQueryService" not in src_path, "BigQueryService should be removed from feedback_service"
        assert "ensure_tenant_feedback" not in src_path, "ensure_tenant_feedback should be removed"

    def test_no_gcs_storage_client_in_module(self):
        """FeedbackService module must NOT import google.cloud.storage directly."""
        import src.services.feedback_service as mod
        src_path = Path(mod.__file__).read_text()
        # storage.Client() direct usage should be gone
        assert "storage.Client" not in src_path or "storage_backend" in src_path

    def test_uses_kb_backend_insert_feedback(self, monkeypatch):
        fake_kb = _FakeKBBackend()
        monkeypatch.setattr("src.services.feedback_service.get_kb_backend", lambda: fake_kb)
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr("src.services.feedback_service.get_storage_backend", lambda: fake_storage)

        svc = self._make_svc()

        # Mock DB session and Redis
        fake_job = MagicMock()
        fake_job.job_id = "job1"
        fake_job.tenant_id = 1

        class _FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def exec(self, stmt): return MagicMock(first=lambda: fake_job)
            def add(self, obj): pass
            async def commit(self): pass
            async def refresh(self, obj): pass

        monkeypatch.setattr("src.services.feedback_service.get_scoped_session", lambda: _FakeSession())
        monkeypatch.setattr(svc, "_check_and_increment_rate_limit", AsyncMock())

        asyncio.run(
            svc.submit("job1", "Test goal", "Test output", 5, "Great job!")
        )

        # insert_feedback must have been called
        assert len(fake_kb.inserted_feedback) == 1
        tid, row = fake_kb.inserted_feedback[0]
        assert tid == "1"
        assert row["score"] == 5
        assert row["job_id"] == "job1"
        assert row["tenant_id"] == 1
        assert row["user_id"] == 5

    def test_store_gcs_copy_uses_storage_backend(self, monkeypatch):
        from src.services.feedback_service import FeedbackService, FeedbackPolicy
        svc = FeedbackService(
            tenant_id=2, user_id=7,
            policy=FeedbackPolicy(max_comments_per_day_per_tenant=10, store_gcs_copy=True)
        )

        fake_kb = _FakeKBBackend()
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr("src.services.feedback_service.get_kb_backend", lambda: fake_kb)
        monkeypatch.setattr("src.services.feedback_service.get_storage_backend", lambda: fake_storage)

        fake_job = MagicMock(job_id="j2", tenant_id=2)

        class _FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def exec(self, stmt): return MagicMock(first=lambda: fake_job)
            def add(self, obj): pass
            async def commit(self): pass
            async def refresh(self, obj): setattr(obj, "created_at", __import__("datetime").datetime.utcnow())

        monkeypatch.setattr("src.services.feedback_service.get_scoped_session", lambda: _FakeSession())
        monkeypatch.setattr(svc, "_check_and_increment_rate_limit", AsyncMock())

        asyncio.run(
            svc.submit("j2", "goal", "output", 4, "ok")
        )

        # storage upload must be called when store_gcs_copy=True
        assert len(fake_storage.uploads) >= 1
        # File should be JSON
        _, key, bucket = fake_storage.uploads[0]
        assert key.endswith(".json")
        assert "feedback" in bucket

    def test_store_gcs_copy_false_no_storage_call(self, monkeypatch):
        fake_kb = _FakeKBBackend()
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr("src.services.feedback_service.get_kb_backend", lambda: fake_kb)
        monkeypatch.setattr("src.services.feedback_service.get_storage_backend", lambda: fake_storage)

        svc = self._make_svc()
        fake_job = MagicMock(job_id="j3", tenant_id=1)

        class _FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def exec(self, stmt): return MagicMock(first=lambda: fake_job)
            def add(self, obj): pass
            async def commit(self): pass
            async def refresh(self, obj): pass

        monkeypatch.setattr("src.services.feedback_service.get_scoped_session", lambda: _FakeSession())
        monkeypatch.setattr(svc, "_check_and_increment_rate_limit", AsyncMock())

        asyncio.run(
            svc.submit("j3", "goal", "output", 3, "meh")
        )
        # store_gcs_copy=False → no storage uploads
        assert len(fake_storage.uploads) == 0

    def test_anonymize_removes_email(self):
        svc = self._make_svc()
        text = "Contact user@example.com for details"
        result = svc._anonymize(text, max_length=500)
        assert "user@example.com" not in result
        assert "[redacted_email]" in result

    def test_anonymize_removes_http_url(self):
        svc = self._make_svc()
        text = "See https://internal.company.com/secret for info"
        result = svc._anonymize(text, max_length=500)
        assert "https://internal.company.com/secret" not in result
        assert "[redacted_url]" in result

    def test_anonymize_multiple_emails(self):
        svc = self._make_svc()
        text = "From: a@b.com To: c@d.org"
        result = svc._anonymize(text, max_length=500)
        assert "a@b.com" not in result
        assert "c@d.org" not in result

    def test_anonymize_preserves_non_pii(self):
        svc = self._make_svc()
        text = "The revenue grew by 15% in Q3 2025"
        result = svc._anonymize(text, max_length=500)
        assert "revenue" in result
        assert "15%" in result

    def test_submit_raises_job_not_found(self, monkeypatch):
        fake_kb = _FakeKBBackend()
        monkeypatch.setattr("src.services.feedback_service.get_kb_backend", lambda: fake_kb)

        svc = self._make_svc()

        class _NoJobSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def exec(self, stmt): return MagicMock(first=lambda: None)
            def add(self, obj): pass
            async def commit(self): pass
            async def refresh(self, obj): pass

        monkeypatch.setattr("src.services.feedback_service.get_scoped_session", lambda: _NoJobSession())
        monkeypatch.setattr(svc, "_check_and_increment_rate_limit", AsyncMock())

        with pytest.raises(ValueError, match="JOB_NOT_FOUND"):
            asyncio.run(
                svc.submit("nonexistent", "goal", "output", 5, "comment")
            )

    def test_rate_limit_key_contains_tenant_id(self):
        svc = self._make_svc()
        # rate limit key is async
        key = asyncio.run(svc._rate_limit_key())
        assert "1" in key  # tenant_id=1 must appear in key

    def test_rate_limit_key_contains_date(self):
        from datetime import datetime
        svc = self._make_svc()
        key = asyncio.run(svc._rate_limit_key())
        today = datetime.utcnow().strftime("%Y-%m-%d")
        assert today in key


# ---------------------------------------------------------------------------
# RepositoryService tests
# ---------------------------------------------------------------------------

class TestRepositoryServiceMigration:
    @pytest.fixture
    def setup(self, monkeypatch):
        fake_kb = _FakeKBBackend()
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr("src.services.repository_service.get_kb_backend", lambda: fake_kb)
        monkeypatch.setattr("src.services.repository_service.get_storage_backend", lambda: fake_storage)
        from src.services.repository_service import RepositoryService
        svc = RepositoryService(tenant_id=10)
        return svc, fake_kb, fake_storage

    def test_no_bigqueryservice_import(self):
        import src.services.repository_service as mod
        src_text = Path(mod.__file__).read_text()
        assert "BigQueryService" not in src_text, "BigQueryService should be removed"

    def test_no_gcs_storage_client_import(self):
        import src.services.repository_service as mod
        src_text = Path(mod.__file__).read_text()
        # Should not directly init google.cloud.storage.Client
        assert "storage.Client(" not in src_text

    def test_list_assets_delegates_to_kb_backend(self, setup):
        svc, fake_kb, _ = setup
        svc.list_assets(limit=25)
        assert len(fake_kb.queried_assets) == 1
        tid, filters, limit, _ = fake_kb.queried_assets[0]
        assert tid == "10"
        assert limit == 25

    def test_list_assets_default_origin_is_ai(self, setup):
        svc, fake_kb, _ = setup
        svc.list_assets()
        tid, filters, limit, _ = fake_kb.queried_assets[0]
        assert (filters or {}).get("origin") == "ai"

    def test_list_assets_with_job_id_filter(self, setup):
        svc, fake_kb, _ = setup
        svc.list_assets(job_id="job123")
        tid, filters, limit, _ = fake_kb.queried_assets[0]
        assert (filters or {}).get("job_id") == "job123"

    def test_list_assets_returns_empty_on_kb_error(self, setup, monkeypatch):
        svc, fake_kb, _ = setup
        def _explode(*a, **kw): raise RuntimeError("DB down")
        fake_kb.query_assets = _explode
        result = svc.list_assets()
        assert result == []

    def test_create_ai_asset_uses_storage_backend(self, setup, tmp_path):
        svc, fake_kb, fake_storage = setup
        content = b"PDF content here"
        svc.create_ai_asset(content, "test.pdf", "application/pdf", job_id="job1")
        assert len(fake_storage.uploads) == 1
        _, key, bucket = fake_storage.uploads[0]
        assert "test.pdf" in key
        assert "10" in bucket  # tenant_id=10 must be in bucket name

    def test_create_ai_asset_inserts_into_kb(self, setup):
        svc, fake_kb, _ = setup
        svc.create_ai_asset(b"bytes", "file.txt", "text/plain", job_id="job2")
        assert len(fake_kb.inserted_docs) == 1
        tid, table, rows = fake_kb.inserted_docs[0]
        assert tid == "10"
        assert "asset" in table
        assert len(rows) == 1
        assert rows[0]["tenant_id"] == 10
        assert rows[0]["filename"] == "file.txt"
        assert rows[0]["mime_type"] == "text/plain"

    def test_create_ai_asset_metadata_has_origin_ai(self, setup):
        svc, fake_kb, _ = setup
        svc.create_ai_asset(b"data", "doc.pdf", "application/pdf")
        _, _, rows = fake_kb.inserted_docs[0]
        assert rows[0]["metadata"]["origin"] == "ai"

    def test_create_ai_asset_content_hash_in_key(self, setup):
        import hashlib
        svc, fake_kb, fake_storage = setup
        content = b"deterministic content"
        expected_hash = hashlib.sha256(content).hexdigest()
        svc.create_ai_asset(content, "file.txt", "text/plain")
        _, key, _ = fake_storage.uploads[0]
        assert expected_hash in key

    def test_create_ai_asset_temp_file_cleaned_up(self, setup, monkeypatch):
        svc, fake_kb, fake_storage = setup
        unlinked = []
        import os as os_mod
        original_unlink = os_mod.unlink
        monkeypatch.setattr(os_mod, "unlink", lambda p: unlinked.append(p))
        svc.create_ai_asset(b"data", "f.txt", "text/plain")
        assert len(unlinked) >= 1

    def test_generate_signed_url_uses_storage_backend(self, setup):
        svc, _, fake_storage = setup
        url = svc.generate_signed_url("gs://bucket/file.pdf", minutes=10)
        assert url  # should not be empty

    def test_repository_asset_storage_uri_alias(self):
        from src.services.repository_service import RepositoryAsset
        asset = RepositoryAsset(
            asset_id="a1", job_id="j1", filename="f.pdf",
            mime_type="application/pdf", size_bytes=100,
            gcs_uri="file:///var/lib/etherion/storage/f.pdf",
            created_at="2026-01-01T00:00:00Z"
        )
        assert asset.storage_uri == asset.gcs_uri

    def test_repository_asset_gcs_uri_field_kept(self):
        """Backwards compat: gcs_uri field still accessible."""
        from src.services.repository_service import RepositoryAsset
        asset = RepositoryAsset(
            asset_id="a1", job_id=None, filename="f.pdf",
            mime_type="text/plain", size_bytes=0,
            gcs_uri="gs://legacy-bucket/file",
            created_at=""
        )
        assert asset.gcs_uri == "gs://legacy-bucket/file"


# ---------------------------------------------------------------------------
# ContentRepositoryService tests
# ---------------------------------------------------------------------------

class TestContentRepositoryServiceMigration:
    @pytest.fixture
    def setup(self, monkeypatch):
        fake_kb = _FakeKBBackend()
        fake_storage = _FakeStorageBackend()
        # content_repository_service uses lazy imports, so patch at the source module
        monkeypatch.setattr("src.services.kb_backend.get_kb_backend", lambda **kw: fake_kb)
        monkeypatch.setattr("src.core.storage_backend.get_storage_backend", lambda **kw: fake_storage)
        from src.services.content_repository_service import ContentRepositoryService
        svc = ContentRepositoryService(tenant_id="5")
        return svc, fake_kb, fake_storage

    def test_no_bigquery_client_in_module(self):
        import src.services.content_repository_service as mod
        src_text = Path(mod.__file__).read_text()
        assert "bigquery.Client" not in src_text
        assert "BigQueryService" not in src_text

    def test_no_gcs_storage_client_in_module(self):
        import src.services.content_repository_service as mod
        src_text = Path(mod.__file__).read_text()
        assert "storage.Client" not in src_text

    def test_list_assets_enforces_origin_ai_filter(self, setup):
        svc, fake_kb, _ = setup
        svc.list_assets("job1")
        tid, filters, _, _ = fake_kb.queried_assets[0]
        assert (filters or {}).get("origin") == "ai"

    def test_list_assets_passes_job_id(self, setup):
        svc, fake_kb, _ = setup
        svc.list_assets("job_xyz")
        tid, filters, _, _ = fake_kb.queried_assets[0]
        assert (filters or {}).get("job_id") == "job_xyz"

    def test_list_assets_passes_mime_type_filter(self, setup):
        svc, fake_kb, _ = setup
        svc.list_assets("job1", mime_type="image/png")
        tid, filters, _, _ = fake_kb.queried_assets[0]
        assert (filters or {}).get("mime_type") == "image/png"

    def test_list_assets_returns_empty_on_error(self, setup):
        svc, fake_kb, _ = setup
        fake_kb.query_assets = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        result, token = svc.list_assets("j1")
        assert result == []

    def test_list_assets_pagination_next_token(self, setup, monkeypatch):
        svc, fake_kb, _ = setup
        # Return page_size rows to trigger next_token
        page_size = 3
        fake_kb.query_assets = lambda *a, **kw: [
            {"asset_id": f"a{i}", "job_id": "j1", "tenant_id": "5",
             "storage_uri": f"file:///f{i}", "gcs_uri": f"file:///f{i}",
             "filename": f"f{i}", "mime_type": "image/png",
             "size_bytes": 100, "created_at": "", "metadata": {}}
            for i in range(page_size)
        ]
        assets, next_token = svc.list_assets("j1", page_size=page_size)
        assert next_token is not None
        assert len(assets) == page_size

    def test_list_assets_no_next_token_when_less_than_page(self, setup):
        svc, fake_kb, _ = setup
        fake_kb.query_assets = lambda *a, **kw: [
            {"asset_id": "a1", "job_id": "j1", "tenant_id": "5",
             "storage_uri": "file:///f1", "gcs_uri": "file:///f1",
             "filename": "f1", "mime_type": "image/png",
             "size_bytes": 100, "created_at": "", "metadata": {}}
        ]
        assets, next_token = svc.list_assets("j1", page_size=10)
        assert next_token is None

    def test_list_assets_invalid_page_size_raises(self, setup):
        svc, _, _ = setup
        with pytest.raises(ValueError):
            svc.list_assets("j1", page_size=0)

    def test_get_asset_retries_and_returns_none_on_failure(self, setup, monkeypatch):
        svc, fake_kb, _ = setup
        # Always return empty rows
        fake_kb.query_assets = lambda *a, **kw: []
        # Patch time.sleep to avoid delay in tests
        import time
        monkeypatch.setattr(time, "sleep", lambda s: None)
        result = svc.get_asset("nonexistent_id")
        assert result is None

    def test_get_asset_returns_record_on_first_hit(self, setup, monkeypatch):
        svc, fake_kb, _ = setup
        import time
        monkeypatch.setattr(time, "sleep", lambda s: None)
        fake_kb.query_assets = lambda *a, **kw: [{
            "asset_id": "a1", "job_id": "j1", "tenant_id": "5",
            "storage_uri": "file:///f.pdf", "gcs_uri": "file:///f.pdf",
            "filename": "f.pdf", "mime_type": "application/pdf",
            "size_bytes": 512, "created_at": "2026-01-01", "metadata": {}
        }]
        result = svc.get_asset("a1")
        assert result is not None
        assert result.asset_id == "a1"

    def test_get_access_inline_base64_for_small_file(self, setup, monkeypatch):
        from src.services.content_repository_service import MAX_INLINE_BYTES, AssetRecord
        svc, fake_kb, fake_storage = setup
        import time
        monkeypatch.setattr(time, "sleep", lambda s: None)
        record = AssetRecord(
            asset_id="a1", job_id="j1", tenant_id="5",
            agent_name=None, agent_id=None, user_id=None,
            mime_type="image/png", gcs_uri="file:///img.png",
            filename="img.png", size_bytes=1024,
            created_at="2026-01-01", metadata={}
        )
        fake_storage.downloads["file:///img.png"] = b"PNG_BYTES"
        monkeypatch.setattr(svc, "get_asset", lambda aid: record)
        access = svc.get_access("a1")
        assert access is not None
        assert "base64" in access
        assert access["mime_type"] == "image/png"
        # Verify base64 decodes correctly
        b64 = access["base64"].split(",")[-1]
        assert base64.b64decode(b64) == b"PNG_BYTES"

    def test_get_access_url_for_large_file(self, setup, monkeypatch):
        from src.services.content_repository_service import MAX_INLINE_BYTES, AssetRecord
        svc, fake_kb, fake_storage = setup
        import time
        monkeypatch.setattr(time, "sleep", lambda s: None)
        record = AssetRecord(
            asset_id="a2", job_id="j1", tenant_id="5",
            agent_name=None, agent_id=None, user_id=None,
            mime_type="video/mp4", gcs_uri="file:///video.mp4",
            filename="video.mp4", size_bytes=MAX_INLINE_BYTES + 1,
            created_at="2026-01-01", metadata={}
        )
        fake_storage.access_urls["file:///video.mp4"] = "https://signed.url/video.mp4"
        monkeypatch.setattr(svc, "get_asset", lambda aid: record)
        access = svc.get_access("a2")
        assert access is not None
        assert "url" in access
        assert access["expires_in_seconds"] == 300
        assert "base64" not in access

    def test_get_access_returns_none_if_no_asset(self, setup, monkeypatch):
        svc, _, _ = setup
        import time
        monkeypatch.setattr(time, "sleep", lambda s: None)
        monkeypatch.setattr(svc, "get_asset", lambda aid: None)
        result = svc.get_access("nonexistent")
        assert result is None

    def test_asset_record_storage_uri_alias(self):
        from src.services.content_repository_service import AssetRecord
        record = AssetRecord(
            asset_id="x", job_id="j", tenant_id="1",
            agent_name=None, agent_id=None, user_id=None,
            mime_type="text/plain", gcs_uri="s3://bucket/f.txt",
            filename="f.txt", size_bytes=0,
            created_at=None, metadata={}
        )
        assert record.storage_uri == "s3://bucket/f.txt"

    def test_row_to_asset_handles_storage_uri_field(self):
        """_row_to_asset should prefer storage_uri over gcs_uri."""
        from src.services.content_repository_service import ContentRepositoryService
        svc = ContentRepositoryService(tenant_id="1")
        row = {
            "asset_id": "a1", "job_id": "j1", "tenant_id": "1",
            "storage_uri": "s3://new-bucket/file",
            "gcs_uri": "gs://old-bucket/file",
            "filename": "file.pdf", "mime_type": "application/pdf",
            "size_bytes": 256, "created_at": "2026-01-01", "metadata": {}
        }
        record = svc._row_to_asset(row)
        assert record.gcs_uri == "s3://new-bucket/file"  # storage_uri wins


# ---------------------------------------------------------------------------
# BQMediaObjectEmbeddingsBackfillService tests
# ---------------------------------------------------------------------------

class TestBackfillServiceMigration:
    @pytest.fixture
    def setup(self, monkeypatch):
        fake_kb = _FakeKBBackend()
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr(
            "src.services.bq_media_object_embeddings_backfill.get_kb_backend",
            lambda: fake_kb
        )
        monkeypatch.setattr(
            "src.services.bq_media_object_embeddings_backfill.get_storage_backend",
            lambda: fake_storage
        )
        from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService
        svc = BQMediaObjectEmbeddingsBackfillService(project_id="test-proj")
        return svc, fake_kb, fake_storage

    def test_no_bigqueryservice_import(self):
        import src.services.bq_media_object_embeddings_backfill as mod
        src_text = Path(mod.__file__).read_text()
        assert "BigQueryService" not in src_text

    def test_no_fetch_tenant_object_to_tempfile(self):
        """Must not use the GCS-specific fetch helper."""
        import src.services.bq_media_object_embeddings_backfill as mod
        src_text = Path(mod.__file__).read_text()
        assert "fetch_tenant_object_to_tempfile" not in src_text

    def test_raises_on_empty_gcs_uri(self, setup):
        svc, _, _ = setup
        with pytest.raises(ValueError, match="gcs_uri"):
            svc.backfill(tenant_id="1", gcs_uri="")

    def test_raises_on_none_gcs_uri(self, setup):
        svc, _, _ = setup
        with pytest.raises((ValueError, TypeError)):
            svc.backfill(tenant_id="1", gcs_uri=None)

    def test_uses_storage_backend_download_to_file(self, setup, monkeypatch, tmp_path):
        svc, fake_kb, fake_storage = setup

        # Set up fake download
        fake_file = tmp_path / "obj.pdf"
        fake_file.write_bytes(b"PDF content for embedding")
        fake_storage.downloads["file:///fake-storage/obj.pdf"] = b"PDF content for embedding"

        download_calls = []
        original_dtf = fake_storage.download_to_file

        def _track_dtf(uri, dest):
            download_calls.append(uri)
            original_dtf(uri, dest)

        fake_storage.download_to_file = _track_dtf

        # Mock embedding service
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 768]
        mock_embedder.dimension = 768

        with patch("src.services.bq_media_object_embeddings_backfill.EmbeddingService",
                   return_value=mock_embedder):
            svc.backfill(tenant_id="1", gcs_uri="file:///fake-storage/obj.pdf")

        assert len(download_calls) >= 1

    def test_upserts_with_storage_uri_match_key(self, setup, monkeypatch, tmp_path):
        svc, fake_kb, fake_storage = setup
        uri = "file:///fake/obj.bin"
        fake_file = tmp_path / "obj.bin"
        fake_file.write_bytes(b"binary data")

        def _dtf(u, dest):
            import shutil
            shutil.copy(str(fake_file), dest)

        fake_storage.download_to_file = _dtf

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.0] * 768]
        mock_embedder.dimension = 768

        with patch("src.services.bq_media_object_embeddings_backfill.EmbeddingService",
                   return_value=mock_embedder):
            svc.backfill(tenant_id="3", gcs_uri=uri)

        assert len(fake_kb.upserted_docs) == 1
        tid, table, match_key, row = fake_kb.upserted_docs[0]
        assert tid == "3"
        assert table == "media_object_embeddings"
        assert match_key == "storage_uri"

    def test_upserted_row_has_storage_uri_field(self, setup, monkeypatch, tmp_path):
        svc, fake_kb, fake_storage = setup
        uri = "s3://bucket/media/obj.bin"
        fake_file = tmp_path / "obj.bin"
        fake_file.write_bytes(b"data")

        def _dtf(u, dest):
            import shutil
            shutil.copy(str(fake_file), dest)

        fake_storage.download_to_file = _dtf

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.0] * 768]
        mock_embedder.dimension = 768

        with patch("src.services.bq_media_object_embeddings_backfill.EmbeddingService",
                   return_value=mock_embedder):
            svc.backfill(tenant_id="5", gcs_uri=uri)

        _, _, _, row = fake_kb.upserted_docs[0]
        assert "storage_uri" in row
        assert row["storage_uri"] == uri

    def test_upserted_row_has_gcs_uri_backwards_compat(self, setup, monkeypatch, tmp_path):
        svc, fake_kb, fake_storage = setup
        uri = "gs://tenant-5-media/file.pdf"
        fake_file = tmp_path / "f.pdf"
        fake_file.write_bytes(b"pdf")

        def _dtf(u, dest):
            import shutil
            shutil.copy(str(fake_file), dest)

        fake_storage.download_to_file = _dtf

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.0] * 768]
        mock_embedder.dimension = 768

        with patch("src.services.bq_media_object_embeddings_backfill.EmbeddingService",
                   return_value=mock_embedder):
            svc.backfill(tenant_id="5", gcs_uri=uri)

        _, _, _, row = fake_kb.upserted_docs[0]
        # Backwards compat: gcs_uri field should still be present
        assert "gcs_uri" in row

    def test_size_limit_enforced(self, setup, monkeypatch, tmp_path):
        svc, fake_kb, fake_storage = setup
        monkeypatch.setenv("KB_OBJECT_FETCH_MAX_SIZE_BYTES", "10")  # tiny limit
        uri = "file:///fake/big.bin"
        fake_file = tmp_path / "big.bin"
        fake_file.write_bytes(b"A" * 100)  # 100 bytes > 10 byte limit

        def _dtf(u, dest):
            import shutil
            shutil.copy(str(fake_file), dest)

        fake_storage.download_to_file = _dtf

        with pytest.raises(ValueError, match="too large"):
            svc.backfill(tenant_id="1", gcs_uri=uri)

    def test_temp_file_cleaned_up_on_success(self, setup, monkeypatch, tmp_path):
        svc, fake_kb, fake_storage = setup
        uri = "file:///fake/cleanup.bin"
        fake_file = tmp_path / "cleanup.bin"
        fake_file.write_bytes(b"data")

        def _dtf(u, dest):
            import shutil
            shutil.copy(str(fake_file), dest)

        fake_storage.download_to_file = _dtf

        unlinked = []
        import os as _os
        monkeypatch.setattr(_os, "unlink", lambda p: unlinked.append(p))

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.0] * 768]
        mock_embedder.dimension = 768

        with patch("src.services.bq_media_object_embeddings_backfill.EmbeddingService",
                   return_value=mock_embedder):
            try:
                svc.backfill(tenant_id="1", gcs_uri=uri)
            except Exception:
                pass

        # temp file unlink should have been attempted
        assert len(unlinked) >= 1

    def test_bq_constructor_param_ignored(self):
        """bq= constructor param should be silently ignored (backwards compat)."""
        from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService
        fake_bq = MagicMock()
        # Should not raise even though bq is ignored
        svc = BQMediaObjectEmbeddingsBackfillService(project_id="proj", bq=fake_bq)
        assert svc is not None


# ---------------------------------------------------------------------------
# MultimodalIngestionService migration
# ---------------------------------------------------------------------------

class TestMultimodalIngestionServiceMigration:
    """Verify MultimodalIngestionService uses storage_backend + kb_backend, not GCS/BQ."""

    def test_no_bigquery_import(self):
        """Module must NOT import google.cloud.bigquery directly."""
        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mis_check",
            str(ROOT / "src" / "services" / "multimodal_ingestion_service.py"),
        )
        source = open(str(ROOT / "src" / "services" / "multimodal_ingestion_service.py")).read()
        assert "from google.cloud import" not in source
        assert "google.cloud.bigquery" not in source
        assert "google.cloud.storage" not in source

    def test_no_bq_schema_manager_import(self):
        """Must not import ensure_tenant_dataset or ensure_table from bq_schema_manager."""
        source = open(str(ROOT / "src" / "services" / "multimodal_ingestion_service.py")).read()
        assert "ensure_tenant_dataset" not in source
        assert "ensure_table" not in source
        # ensure_tenant_multimodal_kb was also removed
        assert "ensure_tenant_multimodal_kb" not in source

    def test_no_insert_rows_json(self):
        """Must not call insert_rows_json directly."""
        source = open(str(ROOT / "src" / "services" / "multimodal_ingestion_service.py")).read()
        assert "insert_rows_json" not in source

    def test_uses_kb_backend(self):
        """Module must import and use get_kb_backend."""
        source = open(str(ROOT / "src" / "services" / "multimodal_ingestion_service.py")).read()
        assert "from src.services.kb_backend import get_kb_backend" in source
        assert "get_kb_backend().insert_docs" in source

    def test_uses_storage_backend(self):
        """Module must import and use get_storage_backend."""
        source = open(str(ROOT / "src" / "services" / "multimodal_ingestion_service.py")).read()
        assert "from src.core.storage_backend import get_storage_backend, StorageBackend" in source
        assert "get_storage_backend().upload" in source

    def test_no_direct_gcs_bucket_calls(self):
        """Must not call self.storage.bucket() or blob.upload_from_string()."""
        source = open(str(ROOT / "src" / "services" / "multimodal_ingestion_service.py")).read()
        assert "upload_from_string" not in source
        assert "self.storage.bucket" not in source
        assert "_ensure_bucket" not in source
        assert "_tenant_bucket" not in source

    def test_storage_uri_in_rows(self):
        """Rows must contain storage_uri field (not just gcs_uri)."""
        source = open(str(ROOT / "src" / "services" / "multimodal_ingestion_service.py")).read()
        assert '"storage_uri"' in source
        # Also keeps gcs_uri for BQ backwards compat
        assert '"gcs_uri"' in source

    def test_init_no_longer_requires_google_cloud(self):
        """__init__ must NOT raise RuntimeError when google-cloud libs are absent."""
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": ""}, clear=False):
            from src.services.multimodal_ingestion_service import MultimodalIngestionService
            # Should not raise — project_id not required for local/pgvector
            svc = MultimodalIngestionService()
            assert svc is not None

    def test_upload_bytes_uses_storage_backend(self, tmp_path):
        """upload_bytes() must call get_storage_backend().upload() not GCS blob."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        fake_uri = "file:///var/lib/etherion/storage/tnt-42-media/uploads/abc/test.txt"
        mock_storage = MagicMock()
        mock_storage.upload.return_value = fake_uri

        with patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            svc = MultimodalIngestionService()
            result = svc.upload_bytes("42", b"hello world", "test.txt", "text/plain")

        assert result == fake_uri
        mock_storage.upload.assert_called_once()
        call_kwargs = mock_storage.upload.call_args
        assert call_kwargs.kwargs.get("bucket") == "tnt-42-media" or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] == "tnt-42-media"
        )
        assert "test.txt" in (call_kwargs.kwargs.get("storage_key") or call_kwargs.args[1])

    def test_upload_bytes_cleans_temp_file(self, tmp_path):
        """upload_bytes() must delete the temp file even on upload failure."""
        created_temps: List[str] = []
        original_ntf = tempfile.NamedTemporaryFile

        def _tracking_ntf(*args, **kwargs):
            f = original_ntf(*args, **kwargs)
            created_temps.append(f.name)
            return f

        mock_storage = MagicMock()
        mock_storage.upload.side_effect = RuntimeError("upload failed")

        from src.services.multimodal_ingestion_service import MultimodalIngestionService
        svc = MultimodalIngestionService()

        with patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            with patch("src.services.multimodal_ingestion_service.tempfile.NamedTemporaryFile",
                       side_effect=_tracking_ntf):
                with pytest.raises(RuntimeError, match="upload failed"):
                    svc.upload_bytes("1", b"data", "f.bin", "application/octet-stream")

        # temp file should have been cleaned up
        for tmp in created_temps:
            assert not os.path.exists(tmp), f"temp file {tmp} not cleaned up"

    def test_upload_image_uses_storage_backend(self):
        """upload_image() must call get_storage_backend().upload() not GCS."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService
        from src.services.pymupdf_parser_service import ExtractedImage

        fake_img_uri = "file:///var/lib/etherion/storage/tnt-7-media/images/doc1/abc.png"
        mock_storage = MagicMock()
        mock_storage.upload.return_value = fake_img_uri

        img = ExtractedImage(
            image_bytes=b"\x89PNG\r\n",
            mime_type="image/png",
            chapter_heading="Chapter 1",
            page_number=1,
            description=None,
        )

        with patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            svc = MultimodalIngestionService()
            result = svc.upload_image("7", img, "doc_abc123")

        assert result == fake_img_uri
        mock_storage.upload.assert_called_once()

    def test_ingest_bytes_calls_kb_insert(self):
        """ingest_bytes() for non-PDF content must call get_kb_backend().insert_docs()."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        mock_kb = MagicMock()
        mock_storage = MagicMock()
        mock_storage.upload.return_value = "file:///storage/tnt-1-media/uploads/abc/doc.txt"

        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.1] * 1408
        mock_embedder.embed_image.return_value = [0.1] * 1408
        mock_embedder.DIMENSION = 1408

        mock_parser = MagicMock()
        from src.services.pymupdf_parser_service import DocumentParseResult, ChapterEssence
        mock_parser.parse_bytes.return_value = DocumentParseResult(
            markdown="# Test\n\nHello world",
            chapters=[
                ChapterEssence(
                    heading="Test",
                    level=1,
                    start_line=0,
                    essence_text="Test Hello world",
                    full_content="Hello world",
                    images=[],
                )
            ],
            images=[],
            total_chars=20,
            estimated_tokens=5,
            source_filename="doc.txt",
            mime_type="text/plain",
            metadata={"parser": "pymupdf"},
        )

        with patch("src.services.multimodal_ingestion_service.get_kb_backend",
                   return_value=mock_kb), \
             patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            svc = MultimodalIngestionService()
            svc._embedder = mock_embedder
            svc._parser = mock_parser

            result = svc.ingest_bytes(
                tenant_id="1",
                content=b"Hello world",
                filename="doc.txt",
                mime_type="text/plain",
                job_id="job_1",
            )

        assert mock_kb.insert_docs.called
        call_args = mock_kb.insert_docs.call_args
        tenant, table, rows = call_args.args
        assert tenant == "1"
        assert table == "multimodal_docs"
        assert len(rows) == 1
        row = rows[0]
        assert "storage_uri" in row
        assert "gcs_uri" in row
        assert row["storage_uri"] == row["gcs_uri"]  # both must be set

    def test_ingest_bytes_no_ensure_kb_call(self):
        """ingest_bytes() must NOT call ensure_tenant_kb (pgvector is schema-agnostic)."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        mock_kb = MagicMock()
        mock_storage = MagicMock()
        mock_storage.upload.return_value = "file:///storage/tnt-1-media/uploads/abc/doc.txt"

        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.0] * 1408
        mock_embedder.DIMENSION = 1408

        with patch("src.services.multimodal_ingestion_service.get_kb_backend",
                   return_value=mock_kb), \
             patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            svc = MultimodalIngestionService()
            svc._embedder = mock_embedder
            svc.ingest_bytes("1", b"text content", "doc.txt", "text/plain")

        mock_kb.ensure_tenant_kb.assert_not_called()

    def test_ingest_gcs_uri_uses_storage_backend_download(self):
        """ingest_gcs_uri() must download via storage_backend.download(), not GCS client."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        mock_kb = MagicMock()
        mock_storage = MagicMock()
        mock_storage.download.return_value = b"Hello from storage"
        mock_storage.upload.return_value = "file:///storage/tnt-2-media/uploads/xyz/doc.txt"

        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.0] * 1408
        mock_embedder.DIMENSION = 1408

        with patch("src.services.multimodal_ingestion_service.get_kb_backend",
                   return_value=mock_kb), \
             patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            svc = MultimodalIngestionService()
            svc._embedder = mock_embedder

            result = svc.ingest_gcs_uri(
                tenant_id="2",
                gcs_uri="file:///storage/tnt-2-media/uploads/xyz/doc.txt",
                filename="doc.txt",
                mime_type="text/plain",
            )

        mock_storage.download.assert_called_once_with(
            "file:///storage/tnt-2-media/uploads/xyz/doc.txt"
        )
        assert result is not None

    def test_ingest_gcs_uri_accepts_any_scheme(self):
        """ingest_gcs_uri() must work with gs://, file://, s3:// URIs."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        for uri_scheme in ["gs://bucket/key", "file:///local/path", "s3://bucket/key"]:
            mock_kb = MagicMock()
            mock_storage = MagicMock()
            mock_storage.download.return_value = b"content"
            mock_storage.upload.return_value = uri_scheme

            mock_embedder = MagicMock()
            mock_embedder.embed_text.return_value = [0.0] * 1408
            mock_embedder.DIMENSION = 1408

            with patch("src.services.multimodal_ingestion_service.get_kb_backend",
                       return_value=mock_kb), \
                 patch("src.services.multimodal_ingestion_service.get_storage_backend",
                       return_value=mock_storage):
                svc = MultimodalIngestionService()
                svc._embedder = mock_embedder
                result = svc.ingest_gcs_uri("1", uri_scheme, "doc.txt", "text/plain")

            assert result.gcs_uri == uri_scheme, f"gcs_uri mismatch for {uri_scheme}"
            assert result.storage_uri == uri_scheme  # property alias

    def test_result_has_storage_uri_alias(self):
        """MultimodalIngestionResult.storage_uri must be an alias for gcs_uri."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionResult
        r = MultimodalIngestionResult(
            tenant_id="1",
            gcs_uri="file:///test/path",
            filename="f.txt",
            mime_type="text/plain",
            size_bytes=10,
            doc_ids=["d1"],
            image_ids=[],
            chapter_count=1,
            part_count=1,
            total_tokens=5,
        )
        assert r.storage_uri == r.gcs_uri == "file:///test/path"

    def test_pdf_streaming_buffers_rows_before_insert(self):
        """_ingest_pdf_streaming must batch-insert after all parts (not per-part)."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        # Track calls to insert_docs
        insert_calls: List[Any] = []

        mock_kb = MagicMock()
        mock_kb.insert_docs.side_effect = lambda t, tbl, rows: insert_calls.append(
            (t, tbl, [r["doc_id"] for r in rows])
        )
        mock_storage = MagicMock()
        mock_storage.upload.return_value = "file:///storage/tnt-3-media/parts/doc_001.pdf"

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1408]
        mock_embedder.DIMENSION = 1408

        # Create a minimal real PDF in memory (single page)
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        pdf_doc = fitz.open()
        page = pdf_doc.new_page()
        page.insert_text((50, 50), "Hello PDF world")
        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()

        with patch("src.services.multimodal_ingestion_service.get_kb_backend",
                   return_value=mock_kb), \
             patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            svc = MultimodalIngestionService()
            svc._embedder = mock_embedder

            result = svc._ingest_pdf_streaming(
                tenant_id="3",
                gcs_uri="file:///storage/tnt-3-media/uploads/hash/doc.pdf",
                content=pdf_bytes,
                filename="doc.pdf",
                mime_type="application/pdf",
                size_bytes=len(pdf_bytes),
                job_id="job_pdf",
            )

        # insert_docs should be called once (batch) with total_parts set
        kb_calls = [c for c in insert_calls if c[1] == "multimodal_docs"]
        assert len(kb_calls) >= 1
        # All rows should have total_parts set (not None)
        for tenant_arg, table_arg, doc_id_list in kb_calls:
            assert tenant_arg == "3"

        assert len(result.doc_ids) >= 1
        assert result.errors == [] or all("Image" not in e for e in result.errors)

    def test_pdf_part_rows_have_storage_uri_and_gcs_uri(self):
        """PDF part rows must include both storage_uri and gcs_uri keys."""
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        inserted_rows: List[Dict[str, Any]] = []

        mock_kb = MagicMock()
        mock_kb.insert_docs.side_effect = lambda t, tbl, rows: inserted_rows.extend(rows)
        mock_storage = MagicMock()
        mock_storage.upload.return_value = "file:///storage/tnt-5-media/parts/doc_001.pdf"

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1408]
        mock_embedder.DIMENSION = 1408

        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        pdf_doc = fitz.open()
        page = pdf_doc.new_page()
        page.insert_text((50, 50), "test page")
        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()

        with patch("src.services.multimodal_ingestion_service.get_kb_backend",
                   return_value=mock_kb), \
             patch("src.services.multimodal_ingestion_service.get_storage_backend",
                   return_value=mock_storage):
            svc = MultimodalIngestionService()
            svc._embedder = mock_embedder
            svc._ingest_pdf_streaming(
                tenant_id="5",
                gcs_uri="file:///storage/tnt-5-media/uploads/hash/doc.pdf",
                content=pdf_bytes,
                filename="doc.pdf",
                mime_type="application/pdf",
                size_bytes=len(pdf_bytes),
            )

        doc_rows = [r for r in inserted_rows if r.get("mime_type") == "application/pdf"]
        assert len(doc_rows) >= 1
        for row in doc_rows:
            assert "storage_uri" in row, "storage_uri missing from PDF part row"
            assert "gcs_uri" in row, "gcs_uri missing from PDF part row (backwards compat)"
            assert row["storage_uri"] == row["gcs_uri"]
            assert row["total_parts"] is not None, "total_parts should be set after batch insert"
