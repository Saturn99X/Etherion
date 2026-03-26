import os


def test_ensure_tenant_kb_disables_object_model_and_index_during_bootstrap(monkeypatch):
    import src.services.bq_schema_manager as m

    seen: list[str | None] = []

    def fake_ensure_tenant_dataset(client, tenant_id: str, location: str = "US"):
        class _DS:
            dataset_id = f"tnt_{tenant_id}"

        return _DS()

    def fake_ensure_table(client, dataset_id: str, table_id: str, schema):
        return None

    def fake_media_object_kb(client, tenant_id: str):
        seen.append(os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX"))

    def fake_ai_assets_object_kb(client, tenant_id: str):
        seen.append(os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX"))

    monkeypatch.setattr(m, "ensure_tenant_dataset", fake_ensure_tenant_dataset)
    monkeypatch.setattr(m, "ensure_table", fake_ensure_table)
    monkeypatch.setattr(m, "ensure_tenant_media_object_kb", fake_media_object_kb)
    monkeypatch.setattr(m, "ensure_tenant_ai_assets_object_kb", fake_ai_assets_object_kb)

    monkeypatch.setenv("KB_OBJECT_TABLES_ENABLED", "true")
    monkeypatch.setenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX", "true")

    m.ensure_tenant_kb(client=object(), tenant_id="123")

    assert seen == ["false", "false"]
    assert os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX") == "true"


def test_ensure_tenant_kb_restores_env_when_unset(monkeypatch):
    import src.services.bq_schema_manager as m

    seen: list[str | None] = []

    def fake_ensure_tenant_dataset(client, tenant_id: str, location: str = "US"):
        class _DS:
            dataset_id = f"tnt_{tenant_id}"

        return _DS()

    def fake_ensure_table(client, dataset_id: str, table_id: str, schema):
        return None

    def fake_media_object_kb(client, tenant_id: str):
        seen.append(os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX"))

    def fake_ai_assets_object_kb(client, tenant_id: str):
        seen.append(os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX"))

    monkeypatch.setattr(m, "ensure_tenant_dataset", fake_ensure_tenant_dataset)
    monkeypatch.setattr(m, "ensure_table", fake_ensure_table)
    monkeypatch.setattr(m, "ensure_tenant_media_object_kb", fake_media_object_kb)
    monkeypatch.setattr(m, "ensure_tenant_ai_assets_object_kb", fake_ai_assets_object_kb)

    monkeypatch.setenv("KB_OBJECT_TABLES_ENABLED", "true")
    monkeypatch.delenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX", raising=False)

    m.ensure_tenant_kb(client=object(), tenant_id="123")

    assert seen == ["false", "false"]
    assert os.getenv("KB_OBJECT_TABLES_CREATE_MODEL_AND_INDEX") is None
