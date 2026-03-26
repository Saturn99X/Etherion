"""Aggressive tests for Tier 3 tool migrations.

Covers: multimodal_kb_tool.py (provider tag, URI scheme freedom),
kb_object_fetch_ingest_tool.py (storage backend, not fetch_tenant_object_to_tempfile).
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _FakeSearchResult:
    def __init__(self, idx=0):
        self.result_type = "doc"
        self.id = f"doc_{idx}"
        self.gcs_uri = f"gs://bucket/doc_{idx}.pdf"
        self.distance = 0.1 * idx
        self.filename = f"doc_{idx}.pdf"
        self.part_number = 1
        self.total_parts = 1
        self.chapter_heading = None
        self.essence_text = "Some text"


class _FakeMultimodalSearchService:
    def __init__(self):
        self.search_all_calls = []
        self.search_docs_calls = []
        self.search_images_calls = []
        self.search_by_image_calls = []

    def search_all(self, tenant_id, query, top_k=10, project_id_filter=None, include_images=True):
        self.search_all_calls.append({"tenant_id": tenant_id, "query": query})
        return [_FakeSearchResult(i) for i in range(top_k)]

    def search_docs(self, tenant_id, query, top_k=10, project_id_filter=None):
        self.search_docs_calls.append({"tenant_id": tenant_id, "query": query})
        return [_FakeSearchResult(i) for i in range(top_k)]

    def search_images(self, tenant_id, query, top_k=10):
        self.search_images_calls.append({"tenant_id": tenant_id, "query": query})
        return [_FakeSearchResult(i) for i in range(top_k)]

    def search_by_image(self, tenant_id, image_bytes, top_k=10, search_docs=True, search_images=True):
        self.search_by_image_calls.append({"tenant_id": tenant_id})
        return [_FakeSearchResult(i) for i in range(top_k)]


class _FakeIngestResult:
    tenant_id = "42"
    gcs_uri = "file:///var/lib/etherion/storage/tnt-42-media/obj.pdf"
    filename = "obj.pdf"
    mime_type = "application/pdf"
    size_bytes = 1024
    doc_ids = ["d1", "d2"]
    chapter_count = 2


class _FakeIngestionService:
    def __init__(self, **kwargs):
        self.calls = []

    def ingest_gcs_uri(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeIngestResult()


class _FakeBackfillService:
    def __init__(self, **kwargs):
        self.backfill_calls = []

    def backfill(self, **kwargs):
        self.backfill_calls.append(kwargs)


class _FakeStorageBackend:
    def __init__(self, content=b"pdf-bytes", size=1024):
        self._content = content
        self._size = size
        self.download_to_file_calls = []

    def download_to_file(self, uri, dest_path):
        self.download_to_file_calls.append((uri, dest_path))
        with open(dest_path, "wb") as f:
            f.write(self._content)

    def download(self, uri): return self._content

    def upload(self, *a, **kw): return "file:///fake/uri"
    def exists(self, uri): return True
    def delete(self, uri): pass
    def generate_access_url(self, uri, expiration_minutes=5): return "/api/files/fake"


# ---------------------------------------------------------------------------
# multimodal_kb_tool tests
# ---------------------------------------------------------------------------

class TestMultimodalKBTool:
    def test_provider_is_multimodal_kb_not_bigquery(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)

        result = asyncio.run(
            mod.multimodal_kb_search.ainvoke({
                "tenant_id": "1",
                "query": "revenue chart",
                "top_k": 3,
            })
        )
        assert result["provider"] == "multimodal_kb"
        assert result["provider"] != "multimodal_bigquery"

    def test_image_search_provider_is_multimodal_kb(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)
        image_b64 = base64.b64encode(b"FAKE_PNG_BYTES").decode()

        result = asyncio.run(
            mod.image_search_by_image.ainvoke({
                "tenant_id": "1",
                "image_base64": image_b64,
                "top_k": 3,
            })
        )
        assert result["provider"] == "multimodal_kb"

    def test_multimodal_search_calls_search_all(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)

        asyncio.run(
            mod.multimodal_kb_search.ainvoke({
                "tenant_id": "5",
                "query": "test query",
                "search_type": "all",
            })
        )
        assert len(fake_svc.search_all_calls) == 1
        assert fake_svc.search_all_calls[0]["query"] == "test query"

    def test_search_type_docs_calls_search_docs(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)

        asyncio.run(
            mod.multimodal_kb_search.ainvoke({
                "tenant_id": "5",
                "query": "test",
                "search_type": "docs",
            })
        )
        assert len(fake_svc.search_docs_calls) == 1
        assert len(fake_svc.search_all_calls) == 0

    def test_search_type_images_calls_search_images(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)

        asyncio.run(
            mod.multimodal_kb_search.ainvoke({
                "tenant_id": "5",
                "query": "diagram",
                "search_type": "images",
            })
        )
        assert len(fake_svc.search_images_calls) == 1

    def test_empty_tenant_id_raises(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)

        with pytest.raises((ValueError, Exception)):
            asyncio.run(
                mod.multimodal_kb_search.ainvoke({
                    "tenant_id": "",
                    "query": "query",
                })
            )

    def test_empty_query_raises(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)

        with pytest.raises((ValueError, Exception)):
            asyncio.run(
                mod.multimodal_kb_search.ainvoke({
                    "tenant_id": "1",
                    "query": "",
                })
            )

    def test_fetch_document_content_accepts_file_uri(self, monkeypatch):
        """Must NOT reject file:// URIs (GCS-only check was removed)."""
        import src.tools.multimodal_kb_tool as mod
        monkeypatch.setattr(mod, "fetch_and_parse_gcs_content",
                            lambda uri, filename: "parsed content")

        result = asyncio.run(
            mod.fetch_document_content.ainvoke({
                "gcs_uri": "file:///var/lib/etherion/storage/tnt-1-media/doc.pdf",
                "filename": "doc.pdf",
                "parse_content": True,
            })
        )
        assert result["content"] == "parsed content"
        assert result["content_type"] == "markdown"

    def test_fetch_document_content_accepts_s3_uri(self, monkeypatch):
        """Must NOT reject s3:// URIs."""
        import src.tools.multimodal_kb_tool as mod
        monkeypatch.setattr(mod, "fetch_and_parse_gcs_content",
                            lambda uri, filename: "s3 content")

        result = asyncio.run(
            mod.fetch_document_content.ainvoke({
                "gcs_uri": "s3://tnt-1-media/doc.pdf",
                "filename": "doc.pdf",
                "parse_content": True,
            })
        )
        assert result["content"] == "s3 content"

    def test_fetch_document_content_accepts_gs_uri(self, monkeypatch):
        """gs:// URIs should still work."""
        import src.tools.multimodal_kb_tool as mod
        monkeypatch.setattr(mod, "fetch_and_parse_gcs_content",
                            lambda uri, filename: "gcs content")

        result = asyncio.run(
            mod.fetch_document_content.ainvoke({
                "gcs_uri": "gs://bucket/doc.pdf",
                "filename": "doc.pdf",
                "parse_content": True,
            })
        )
        assert result["content"] == "gcs content"

    def test_fetch_document_content_parse_false_returns_base64(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        raw_bytes = b"raw PDF bytes"
        monkeypatch.setattr(mod, "fetch_gcs_content",
                            lambda uri, project_id=None: raw_bytes)

        result = asyncio.run(
            mod.fetch_document_content.ainvoke({
                "gcs_uri": "gs://bucket/doc.pdf",
                "filename": "doc.pdf",
                "parse_content": False,
            })
        )
        assert result["content_type"] == "raw_bytes_base64"
        decoded = base64.b64decode(result["content"])
        assert decoded == raw_bytes
        assert result["size_bytes"] == len(raw_bytes)

    def test_fetch_document_raises_on_empty_uri(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        with pytest.raises((ValueError, Exception)):
            asyncio.run(
                mod.fetch_document_content.ainvoke({
                    "gcs_uri": "",
                    "filename": "doc.pdf",
                })
            )

    def test_results_contain_expected_fields(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)

        result = asyncio.run(
            mod.multimodal_kb_search.ainvoke({
                "tenant_id": "1",
                "query": "test",
                "top_k": 2,
            })
        )
        assert "results" in result
        assert "total_results" in result
        assert result["total_results"] == 2
        for r in result["results"]:
            assert "type" in r
            assert "id" in r
            assert "gcs_uri" in r
            assert "distance" in r

    def test_image_search_passes_bytes_to_service(self, monkeypatch):
        import src.tools.multimodal_kb_tool as mod
        fake_svc = _FakeMultimodalSearchService()
        monkeypatch.setattr(mod, "MultimodalSearchService", lambda: fake_svc)
        raw = b"FAKE IMAGE BYTES"
        b64 = base64.b64encode(raw).decode()

        asyncio.run(
            mod.image_search_by_image.ainvoke({
                "tenant_id": "7",
                "image_base64": b64,
                "top_k": 5,
            })
        )
        assert len(fake_svc.search_by_image_calls) == 1

    def test_schema_hints_returned_correctly(self):
        import src.tools.multimodal_kb_tool as mod
        hints = mod.multimodal_kb_search_get_schema_hints()
        assert "input_schema" in hints
        assert "usage" in hints
        assert "examples" in hints

    def test_fetch_document_schema_hints(self):
        import src.tools.multimodal_kb_tool as mod
        hints = mod.fetch_document_content_get_schema_hints()
        assert "input_schema" in hints

    def test_get_tool_by_name_returns_correct(self):
        import src.tools.multimodal_kb_tool as mod
        t = mod.get_tool_by_name("multimodal_kb_search")
        assert t is not None
        assert t["name"] == "multimodal_kb_search"

    def test_get_tool_by_name_returns_none_for_missing(self):
        import src.tools.multimodal_kb_tool as mod
        t = mod.get_tool_by_name("nonexistent_tool_xyz")
        assert t is None

    def test_all_tools_in_registry(self):
        import src.tools.multimodal_kb_tool as mod
        tools = mod.get_multimodal_kb_tools()
        names = {t["name"] for t in tools}
        assert "multimodal_kb_search" in names
        assert "fetch_document_content" in names
        assert "image_search_by_image" in names


# ---------------------------------------------------------------------------
# kb_object_fetch_ingest_tool tests
# ---------------------------------------------------------------------------

class TestKBObjectFetchIngestToolMigration:
    def test_no_fetch_tenant_object_to_tempfile_import(self):
        """Tool must NOT import the GCS-specific fetch helper."""
        import src.tools.kb_object_fetch_ingest_tool as mod
        src_text = Path(mod.__file__).read_text()
        assert "fetch_tenant_object_to_tempfile" not in src_text

    def test_uses_get_storage_backend(self):
        """Tool must import and use get_storage_backend."""
        import src.tools.kb_object_fetch_ingest_tool as mod
        src_text = Path(mod.__file__).read_text()
        assert "get_storage_backend" in src_text

    def test_raises_on_empty_tenant_id(self, monkeypatch):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None): return True if "enabled" in k else d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())

        with pytest.raises((ValueError, Exception)):
            asyncio.run(
                mod.kb_object_fetch_ingest.ainvoke({"tenant_id": "", "gcs_uri": "gs://b/f.pdf"})
            )

    def test_raises_on_empty_gcs_uri(self, monkeypatch):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None): return True if "enabled" in k else d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())

        with pytest.raises((ValueError, Exception)):
            asyncio.run(
                mod.kb_object_fetch_ingest.ainvoke({"tenant_id": "1", "gcs_uri": ""})
            )

    def test_raises_when_feature_disabled(self, monkeypatch):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return False
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())

        with pytest.raises(RuntimeError, match="kb_direct_gcs_fetch_enabled"):
            asyncio.run(
                mod.kb_object_fetch_ingest.ainvoke({
                    "tenant_id": "1",
                    "gcs_uri": "gs://bucket/file.pdf"
                })
            )

    def test_calls_storage_backend_download_to_file(self, monkeypatch, tmp_path):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                if k == "kb_object_tables_enabled": return False
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())

        fake_storage = _FakeStorageBackend(content=b"PDF bytes", size=8)
        monkeypatch.setattr(mod, "get_storage_backend", lambda: fake_storage)

        fake_ingest = _FakeIngestionService()
        monkeypatch.setattr(mod, "MultimodalIngestionService", lambda project_id=None: fake_ingest)

        asyncio.run(
            mod.kb_object_fetch_ingest.ainvoke({
                "tenant_id": "42",
                "gcs_uri": "file:///var/data/doc.pdf",
            })
        )

        assert len(fake_storage.download_to_file_calls) == 1
        uri, _ = fake_storage.download_to_file_calls[0]
        assert uri == "file:///var/data/doc.pdf"

    def test_calls_ingest_gcs_uri(self, monkeypatch):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                if k == "kb_object_tables_enabled": return False
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())

        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr(mod, "get_storage_backend", lambda: fake_storage)

        fake_ingest = _FakeIngestionService()
        monkeypatch.setattr(mod, "MultimodalIngestionService", lambda project_id=None: fake_ingest)

        asyncio.run(
            mod.kb_object_fetch_ingest.ainvoke({
                "tenant_id": "42",
                "gcs_uri": "s3://tnt-42-media/obj.pdf",
            })
        )

        assert len(fake_ingest.calls) == 1
        call = fake_ingest.calls[0]
        assert call["tenant_id"] == "42"
        assert call["gcs_uri"] == "s3://tnt-42-media/obj.pdf"

    def test_returns_storage_uri_in_output(self, monkeypatch):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                if k == "kb_object_tables_enabled": return False
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr(mod, "get_storage_backend", lambda: fake_storage)
        fake_ingest = _FakeIngestionService()
        monkeypatch.setattr(mod, "MultimodalIngestionService", lambda project_id=None: fake_ingest)

        result = asyncio.run(
            mod.kb_object_fetch_ingest.ainvoke({
                "tenant_id": "42",
                "gcs_uri": "file:///data/obj.pdf",
            })
        )
        assert "storage_uri" in result
        assert result["provider"] == "object_kb_fetch_ingest"

    def test_calls_backfill_when_object_tables_enabled(self, monkeypatch):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                if k == "kb_object_tables_enabled": return True
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr(mod, "get_storage_backend", lambda: fake_storage)
        fake_ingest = _FakeIngestionService()
        monkeypatch.setattr(mod, "MultimodalIngestionService", lambda project_id=None: fake_ingest)
        fake_backfill = _FakeBackfillService()
        monkeypatch.setattr(mod, "BQMediaObjectEmbeddingsBackfillService",
                            lambda project_id=None: fake_backfill)

        asyncio.run(
            mod.kb_object_fetch_ingest.ainvoke({
                "tenant_id": "42",
                "gcs_uri": "file:///data/obj.pdf",
            })
        )
        assert len(fake_backfill.backfill_calls) == 1

    def test_backfill_failure_does_not_propagate(self, monkeypatch):
        """Backfill errors must be caught and not crash the tool."""
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                if k == "kb_object_tables_enabled": return True
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr(mod, "get_storage_backend", lambda: fake_storage)
        fake_ingest = _FakeIngestionService()
        monkeypatch.setattr(mod, "MultimodalIngestionService", lambda project_id=None: fake_ingest)

        class _ExplodingBackfill:
            def backfill(self, **kwargs): raise RuntimeError("Vault is down!")

        monkeypatch.setattr(mod, "BQMediaObjectEmbeddingsBackfillService",
                            lambda project_id=None: _ExplodingBackfill())

        # Should complete successfully even though backfill explodes
        result = asyncio.run(
            mod.kb_object_fetch_ingest.ainvoke({
                "tenant_id": "42",
                "gcs_uri": "file:///data/obj.pdf",
            })
        )
        assert result["provider"] == "object_kb_fetch_ingest"

    def test_max_size_bytes_zero_raises(self, monkeypatch):
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())

        with pytest.raises((ValueError, Exception)):
            asyncio.run(
                mod.kb_object_fetch_ingest.ainvoke({
                    "tenant_id": "1",
                    "gcs_uri": "gs://bucket/f.pdf",
                    "max_size_bytes": 0,
                })
            )

    def test_accepts_file_uri(self, monkeypatch):
        """Tool should accept file:// URIs, not just gs://."""
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                if k == "kb_object_tables_enabled": return False
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr(mod, "get_storage_backend", lambda: fake_storage)
        fake_ingest = _FakeIngestionService()
        monkeypatch.setattr(mod, "MultimodalIngestionService", lambda project_id=None: fake_ingest)

        result = asyncio.run(
            mod.kb_object_fetch_ingest.ainvoke({
                "tenant_id": "1",
                "gcs_uri": "file:///local/path/doc.pdf",
            })
        )
        assert result is not None

    def test_accepts_s3_uri(self, monkeypatch):
        """Tool should accept s3:// URIs."""
        import src.tools.kb_object_fetch_ingest_tool as mod

        class _Cfg:
            def get(self, k, d=None):
                if k == "kb_direct_gcs_fetch_enabled": return True
                if k == "kb_object_tables_enabled": return False
                return d

        monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())
        fake_storage = _FakeStorageBackend()
        monkeypatch.setattr(mod, "get_storage_backend", lambda: fake_storage)
        fake_ingest = _FakeIngestionService()
        monkeypatch.setattr(mod, "MultimodalIngestionService", lambda project_id=None: fake_ingest)

        result = asyncio.run(
            mod.kb_object_fetch_ingest.ainvoke({
                "tenant_id": "5",
                "gcs_uri": "s3://tnt-5-media/uploads/obj.docx",
            })
        )
        assert result is not None
