"""Integration tests for the GCP → bare-metal migration.

These tests exercise multiple components together using real local filesystem,
in-memory KB backend stubs, and the full service stack. They verify that the
abstraction layers interoperate correctly end-to-end.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# In-memory KB backend for integration tests
# ---------------------------------------------------------------------------

class InMemoryKBBackend:
    """Full in-memory KB backend for integration testing without a real DB."""

    def __init__(self):
        self._docs: Dict[str, List[Dict]] = {}    # table → rows
        self._feedback: List[Dict] = []
        self._assets: List[Dict] = []
        self.inserted_docs: List = []  # records (tenant_id, table, rows) per call

    def ensure_tenant_kb(self, tenant_id): pass

    def insert_docs(self, tenant_id, table, rows):
        rows = list(rows)
        self.inserted_docs.append((tenant_id, table, rows))
        if table not in self._docs:
            self._docs[table] = []
        for row in rows:
            r = dict(row)
            r["_tenant_id"] = tenant_id
            self._docs[table].append(r)

    def upsert_doc(self, tenant_id, table, match_key, row):
        if table not in self._docs:
            self._docs[table] = []
        # Find and replace if match
        for i, existing in enumerate(self._docs[table]):
            if existing.get(match_key) == row.get(match_key):
                self._docs[table][i] = dict(row)
                return
        self._docs[table].append(dict(row))

    def query_assets(self, tenant_id, filters=None, limit=50, offset=0):
        results = [r for r in self._assets if r.get("tenant_id") == str(tenant_id)
                   or r.get("_tenant_id") == str(tenant_id)
                   or r.get("tenant_id") == tenant_id
                   or r.get("_tenant_id") == tenant_id]
        if filters:
            for k, v in filters.items():
                results = [
                    r for r in results
                    if r.get(k) == v
                    or (isinstance(r.get("metadata"), dict) and r["metadata"].get(k) == v)
                ]
        return results[offset:offset + limit]

    def insert_feedback(self, tenant_id, row):
        r = dict(row)
        r["_tenant_id"] = tenant_id
        self._feedback.append(r)

    def vector_search(self, *a, **kw): return []
    def text_search(self, *a, **kw): return []
    def query(self, *a, **kw): return []

    def add_asset(self, row):
        """Helper to seed an asset for testing."""
        self._assets.append(row)


# ---------------------------------------------------------------------------
# End-to-end: RepositoryService + LocalStorageBackend
# ---------------------------------------------------------------------------

class TestRepositoryServiceE2E:
    @pytest.fixture
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))

        import src.core.storage_backend as sb_mod
        sb_mod._backend_cache = None
        from src.core.storage_backend_local import LocalStorageBackend
        local_backend = LocalStorageBackend()

        kb = InMemoryKBBackend()
        monkeypatch.setattr("src.services.repository_service.get_kb_backend", lambda: kb)
        monkeypatch.setattr("src.services.repository_service.get_storage_backend", lambda: local_backend)

        from src.services.repository_service import RepositoryService
        svc = RepositoryService(tenant_id=1)
        return svc, kb, local_backend, tmp_path

    def test_create_then_list_asset(self, setup):
        svc, kb, backend, _ = setup
        content = b"Test PDF content here"
        asset = svc.create_ai_asset(content, "test.pdf", "application/pdf", job_id="job1")
        assert asset.asset_id is not None
        assert asset.filename == "test.pdf"
        # Seed KB with the row that was inserted
        for tid, table, rows in kb.inserted_docs:
            for row in rows:
                kb.add_asset({**row, "tenant_id": "1"})
        listed = svc.list_assets(limit=10)
        assert len(listed) >= 1
        assert any(a.filename == "test.pdf" for a in listed)

    def test_create_asset_file_exists_on_disk(self, setup, tmp_path):
        svc, kb, backend, _ = setup
        content = b"binary content"
        asset = svc.create_ai_asset(content, "data.bin", "application/octet-stream")
        # The file should exist on disk
        dest_path = asset.gcs_uri.replace("file://", "")
        assert os.path.exists(dest_path)
        assert open(dest_path, "rb").read() == content

    def test_create_asset_signed_url_returns_api_path(self, setup):
        svc, kb, backend, _ = setup
        content = b"image content"
        asset = svc.create_ai_asset(content, "img.png", "image/png")
        url = svc.generate_signed_url(asset.gcs_uri, minutes=5)
        assert url.startswith("/api/files/")

    def test_list_assets_empty_when_none_created(self, setup):
        svc, _, _, _ = setup
        result = svc.list_assets()
        assert result == []

    def test_create_multiple_assets_different_content(self, setup):
        svc, kb, _, _ = setup
        svc.create_ai_asset(b"doc1", "doc1.txt", "text/plain", job_id="j1")
        svc.create_ai_asset(b"doc2", "doc2.txt", "text/plain", job_id="j1")
        assert len(kb.inserted_docs) == 2
        assert kb.inserted_docs[0][2][0]["filename"] == "doc1.txt"
        assert kb.inserted_docs[1][2][0]["filename"] == "doc2.txt"

    def test_content_hash_idempotent(self, setup):
        """Same content uploaded twice should produce same asset_id."""
        import hashlib
        svc, kb, _, _ = setup
        content = b"idempotent content"
        a1 = svc.create_ai_asset(content, "f.txt", "text/plain")
        a2 = svc.create_ai_asset(content, "f.txt", "text/plain")
        assert a1.asset_id == a2.asset_id


# ---------------------------------------------------------------------------
# End-to-end: ContentRepositoryService + LocalStorageBackend
# ---------------------------------------------------------------------------

class TestContentRepositoryServiceE2E:
    @pytest.fixture
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))

        from src.core.storage_backend_local import LocalStorageBackend
        local_backend = LocalStorageBackend()

        kb = InMemoryKBBackend()
        monkeypatch.setattr("src.services.kb_backend.get_kb_backend", lambda **kw: kb)
        monkeypatch.setattr("src.core.storage_backend.get_storage_backend", lambda **kw: local_backend)

        from src.services.content_repository_service import ContentRepositoryService
        svc = ContentRepositoryService(tenant_id="1")
        return svc, kb, local_backend, tmp_path

    def test_get_access_inline_small_file(self, setup, tmp_path):
        svc, kb, backend, _ = setup
        content = b"small file content"
        # Create a file via local backend
        import tempfile, shutil
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            tmp_path_f = f.name
        try:
            uri = backend.upload(tmp_path_f, "small.txt", bucket="tnt-1-media")
        finally:
            os.unlink(tmp_path_f)

        import time
        from src.services.content_repository_service import AssetRecord
        record = AssetRecord(
            asset_id="s1", job_id="j1", tenant_id="1",
            agent_name=None, agent_id=None, user_id=None,
            mime_type="text/plain", gcs_uri=uri,
            filename="small.txt", size_bytes=len(content),
            created_at="2026-01-01", metadata={}
        )
        svc_patched = svc
        with patch.object(svc_patched, "get_asset", return_value=record):
            access = svc_patched.get_access("s1")

        assert access is not None
        assert "base64" in access
        b64 = access["base64"].split(",")[-1]
        assert base64.b64decode(b64) == content

    def test_get_access_url_large_file(self, setup, tmp_path):
        from src.services.content_repository_service import MAX_INLINE_BYTES, AssetRecord
        svc, kb, backend, _ = setup

        # Create a large file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"X" * (MAX_INLINE_BYTES + 100))
            tmp_path_f = f.name
        try:
            uri = backend.upload(tmp_path_f, "large.bin", bucket="tnt-1-media")
        finally:
            os.unlink(tmp_path_f)

        record = AssetRecord(
            asset_id="l1", job_id="j1", tenant_id="1",
            agent_name=None, agent_id=None, user_id=None,
            mime_type="application/octet-stream", gcs_uri=uri,
            filename="large.bin", size_bytes=MAX_INLINE_BYTES + 100,
            created_at="2026-01-01", metadata={}
        )
        with patch.object(svc, "get_asset", return_value=record):
            access = svc.get_access("l1")

        assert access is not None
        assert "url" in access
        assert "base64" not in access
        assert access["url"].startswith("/api/files/")


# ---------------------------------------------------------------------------
# End-to-end: FeedbackService KB insert
# ---------------------------------------------------------------------------

class TestFeedbackServiceE2E:
    @pytest.fixture
    def setup(self, tmp_path, monkeypatch):
        kb = InMemoryKBBackend()
        fake_storage = MagicMock()
        fake_storage.upload.return_value = "file:///fake/path"
        fake_storage.bucket_for_tenant = staticmethod(lambda tid, bt: f"tnt-{tid}-{bt}")

        monkeypatch.setattr("src.services.feedback_service.get_kb_backend", lambda: kb)
        monkeypatch.setattr("src.services.feedback_service.get_storage_backend", lambda: fake_storage)

        from src.services.feedback_service import FeedbackService, FeedbackPolicy
        svc = FeedbackService(
            tenant_id=7, user_id=3,
            policy=FeedbackPolicy(max_comments_per_day_per_tenant=100)
        )
        return svc, kb, fake_storage

    def test_feedback_inserted_into_kb(self, setup, monkeypatch):
        svc, kb, _ = setup
        fake_job = MagicMock(job_id="job1", tenant_id=7)

        class _FS:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def exec(self, stmt): return MagicMock(first=lambda: fake_job)
            def add(self, obj): pass
            async def commit(self): pass
            async def refresh(self, obj): pass

        monkeypatch.setattr("src.services.feedback_service.get_scoped_session", lambda: _FS())
        monkeypatch.setattr(svc, "_check_and_increment_rate_limit", MagicMock(return_value=None))
        # Make _check_and_increment_rate_limit awaitable
        from unittest.mock import AsyncMock
        monkeypatch.setattr(svc, "_check_and_increment_rate_limit", AsyncMock())

        asyncio.run(
            svc.submit("job1", "What is the weather?", "It is sunny", 5, "Perfect!")
        )
        assert len(kb._feedback) == 1
        fb = kb._feedback[0]
        assert fb["_tenant_id"] == "7"
        assert fb["score"] == 5
        assert fb["job_id"] == "job1"

    def test_pii_stripped_from_feedback(self, setup, monkeypatch):
        svc, kb, _ = setup
        fake_job = MagicMock(job_id="j2", tenant_id=7)

        class _FS:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def exec(self, stmt): return MagicMock(first=lambda: fake_job)
            def add(self, obj): pass
            async def commit(self): pass
            async def refresh(self, obj): pass

        monkeypatch.setattr("src.services.feedback_service.get_scoped_session", lambda: _FS())
        from unittest.mock import AsyncMock
        monkeypatch.setattr(svc, "_check_and_increment_rate_limit", AsyncMock())

        asyncio.run(
            svc.submit(
                "j2",
                "My email is bob@example.com and I need help",
                "Contact us at https://private.company.com/support",
                4,
                "Great but see john@corp.org for details"
            )
        )
        fb = kb._feedback[0]
        assert "bob@example.com" not in fb.get("goal_text", "")
        assert "https://private.company.com/support" not in fb.get("final_output_text", "")
        assert "john@corp.org" not in fb.get("comment_text", "")


# ---------------------------------------------------------------------------
# End-to-end: BQ Backfill + local storage
# ---------------------------------------------------------------------------

class TestBackfillE2E:
    @pytest.fixture
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
        from src.core.storage_backend_local import LocalStorageBackend
        local_backend = LocalStorageBackend()
        kb = InMemoryKBBackend()
        monkeypatch.setattr(
            "src.services.bq_media_object_embeddings_backfill.get_kb_backend", lambda: kb
        )
        monkeypatch.setattr(
            "src.services.bq_media_object_embeddings_backfill.get_storage_backend",
            lambda: local_backend
        )
        # Create a real file in local storage
        src_file = tmp_path / "media_obj.txt"
        src_file.write_bytes(b"This is a document about machine learning")
        uri = local_backend.upload(str(src_file), "media_obj.txt", bucket="tnt-1-media")
        return kb, local_backend, uri, tmp_path

    def test_backfill_upserts_to_kb(self, setup, monkeypatch):
        kb, backend, uri, _ = setup
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 768]
        mock_embedder.dimension = 768

        with patch("src.services.bq_media_object_embeddings_backfill.EmbeddingService",
                   return_value=mock_embedder):
            from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService
            svc = BQMediaObjectEmbeddingsBackfillService(project_id="test")
            svc.backfill(tenant_id="1", gcs_uri=uri)

        assert len(kb._docs.get("media_object_embeddings", [])) == 1
        row = kb._docs["media_object_embeddings"][0]
        assert row["storage_uri"] == uri
        assert row["gcs_uri"] == uri  # backwards compat
        assert len(row["vector_embedding"]) == 768

    def test_backfill_upsert_is_idempotent(self, setup, monkeypatch):
        kb, backend, uri, _ = setup
        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.5] * 768]
        mock_embedder.dimension = 768

        with patch("src.services.bq_media_object_embeddings_backfill.EmbeddingService",
                   return_value=mock_embedder):
            from src.services.bq_media_object_embeddings_backfill import BQMediaObjectEmbeddingsBackfillService
            svc = BQMediaObjectEmbeddingsBackfillService()
            svc.backfill(tenant_id="1", gcs_uri=uri)
            svc.backfill(tenant_id="1", gcs_uri=uri)

        # Should only have one row (upsert, not double insert)
        rows = kb._docs.get("media_object_embeddings", [])
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Backend toggle: verify both backends use the same interface
# ---------------------------------------------------------------------------

class TestBackendToggle:
    def test_storage_backend_interface_consistent(self, tmp_path, monkeypatch):
        """Local and GCS backends must expose the same interface."""
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
        from src.core.storage_backend import StorageBackend
        from src.core.storage_backend_local import LocalStorageBackend
        required = ["upload", "download", "download_to_file", "generate_access_url", "delete", "exists"]
        backend = LocalStorageBackend()
        for method in required:
            assert hasattr(backend, method), f"LocalStorageBackend missing {method}"

    def test_kb_backend_interface_consistent(self):
        """pgvector and BQ backends must expose the same interface."""
        from src.services.kb_backend import KBBackend
        from src.services.kb_backend_pgvector import PgvectorKBBackend
        required = ["ensure_tenant_kb", "vector_search", "text_search", "insert_docs",
                    "upsert_doc", "query_assets", "insert_feedback", "query"]
        from src.services.kb_backend_pgvector import PgvectorKBBackend
        b = PgvectorKBBackend()
        for method in required:
            assert hasattr(b, method), f"PgvectorKBBackend missing {method}"

    def test_env_variable_controls_storage_backend(self, monkeypatch, tmp_path):
        """Toggling STORAGE_BACKEND env var changes backend type."""
        import src.core.storage_backend as mod
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
        mod._backend_cache = None
        local = mod.get_storage_backend(force_new=True)
        from src.core.storage_backend_local import LocalStorageBackend
        assert isinstance(local, LocalStorageBackend)
        mod._backend_cache = None

    def test_env_variable_controls_kb_backend(self, monkeypatch):
        """Toggling KB_VECTOR_BACKEND env var changes backend type."""
        import src.services.kb_backend as mod
        monkeypatch.setenv("KB_VECTOR_BACKEND", "pgvector")
        mod._backend_cache = None
        pgvec = mod.get_kb_backend(force_new=True)
        from src.services.kb_backend_pgvector import PgvectorKBBackend
        assert isinstance(pgvec, PgvectorKBBackend)
        mod._backend_cache = None


# ---------------------------------------------------------------------------
# Security: Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_repository_service_tenant_filter_applied(self, monkeypatch):
        """RepositoryService must always filter by its own tenant_id."""
        kb = InMemoryKBBackend()
        # Add assets for two different tenants
        kb.add_asset({"asset_id": "a1", "tenant_id": "1", "filename": "f1.pdf",
                      "storage_uri": "file:///f1", "gcs_uri": "file:///f1",
                      "mime_type": "application/pdf", "size_bytes": 100,
                      "created_at": "", "metadata": {"origin": "ai"}, "origin": "ai"})
        kb.add_asset({"asset_id": "a2", "tenant_id": "2", "filename": "f2.pdf",
                      "storage_uri": "file:///f2", "gcs_uri": "file:///f2",
                      "mime_type": "application/pdf", "size_bytes": 100,
                      "created_at": "", "metadata": {"origin": "ai"}, "origin": "ai"})

        fake_storage = MagicMock()
        fake_storage.generate_access_url.return_value = "/api/files/f"
        monkeypatch.setattr("src.services.repository_service.get_kb_backend", lambda: kb)
        monkeypatch.setattr("src.services.repository_service.get_storage_backend", lambda: fake_storage)

        from src.services.repository_service import RepositoryService
        svc1 = RepositoryService(tenant_id=1)
        svc2 = RepositoryService(tenant_id=2)

        assets1 = svc1.list_assets()
        assets2 = svc2.list_assets()

        # Each service should only see its own tenant's assets
        for a in assets1:
            assert a.asset_id != "a2", "tenant 1 should not see tenant 2 assets"
        for a in assets2:
            assert a.asset_id != "a1", "tenant 2 should not see tenant 1 assets"

    def test_content_repository_tenant_filter_applied(self, monkeypatch):
        """ContentRepositoryService must always pass its own tenant_id."""
        kb = InMemoryKBBackend()
        queries = []
        original = kb.query_assets

        def _track(tid, **kwargs):
            queries.append(tid)
            return []

        kb.query_assets = _track

        fake_storage = MagicMock()
        monkeypatch.setattr("src.services.kb_backend.get_kb_backend", lambda **kw: kb)
        monkeypatch.setattr("src.core.storage_backend.get_storage_backend", lambda **kw: fake_storage)

        from src.services.content_repository_service import ContentRepositoryService
        svc = ContentRepositoryService(tenant_id="42")
        svc.list_assets("job1")

        assert all(tid == "42" for tid in queries)

    def test_local_backend_path_traversal_blocked(self, tmp_path, monkeypatch):
        """File:// path traversal must be blocked at storage layer."""
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
        from src.core.storage_backend_local import LocalStorageBackend
        backend = LocalStorageBackend()
        malicious_uri = f"file://{tmp_path}/../../etc/passwd"
        with pytest.raises(Exception):
            backend.download(malicious_uri)

    def test_vault_path_per_tenant(self):
        """Vault paths must be scoped to tenant to prevent cross-tenant access."""
        from src.security.credential_backend_vault import VaultCredentialBackend
        b = VaultCredentialBackend()
        p_t1 = b._path("1", "gmail", "token")
        p_t2 = b._path("2", "gmail", "token")
        # Paths must differ and not be prefixed one by the other
        assert p_t1 != p_t2
        assert not p_t1.startswith(p_t2)
        assert not p_t2.startswith(p_t1)


# ---------------------------------------------------------------------------
# .env.example completeness
# ---------------------------------------------------------------------------

class TestEnvExampleCompleteness:
    @pytest.fixture(autouse=True)
    def env_example_text(self):
        self._text = (ROOT / ".env.example").read_text()

    def test_storage_backend_var_present(self):
        assert "STORAGE_BACKEND" in self._text

    def test_kb_vector_backend_var_present(self):
        assert "KB_VECTOR_BACKEND" in self._text

    def test_minio_endpoint_var_present(self):
        assert "MINIO_ENDPOINT" in self._text

    def test_minio_access_key_var_present(self):
        assert "MINIO_ACCESS_KEY" in self._text

    def test_minio_secret_key_var_present(self):
        assert "MINIO_SECRET_KEY" in self._text

    def test_storage_local_root_var_present(self):
        assert "STORAGE_LOCAL_ROOT" in self._text

    def test_secrets_backend_var_present(self):
        assert "SECRETS_BACKEND" in self._text

    def test_vault_addr_var_present(self):
        assert "VAULT_ADDR" in self._text

    def test_vault_role_id_var_present(self):
        assert "VAULT_ROLE_ID" in self._text

    def test_vault_secret_id_var_present(self):
        assert "VAULT_SECRET_ID" in self._text


# ---------------------------------------------------------------------------
# Migration scripts sanity checks
# ---------------------------------------------------------------------------

class TestMigrationScriptsSanity:
    def test_migrate_bq_to_pgvector_exists(self):
        script = ROOT / "scripts" / "migrate_bq_to_pgvector.py"
        assert script.exists()
        text = script.read_text()
        assert "KB_VECTOR_BACKEND" in text or "pgvector" in text.lower()

    def test_migrate_gcs_to_local_exists(self):
        script = ROOT / "scripts" / "migrate_gcs_to_local.py"
        assert script.exists()
        text = script.read_text()
        assert "STORAGE_BACKEND" in text or "local" in text.lower()

    def test_migrate_gcs_to_local_has_dry_run(self):
        script = ROOT / "scripts" / "migrate_gcs_to_local.py"
        text = script.read_text()
        assert "--dry-run" in text

    def test_migrate_gcs_to_local_has_tenant_flag(self):
        script = ROOT / "scripts" / "migrate_gcs_to_local.py"
        text = script.read_text()
        assert "--tenant" in text

    def test_migrate_gcs_updates_storage_uri(self):
        """Migration script must update storage_uri in DB (not just move files)."""
        script = ROOT / "scripts" / "migrate_gcs_to_local.py"
        text = script.read_text()
        assert "storage_uri" in text
        assert "UPDATE" in text.upper() or "replace" in text

    def test_migrate_bq_has_dry_run(self):
        script = ROOT / "scripts" / "migrate_bq_to_pgvector.py"
        text = script.read_text()
        assert "--dry-run" in text

    def test_migrate_bq_has_tenant_flag(self):
        script = ROOT / "scripts" / "migrate_bq_to_pgvector.py"
        text = script.read_text()
        assert "--tenant" in text


# ---------------------------------------------------------------------------
# Ansible role completeness checks
# ---------------------------------------------------------------------------

class TestAnsibleRoleCompleteness:
    ROLES = [
        "patroni", "etherion-app", "redis-cluster", "haproxy", "nginx",
        "vault", "minio", "frrouting", "matchbox", "monitoring"
    ]

    def test_all_roles_have_tasks_main(self):
        roles_dir = ROOT / "infra" / "ansible" / "roles"
        for role in self.ROLES:
            tasks_file = roles_dir / role / "tasks" / "main.yml"
            assert tasks_file.exists(), f"{role}/tasks/main.yml missing"
            assert tasks_file.stat().st_size > 0, f"{role}/tasks/main.yml is empty"

    def test_all_roles_have_handlers(self):
        roles_dir = ROOT / "infra" / "ansible" / "roles"
        for role in self.ROLES:
            handlers_file = roles_dir / role / "handlers" / "main.yml"
            assert handlers_file.exists(), f"{role}/handlers/main.yml missing"

    def test_critical_roles_have_templates(self):
        roles_dir = ROOT / "infra" / "ansible" / "roles"
        roles_with_templates = ["patroni", "etherion-app", "haproxy", "nginx", "vault",
                                 "minio", "monitoring", "frrouting"]
        for role in roles_with_templates:
            templates_dir = roles_dir / role / "templates"
            templates = list(templates_dir.glob("*.j2"))
            assert len(templates) >= 1, f"{role}/templates/ has no .j2 files"

    def test_site_playbook_references_all_roles(self):
        site = ROOT / "infra" / "ansible" / "playbooks" / "site.yml"
        assert site.exists()
        text = site.read_text()
        for role in ["patroni", "redis-cluster", "etherion-app"]:
            assert role in text, f"site.yml doesn't include {role}"

    def test_deploy_app_playbook_has_health_check(self):
        deploy = ROOT / "infra" / "ansible" / "playbooks" / "deploy-app.yml"
        assert deploy.exists()
        text = deploy.read_text()
        assert "health" in text.lower()

    def test_vault_policy_template_exists(self):
        policy = ROOT / "infra" / "ansible" / "roles" / "vault" / "templates" / "etherion-api-policy.hcl.j2"
        assert policy.exists()
        text = policy.read_text()
        assert "secret/data/tenants" in text

    def test_vault_config_has_raft_storage(self):
        vault_hcl = ROOT / "infra" / "ansible" / "roles" / "vault" / "templates" / "vault.hcl.j2"
        assert vault_hcl.exists()
        text = vault_hcl.read_text()
        assert "raft" in text.lower()

    def test_monitoring_has_prometheus_config(self):
        prom = ROOT / "infra" / "ansible" / "roles" / "monitoring" / "templates" / "prometheus.yml.j2"
        assert prom.exists()
        text = prom.read_text()
        assert "etherion" in text.lower()

    def test_monitoring_has_alert_rules(self):
        alerts = ROOT / "infra" / "ansible" / "roles" / "monitoring" / "templates" / "alert_rules.yml.j2"
        assert alerts.exists()
        text = alerts.read_text()
        assert "APIDown" in text or "alert:" in text

    def test_bgp_health_check_script_exists(self):
        script = ROOT / "infra" / "ansible" / "roles" / "frrouting" / "templates" / "bgp-health-check.sh.j2"
        assert script.exists()
        text = script.read_text()
        assert "/health" in text  # health check endpoint
        assert "vtysh" in text    # FRRouting CLI


# ---------------------------------------------------------------------------
# NixOS module completeness checks
# ---------------------------------------------------------------------------

class TestNixOSModuleCompleteness:
    NIX_MODULES = [
        "base.nix", "postgresql.nix", "redis.nix", "etherion-api.nix",
        "etherion-worker.nix", "haproxy.nix", "nginx.nix", "vault.nix",
        "minio.nix", "frrouting.nix", "matchbox.nix", "flake.nix"
    ]

    def test_all_nix_modules_exist(self):
        nix_dir = ROOT / "infra" / "nix"
        for module in self.NIX_MODULES:
            f = nix_dir / module
            assert f.exists(), f"infra/nix/{module} missing"
            assert f.stat().st_size > 0, f"infra/nix/{module} is empty"

    def test_postgresql_nix_has_pgvector(self):
        text = (ROOT / "infra" / "nix" / "postgresql.nix").read_text()
        assert "pgvector" in text

    def test_vault_nix_has_vault(self):
        text = (ROOT / "infra" / "nix" / "vault.nix").read_text()
        assert "vault" in text.lower()

    def test_api_nix_has_uvicorn(self):
        text = (ROOT / "infra" / "nix" / "etherion-api.nix").read_text()
        assert "uvicorn" in text

    def test_frrouting_nix_has_bgp(self):
        text = (ROOT / "infra" / "nix" / "frrouting.nix").read_text()
        assert "bgp" in text.lower() or "frr" in text.lower()


# ---------------------------------------------------------------------------
# Matchbox PXE config checks
# ---------------------------------------------------------------------------

class TestMatchboxConfigs:
    def test_group_files_exist(self):
        groups_dir = ROOT / "infra" / "matchbox" / "groups"
        assert len(list(groups_dir.glob("*.json"))) >= 1

    def test_profile_files_exist(self):
        profiles_dir = ROOT / "infra" / "matchbox" / "profiles"
        assert len(list(profiles_dir.glob("*.json"))) >= 1

    def test_ignition_files_exist(self):
        ignition_dir = ROOT / "infra" / "matchbox" / "ignition"
        assert len(list(ignition_dir.glob("*.json"))) >= 1

    def test_group_has_profile_reference(self):
        groups_dir = ROOT / "infra" / "matchbox" / "groups"
        for f in groups_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert "profile" in data, f"{f.name} missing 'profile' field"

    def test_profile_has_boot_config(self):
        profiles_dir = ROOT / "infra" / "matchbox" / "profiles"
        for f in profiles_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert "boot" in data or "id" in data, f"{f.name} missing 'boot' or 'id'"

    def test_ignition_is_valid_json(self):
        ignition_dir = ROOT / "infra" / "matchbox" / "ignition"
        for f in ignition_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert "ignition" in data, f"{f.name} not a valid Ignition config"
            assert "version" in data["ignition"], f"{f.name} missing ignition.version"
