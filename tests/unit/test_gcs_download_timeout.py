def test_admin_ingest_gcs_download_passes_timeout(monkeypatch):
    import src.core.tasks as tasks

    seen = {}

    class _FakeBlob:
        def download_as_bytes(self, timeout=None):
            seen["timeout"] = timeout
            return b"ok"

    out = tasks._download_blob_bytes(_FakeBlob(), timeout_s=12.5)
    assert out == b"ok"
    assert seen.get("timeout") == 12.5
