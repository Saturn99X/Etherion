def test_admin_ingest_status_payload_merge_sets_updated_at(monkeypatch):
    import importlib

    mod = importlib.import_module("src.core.tasks")
    importlib.reload(mod)

    base = {
        "job_id": "x",
        "status": "RUNNING",
        "tenant_id": "t",
        "gcs_uri": "gs://b/o",
        "filename": "f",
        "mime_type": "text/plain",
        "size_bytes": 1,
        "project_id": None,
        "error": None,
        "stage": "START",
        "started_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "elapsed_s": 0.0,
    }

    def _now_iso():
        return "2025-01-01T00:00:01Z"

    def _merge_status(base_payload, updates):
        out = dict(base_payload)
        out.update(updates)
        out["updated_at"] = _now_iso()
        return out

    merged = _merge_status(base, {"stage": "GCS_DOWNLOAD", "elapsed_s": 1.23})
    assert merged["stage"] == "GCS_DOWNLOAD"
    assert merged["elapsed_s"] == 1.23
    assert merged["updated_at"] == "2025-01-01T00:00:01Z"
