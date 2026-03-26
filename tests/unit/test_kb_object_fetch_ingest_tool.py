import os
import asyncio
import builtins


def test_kb_object_fetch_ingest_fetches_and_ingests(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")

    from src.tools import kb_object_fetch_ingest_tool as mod

    class _Cfg:
        def get(self, key, default=None):
            if key == "kb_direct_gcs_fetch_enabled":
                return True
            if key == "kb_object_tables_enabled":
                return True
            return default

    monkeypatch.setattr(mod, "EnvironmentConfig", lambda: _Cfg())

    class _Obj:
        gcs_uri = "gs://tnt-110-media/uploads/x/file.pdf"
        filename = "file.pdf"
        content_type = "application/pdf"
        size_bytes = 10
        local_path = "/tmp/fake"

    monkeypatch.setattr(mod, "fetch_tenant_object_to_tempfile", lambda **kwargs: _Obj())

    def _open(path, mode="r", *args, **kwargs):
        assert path == "/tmp/fake"
        assert "b" in mode
        class _F:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                return b"PDFBYTES"
        return _F()

    monkeypatch.setattr(builtins, "open", _open)
    monkeypatch.setattr(mod.os, "unlink", lambda p: None)

    class _Ingest:
        def ingest_existing_gcs_uri(self, **kwargs):
            assert kwargs["tenant_id"] == "110"
            assert kwargs["gcs_uri"] == "gs://tnt-110-media/uploads/x/file.pdf"
            assert kwargs["filename"] == "file.pdf"
            assert kwargs["mime_type"] == "application/pdf"
            assert kwargs["size_bytes"] == 10
            assert kwargs["content"] == b"PDFBYTES"
            class _R:
                tenant_id = "110"
                gcs_uri = kwargs["gcs_uri"]
                filename = kwargs["filename"]
                mime_type = kwargs["mime_type"]
                size_bytes = kwargs["size_bytes"]
                chunks_inserted = 1
            return _R()

    monkeypatch.setattr(mod, "IngestionService", lambda project_id=None: _Ingest())

    called = {"backfill": False}

    class _Backfill:
        def backfill(self, **kwargs):
            called["backfill"] = True

    monkeypatch.setattr(mod, "BQMediaObjectEmbeddingsBackfillService", lambda project_id=None: _Backfill())

    out = asyncio.run(
        mod.kb_object_fetch_ingest.ainvoke(
            {
                "tenant_id": "110",
                "gcs_uri": "gs://tnt-110-media/uploads/x/file.pdf",
                "project_id": "p1",
            }
        )
    )

    assert out["provider"] == "object_kb_fetch_ingest"
    assert out["gcs_uri"] == "gs://tnt-110-media/uploads/x/file.pdf"
    assert out["chunks_inserted"] == 1
    assert called["backfill"] is True
