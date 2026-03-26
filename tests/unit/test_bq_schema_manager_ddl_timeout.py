import os


def test_bq_schema_manager_external_table_ddl_uses_timeout(monkeypatch):
    import importlib

    mod = importlib.import_module("src.services.bq_schema_manager")
    importlib.reload(mod)

    monkeypatch.setenv("BIGQUERY_DDL_TIMEOUT_SECONDS", "7")

    class _Job:
        def __init__(self):
            self.timeouts = []

        def result(self, timeout=None):
            self.timeouts.append(timeout)
            return None

    class _Client:
        def __init__(self):
            self.project = "p"
            self.jobs = []

        def get_table(self, _ref):
            raise Exception("not found")

        def query(self, _ddl):
            j = _Job()
            self.jobs.append(j)
            return j

    class _Dataset:
        dataset_id = "tnt_123"

    monkeypatch.setattr(mod, "ensure_tenant_dataset", lambda client, tenant_id, location="US": _Dataset())
    monkeypatch.setattr(mod, "ensure_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_client_for_project", lambda client, project: client)

    c = _Client()
    mod.ensure_tenant_ai_assets_object_kb(c, "123")

    assert c.jobs, "expected at least one query job"
    assert c.jobs[0].timeouts == [7.0]
