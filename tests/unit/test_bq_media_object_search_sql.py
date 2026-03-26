import os


def test_bq_media_object_search_builds_vector_search_with_query_embedding(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")

    from src.services import bq_media_object_search as mod
    from src.services.bq_media_object_search import BQMediaObjectSearchService

    monkeypatch.setattr(mod, "ensure_tenant_media_object_kb", lambda client, tenant_id: None)

    class _BQ:
        def __init__(self):
            self.client = object()
            self.sql = None
            self.params = None
            self.labels = None

        def query(self, sql, params=None, labels=None, job_id=None, location=None):
            self.sql = sql
            self.params = params
            self.labels = labels
            return []

    bq = _BQ()

    class _Embedder:
        def embed_texts(self, texts, task="RETRIEVAL_QUERY"):
            return [[0.1, 0.2, 0.3]]

    svc = BQMediaObjectSearchService(project_id=os.environ["GOOGLE_CLOUD_PROJECT"], bq=bq, embedder=_Embedder())
    svc.search(tenant_id="110", query="find my pdf", top_k=7)

    assert bq.sql is not None
    assert "VECTOR_SEARCH" in bq.sql
    assert "tnt_110.media_object_embeddings" in bq.sql
    assert "'vector_embedding'" in bq.sql
    assert "top_k => @top_k" in bq.sql
    assert "@query_vec" in bq.sql

    assert bq.params is not None
    assert bq.params["top_k"] == 7
    assert bq.params["query"] == "find my pdf"
    assert bq.params["query_vec"] == [0.1, 0.2, 0.3]


def test_bq_media_object_search_adds_content_type_prefix_filter(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")

    from src.services import bq_media_object_search as mod
    from src.services.bq_media_object_search import BQMediaObjectSearchService

    monkeypatch.setattr(mod, "ensure_tenant_media_object_kb", lambda client, tenant_id: None)

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

    class _Embedder:
        def embed_texts(self, texts, task="RETRIEVAL_QUERY"):
            return [[0.0, 0.0, 0.0]]

    svc = BQMediaObjectSearchService(project_id=os.environ["GOOGLE_CLOUD_PROJECT"], bq=bq, embedder=_Embedder())
    svc.search(tenant_id="110", query="find", top_k=5, content_type_prefix="application/")

    assert bq.sql is not None
    assert "STARTS_WITH(content_type, @content_type_prefix)" in bq.sql
    assert bq.params is not None
    assert bq.params["content_type_prefix"] == "application/"
