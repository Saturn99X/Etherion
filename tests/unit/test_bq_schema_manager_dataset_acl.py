def test_ensure_tenant_dataset_get_or_create(monkeypatch):
    import src.services.bq_schema_manager as m

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")

    class _Dataset:
        def __init__(self):
            self.dataset_id = "tnt_1"

    class _Client:
        def __init__(self):
            self.project = "p"
            self.created = False

        def get_dataset(self, ds_ref):
            raise RuntimeError("not found")

        def create_dataset(self, dataset):
            self.created = True
            return _Dataset()

    c = _Client()
    ds = m.ensure_tenant_dataset(client=c, tenant_id="1")
    assert getattr(ds, "dataset_id", None) == "tnt_1"
    assert c.created is True
