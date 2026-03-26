import os


def test_bq_media_object_embeddings_backfill_external_requires_gcs_uri(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")

    from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService

    class _BQ:
        def __init__(self):
            self.client = object()

        def query(self, sql, params=None, labels=None, job_id=None, location=None):
            return []

    svc = BQMediaObjectEmbeddingsBackfillService(project_id=os.environ["GOOGLE_CLOUD_PROJECT"], bq=_BQ())
    try:
        svc.backfill(tenant_id="110")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "gcs_uri is required" in str(e)


def test_bq_media_object_embeddings_backfill_external_merges_single_row(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")

    from src.services import bq_media_object_embeddings_backfill as mod
    from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService

    monkeypatch.setattr(mod, "ensure_tenant_media_object_kb", lambda client, tenant_id: None)

    class _Obj:
        bucket_name = "tnt-110-media"
        object_name = "uploads/x/file.pdf"
        filename = "file.pdf"
        content_type = "application/pdf"
        size_bytes = 123
        local_path = "/tmp/fake"

    monkeypatch.setattr(mod, "fetch_tenant_object_to_tempfile", lambda **kwargs: _Obj())

    class _Embedder:
        dimension = 3

        def __init__(self, project_id=None):
            pass

        def embed_texts(self, texts, task="RETRIEVAL_DOCUMENT"):
            return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(mod, "EmbeddingService", _Embedder)

    class _BQ:
        def __init__(self):
            self.client = object()
            self.sql = None
            self.params = None

        def query(self, sql, params=None, labels=None, job_id=None, location=None):
            self.sql = sql
            self.params = params
            return []

    bq = _BQ()
    svc = BQMediaObjectEmbeddingsBackfillService(project_id=os.environ["GOOGLE_CLOUD_PROJECT"], bq=bq)
    svc.backfill(tenant_id="110", gcs_uri="gs://tnt-110-media/uploads/x/file.pdf")

    assert bq.sql is not None
    assert "MERGE" in bq.sql
    assert "PARSE_JSON" in bq.sql
    assert "@vector_embedding" in bq.sql
    assert bq.params is not None
    assert bq.params["tenant_id"] == "110"
    assert bq.params["gcs_uri"] == "gs://tnt-110-media/uploads/x/file.pdf"
    assert bq.params["vector_embedding"] == [0.1, 0.2, 0.3]
