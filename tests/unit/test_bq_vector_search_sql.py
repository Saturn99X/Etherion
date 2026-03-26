import os


def test_bq_vector_search_quotes_embedding_column(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")

    from src.services import bq_vector_search as mod
    from src.services.bq_vector_search import BQVectorSearchService

    monkeypatch.setattr(mod, "ensure_tenant_kb", lambda client, tenant_id: None)

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

    class _Embedder:
        def embed_texts(self, texts, task="RETRIEVAL_DOCUMENT"):
            return [[0.0] * 768]

    bq = _BQ()
    svc = BQVectorSearchService(project_id=os.environ["GOOGLE_CLOUD_PROJECT"], bq=bq, embedder=_Embedder())
    svc.search(
        tenant_id="110",
        query="hello",
        top_k=7,
        project_id_filter="physics_entropy_eval",
        kb_type=None,
        job_id=None,
    )

    assert bq.sql is not None
    assert "VECTOR_SEARCH" in bq.sql
    assert "'vector_embedding'" in bq.sql
    assert "(SELECT @query_vec AS query_embedding)" in bq.sql
    assert "'query_embedding'" in bq.sql
    assert "SELECT base, distance" in bq.sql
    assert "JSON_VALUE(metadata, '$.project_id') = @project_id" in bq.sql
    assert bq.params is not None
    assert bq.params["top_k"] == 7
    assert bq.params["project_id"] == "physics_entropy_eval"
    assert isinstance(bq.params["query_vec"], list)
    assert len(bq.params["query_vec"]) == 768
