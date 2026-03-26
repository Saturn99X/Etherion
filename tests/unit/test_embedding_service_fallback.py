import os


def test_embedding_service_falls_back_to_005_when_004_fails(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")
    monkeypatch.setenv("VERTEX_EMBEDDING_MODEL", "text-embedding-004")
    monkeypatch.setenv("VERTEX_EMBEDDING_MODEL_FALLBACK", "text-embedding-005")

    from google.cloud import aiplatform as aiplatform_mod
    from src.services.embedding_service import EmbeddingService
    from vertexai.preview import language_models

    monkeypatch.setattr(aiplatform_mod, "init", lambda **kwargs: None)

    calls = []

    class _Emb:
        def __init__(self, values):
            self.values = values

    class _Model:
        def get_embeddings(self, batch):
            return [_Emb([0.1] * 768) for _ in batch]

    def fake_from_pretrained(name: str):
        calls.append(name)
        if name == "text-embedding-004":
            raise Exception("model not found")
        return _Model()

    monkeypatch.setattr(language_models.TextEmbeddingModel, "from_pretrained", staticmethod(fake_from_pretrained))

    svc = EmbeddingService(project_id=os.environ["GOOGLE_CLOUD_PROJECT"], location="us-central1")
    out = svc.embed_texts(["hello", "world"])

    assert calls == ["text-embedding-004", "text-embedding-005"]
    assert len(out) == 2
    assert len(out[0]) == 768


def test_embedding_service_uses_us_central1_when_vertex_ai_location_is_global(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")
    monkeypatch.delenv("VERTEX_EMBEDDING_LOCATION", raising=False)
    monkeypatch.setenv("VERTEX_AI_LOCATION", "global")

    from src.services.embedding_service import EmbeddingService

    svc = EmbeddingService(project_id=os.environ["GOOGLE_CLOUD_PROJECT"])
    assert svc.location == "us-central1"
