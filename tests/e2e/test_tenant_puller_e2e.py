import os
import sys
import types
import importlib.util
from pathlib import Path

import pytest


def load_cf_module():
    repo_root = Path(__file__).resolve().parents[2]
    cf_path = repo_root / "terraform/modules/data_ingestion/function_src/cloud_function.py"
    assert cf_path.exists(), f"Cloud Function source not found at {cf_path}"
    # Preload minimal google.cloud stubs to avoid ImportError at import time
    # Only shapes used by module are stubbed; real behavior is monkeypatched later
    if "google" not in sys.modules:
        sys.modules["google"] = types.ModuleType("google")
    google = sys.modules["google"]
    if not hasattr(google, "cloud"):
        google.cloud = types.ModuleType("google.cloud")  # type: ignore[attr-defined]
        sys.modules["google.cloud"] = google.cloud
    # storage
    if "google.cloud.storage" not in sys.modules:
        storage_mod = types.ModuleType("google.cloud.storage")
        storage_mod.Client = type("Client", (), {})
        sys.modules["google.cloud.storage"] = storage_mod
    # secretmanager
    if "google.cloud.secretmanager" not in sys.modules:
        sm_mod = types.ModuleType("google.cloud.secretmanager")
        sm_mod.SecretManagerServiceClient = type("SecretManagerServiceClient", (), {})
        sys.modules["google.cloud.secretmanager"] = sm_mod
    # pubsub_v1
    if "google.cloud.pubsub_v1" not in sys.modules:
        ps_mod = types.ModuleType("google.cloud.pubsub_v1")
        ps_mod.PublisherClient = type("PublisherClient", (), {})
        sys.modules["google.cloud.pubsub_v1"] = ps_mod
    # bigquery
    if "google.cloud.bigquery" not in sys.modules:
        bq_mod = types.ModuleType("google.cloud.bigquery")
        bq_mod.Client = type("Client", (), {})
        bq_mod.SchemaField = lambda *a, **k: ("SchemaField", a, k)
        bq_mod.Dataset = type("Dataset", (), {"__init__": lambda self, *a, **k: None})
        bq_mod.Table = type("Table", (), {"__init__": lambda self, *a, **k: None})
        sys.modules["google.cloud.bigquery"] = bq_mod

    # functions_framework decorators (no-op stubs)
    if "functions_framework" not in sys.modules:
        ff = types.ModuleType("functions_framework")
        ff.http = (lambda f: f)
        ff.cloud_event = (lambda f: f)
        sys.modules["functions_framework"] = ff

    # pandas stub (we don't exercise tabular path in this test)
    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.ModuleType("pandas")

    spec = importlib.util.spec_from_file_location("cf_module", str(cf_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


class FakePayload:
    def __init__(self, data: bytes):
        self.data = data


class FakeAccessSecretResp:
    def __init__(self, data: bytes):
        self.payload = types.SimpleNamespace(data=data)


class FakeBQClient:
    def __init__(self, project=None):
        self.project = project
        self.inserted = []

    # Dataset/table admin methods (no-ops for test)
    def get_dataset(self, ds):
        return object()

    def create_dataset(self, ds, exists_ok=True):
        return object()

    def get_table(self, tbl):
        return object()

    def create_table(self, tbl):
        return object()

    def insert_rows_json(self, table, rows):
        self.inserted.extend(rows)
        return []  # no errors


class FakeResp:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json


@pytest.mark.e2e
def test_tenant_puller_inserts_rows(monkeypatch):
    mod = load_cf_module()

    # Arrange environment
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    # Monkeypatch Secret Manager access to return a Slack token
    def fake_access_secret_version(request):
        return FakeAccessSecretResp(b'{"access_token": "xoxb-test-token"}')

    monkeypatch.setattr(mod, "secret_client", types.SimpleNamespace(access_secret_version=fake_access_secret_version))

    # Monkeypatch BigQuery client to capture inserts
    monkeypatch.setattr(mod.bigquery, "Client", FakeBQClient)

    # Monkeypatch requests module import used inside function
    def fake_get(url, params=None, headers=None, timeout=None):
        assert "slack.com/api/conversations.list" in url
        return FakeResp({
            "ok": True,
            "channels": [
                {"id": "C123", "name": "general", "num_members": 42, "created": 1600000000, "is_private": False}
            ]
        })

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    # Build fake HTTP request
    class FakeRequest:
        method = "POST"

        def get_json(self):
            return {"tenant_id": "t1", "provider": "slack", "limit": 1}

        @property
        def args(self):
            return {}

    # Act
    result = mod.pull_tenant_data(FakeRequest())

    # Normalize response
    if isinstance(result, tuple):
        body, status = result
        assert status == 200
        res = body
    else:
        res = result

    # Assert
    assert res.get("ok") is True
    assert res.get("provider") == "slack"
    assert res.get("tenant_id") == "t1"
    assert res.get("inserted") == 1
