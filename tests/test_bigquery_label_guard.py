import pytest

from src.services.bigquery_service import BigQueryService


class DummyClient:
    def query(self, sql, job_config=None):
        class DummyJob:
            def result(self_inner):
                return []
        # Simulate behavior
        assert job_config is not None
        assert getattr(job_config, 'labels', None) is not None
        assert 'tenant_id' in job_config.labels and str(job_config.labels['tenant_id']).strip() != ''
        return DummyJob()


def test_query_requires_tenant_label(monkeypatch):
    svc = BigQueryService(project_id="dummy", client=DummyClient())

    # Missing labels should raise
    with pytest.raises(ValueError):
        svc.query("SELECT 1")

    # Missing tenant_id should raise
    with pytest.raises(ValueError):
        svc.query("SELECT 1", labels={"component": "x"})

    # Empty tenant_id should raise
    with pytest.raises(ValueError):
        svc.query("SELECT 1", labels={"tenant_id": "  "})

    # Proper labels should pass and return empty list
    res = svc.query("SELECT 1", labels={"tenant_id": "123", "component": "test"})
    assert list(res) == []


def test_query_respects_maximum_bytes_billed_env_and_override(monkeypatch):
    monkeypatch.setenv("BIGQUERY_MAX_BYTES_BILLED", "1000")

    class DummyClientWithMax:
        def __init__(self):
            self.last_job_config = None

        def query(self, sql, job_config=None):
            self.last_job_config = job_config

            class DummyJob:
                def result(self_inner):
                    return []

            return DummyJob()

    client = DummyClientWithMax()
    svc = BigQueryService(project_id="dummy", client=client)

    svc.query("SELECT 1", labels={"tenant_id": "123", "component": "test"})
    assert client.last_job_config is not None
    assert getattr(client.last_job_config, "maximum_bytes_billed", None) == 1000

    svc.query(
        "SELECT 1",
        labels={"tenant_id": "123", "component": "test"},
        maximum_bytes_billed=42,
    )
    assert client.last_job_config is not None
    assert getattr(client.last_job_config, "maximum_bytes_billed", None) == 42


