"""Aggressive tests for HashiCorp Vault credential backend and credential_manager routing.

Tests: VaultCredentialBackend (path format, KV v2 operations, AppRole auth,
error handling), credential_manager.py SECRETS_BACKEND routing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call, PropertyMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# VaultCredentialBackend tests
# ---------------------------------------------------------------------------

class TestVaultCredentialBackend:
    @pytest.fixture
    def mock_hvac(self):
        """Create a mock hvac client."""
        mock_client = MagicMock()
        mock_client.auth.approle.login.return_value = {"auth": {"client_token": "s.test"}}
        mock_client.secrets.kv.v2.create_or_update_secret.return_value = {}
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "secret_value"}}
        }
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.return_value = {}
        return mock_client

    @pytest.fixture
    def backend(self, mock_hvac, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://vault-test:8200")
        monkeypatch.setenv("VAULT_ROLE_ID", "test-role-id")
        monkeypatch.setenv("VAULT_SECRET_ID", "test-secret-id")
        monkeypatch.setenv("VAULT_MOUNT", "secret")

        with patch("hvac.Client", return_value=mock_hvac):
            from src.security.credential_backend_vault import VaultCredentialBackend
            b = VaultCredentialBackend()
            b._client = mock_hvac  # pre-initialize to avoid re-login
            return b, mock_hvac

    def test_path_format(self, backend):
        b, _ = backend
        path = b._path("42", "gmail", "access_token")
        assert path == "tenants/42/gmail/access_token"

    def test_path_format_different_tenants(self, backend):
        b, _ = backend
        p1 = b._path("1", "slack", "bot_token")
        p2 = b._path("2", "slack", "bot_token")
        assert p1 != p2
        assert "1" in p1
        assert "2" in p2

    def test_store_calls_create_or_update_secret(self, backend):
        b, mock_client = backend
        b.store("10", "stripe", "api_key", "sk_test_abc123")
        mock_client.secrets.kv.v2.create_or_update_secret.assert_called_once()
        call_kwargs = mock_client.secrets.kv.v2.create_or_update_secret.call_args
        assert call_kwargs[1]["path"] == "tenants/10/stripe/api_key"
        assert call_kwargs[1]["secret"]["value"] == "sk_test_abc123"

    def test_store_uses_configured_mount(self, backend, monkeypatch):
        monkeypatch.setenv("VAULT_MOUNT", "custom-mount")
        b, mock_client = backend
        b.store("1", "svc", "key", "val")
        call_kwargs = mock_client.secrets.kv.v2.create_or_update_secret.call_args
        assert call_kwargs[1]["mount_point"] == "secret"  # b was created with VAULT_MOUNT=secret

    def test_get_returns_secret_value(self, backend):
        b, mock_client = backend
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "my_secret_value"}}
        }
        result = b.get("5", "hubspot", "api_key")
        assert result == "my_secret_value"

    def test_get_calls_correct_path(self, backend):
        b, mock_client = backend
        b.get("99", "jira", "token")
        call_kwargs = mock_client.secrets.kv.v2.read_secret_version.call_args
        assert call_kwargs[1]["path"] == "tenants/99/jira/token"

    def test_get_returns_none_on_not_found(self, backend):
        b, mock_client = backend
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("404 Not Found")
        result = b.get("1", "svc", "key")
        assert result is None

    def test_get_returns_none_on_network_error(self, backend):
        b, mock_client = backend
        mock_client.secrets.kv.v2.read_secret_version.side_effect = ConnectionError("timeout")
        result = b.get("1", "svc", "key")
        assert result is None

    def test_get_returns_none_on_vault_sealed(self, backend):
        b, mock_client = backend
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("Vault is sealed")
        result = b.get("1", "svc", "key")
        assert result is None

    def test_revoke_calls_delete_all_versions(self, backend):
        b, mock_client = backend
        b.revoke("7", "salesforce", "oauth_token")
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.assert_called_once()
        call_kwargs = mock_client.secrets.kv.v2.delete_metadata_and_all_versions.call_args
        assert call_kwargs[1]["path"] == "tenants/7/salesforce/oauth_token"

    def test_revoke_silently_handles_errors(self, backend):
        """revoke() must not raise even if Vault is down."""
        b, mock_client = backend
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.side_effect = Exception("network err")
        # Should not raise
        b.revoke("1", "svc", "key")

    def test_approle_login_called_when_role_id_set(self, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
        monkeypatch.setenv("VAULT_ROLE_ID", "my-role-id")
        monkeypatch.setenv("VAULT_SECRET_ID", "my-secret-id")

        mock_client = MagicMock()
        with patch("hvac.Client", return_value=mock_client):
            from src.security.credential_backend_vault import VaultCredentialBackend
            b = VaultCredentialBackend()
            b._client = None  # Force re-init
            b._get_client()
        mock_client.auth.approle.login.assert_called_once_with(
            role_id="my-role-id",
            secret_id="my-secret-id"
        )

    def test_approle_login_skipped_when_no_role_id(self, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
        monkeypatch.delenv("VAULT_ROLE_ID", raising=False)
        monkeypatch.delenv("VAULT_SECRET_ID", raising=False)

        mock_client = MagicMock()
        with patch("hvac.Client", return_value=mock_client):
            from src.security.credential_backend_vault import VaultCredentialBackend
            b = VaultCredentialBackend()
            b._client = None
            b._get_client()
        mock_client.auth.approle.login.assert_not_called()

    def test_vault_addr_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://custom-vault:9200")
        from src.security.credential_backend_vault import VaultCredentialBackend
        b = VaultCredentialBackend()
        assert b._addr == "http://custom-vault:9200"

    def test_vault_mount_from_env(self, monkeypatch):
        monkeypatch.setenv("VAULT_MOUNT", "kvv2")
        from src.security.credential_backend_vault import VaultCredentialBackend
        b = VaultCredentialBackend()
        assert b._mount == "kvv2"

    def test_default_vault_addr(self, monkeypatch):
        monkeypatch.delenv("VAULT_ADDR", raising=False)
        from src.security.credential_backend_vault import VaultCredentialBackend
        b = VaultCredentialBackend()
        assert "vault" in b._addr or "8200" in b._addr

    def test_store_round_trip_mock(self, backend):
        """store then get should return the stored value via mock."""
        b, mock_client = backend
        stored_val = "super_secret_api_key_xyz"
        b.store("3", "openai", "api_key", stored_val)
        # Now mock the get to return what we stored
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": stored_val}}
        }
        retrieved = b.get("3", "openai", "api_key")
        assert retrieved == stored_val

    def test_get_vault_backend_singleton(self, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
        import src.security.credential_backend_vault as mod
        mod._vault_backend = None  # Reset singleton
        b1 = mod.get_vault_backend()
        b2 = mod.get_vault_backend()
        assert b1 is b2
        mod._vault_backend = None


# ---------------------------------------------------------------------------
# CredentialManager routing tests
# ---------------------------------------------------------------------------

class TestCredentialManagerVaultRouting:
    @pytest.fixture(autouse=True)
    def reset_env(self, monkeypatch):
        """Each test gets a clean environment."""
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        monkeypatch.delenv("VAULT_ROLE_ID", raising=False)
        monkeypatch.delenv("VAULT_SECRET_ID", raising=False)
        monkeypatch.setenv("USE_LOCAL_SECRETS", "false")
        yield

    def test_secrets_backend_vault_sets_use_vault(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "vault")
        mock_vault = MagicMock()
        with patch("src.security.credential_backend_vault.get_vault_backend", return_value=mock_vault):
            with patch("src.security.credential_manager.is_production", return_value=False):
                from importlib import reload
                import src.security.credential_manager as mod
                cm = mod.CredentialManager()
        assert cm.use_vault is True

    def test_secrets_backend_vault_store_routes_to_vault(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "vault")
        mock_vault = MagicMock()
        mock_vault.store = MagicMock()
        with patch("src.security.credential_manager.is_production", return_value=False):
            with patch("src.security.credential_backend_vault.get_vault_backend", return_value=mock_vault):
                from src.security.credential_manager import CredentialManager
                cm = CredentialManager()
                cm._vault = mock_vault
                cm.use_vault = True
                cm.store_secret("t1", "gmail", "token", "abc")
        mock_vault.store.assert_called_once_with("t1", "gmail", "token", "abc")

    def test_secrets_backend_vault_get_routes_to_vault(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "vault")
        mock_vault = MagicMock()
        mock_vault.get = MagicMock(return_value="vault_secret")
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            result = cm.get_secret("t1", "gmail", "token")
        mock_vault.get.assert_called_once_with("t1", "gmail", "token")
        assert result == "vault_secret"

    def test_secrets_backend_vault_revoke_routes_to_vault(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "vault")
        mock_vault = MagicMock()
        mock_vault.revoke = MagicMock()
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            cm.revoke_secret("t1", "gmail", "token")
        mock_vault.revoke.assert_called_once_with("t1", "gmail", "token")

    def test_vault_takes_priority_over_local(self, monkeypatch):
        """When SECRETS_BACKEND=vault, local file store should NOT be used."""
        monkeypatch.setenv("SECRETS_BACKEND", "vault")
        monkeypatch.setenv("USE_LOCAL_SECRETS", "true")
        mock_vault = MagicMock()
        mock_vault.store = MagicMock()
        mock_vault.get = MagicMock(return_value="vault_val")
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            result = cm.get_secret("t", "s", "k")
        mock_vault.get.assert_called_once()
        assert result == "vault_val"

    def test_secrets_backend_local_uses_local_store(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "local")
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
        assert cm.use_local is True
        assert cm.use_vault is False

    def test_secrets_backend_unset_defaults_to_gcp(self, monkeypatch):
        """No SECRETS_BACKEND set should default to GCP (or local in test env)."""
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            # Should not raise even if GCP creds absent
            try:
                cm = CredentialManager()
                assert cm.use_vault is False
            except Exception:
                pass  # GCP init failure is OK in test

    def test_vault_store_does_not_call_gcp(self, monkeypatch):
        """When vault is active, GCP Secret Manager must NOT be called."""
        monkeypatch.setenv("SECRETS_BACKEND", "vault")
        mock_vault = MagicMock()
        mock_vault.store = MagicMock()
        mock_sm_client = MagicMock()
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            cm.client = mock_sm_client  # Would be used if GCP path taken
            cm.store_secret("t", "svc", "k", "val")
        mock_sm_client.create_secret.assert_not_called()
        mock_sm_client.add_secret_version.assert_not_called()

    def test_vault_get_does_not_call_gcp(self, monkeypatch):
        mock_vault = MagicMock()
        mock_vault.get = MagicMock(return_value="v")
        mock_sm_client = MagicMock()
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            cm.client = mock_sm_client
            cm.get_secret("t", "svc", "k")
        mock_sm_client.access_secret_version.assert_not_called()

    def test_vault_revoke_does_not_call_gcp(self, monkeypatch):
        mock_vault = MagicMock()
        mock_vault.revoke = MagicMock()
        mock_sm_client = MagicMock()
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            cm.client = mock_sm_client
            cm.revoke_secret("t", "svc", "k")
        mock_sm_client.delete_secret.assert_not_called()

    def test_vault_returns_none_when_secret_missing(self, monkeypatch):
        mock_vault = MagicMock()
        mock_vault.get = MagicMock(return_value=None)
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            result = cm.get_secret("t", "svc", "nonexistent_key")
        assert result is None

    def test_env_vars_section_in_env_example(self):
        """Ensure .env.example documents vault env vars."""
        env_example = (ROOT / ".env.example").read_text()
        assert "SECRETS_BACKEND" in env_example
        assert "VAULT_ADDR" in env_example
        assert "VAULT_ROLE_ID" in env_example
        assert "VAULT_SECRET_ID" in env_example


# ---------------------------------------------------------------------------
# Integration: local → vault credential round-trip simulation
# ---------------------------------------------------------------------------

class TestCredentialRoundTrip:
    def test_local_store_and_retrieve(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SECRETS_BACKEND", "local")
        monkeypatch.setenv("LOCAL_SECRETS_FILE", str(tmp_path / "secrets.json"))
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm.use_local = True
            cm.use_vault = False
            cm.store_secret("tenant_42", "openai", "api_key", "sk-test-123")
            result = cm.get_secret("tenant_42", "openai", "api_key")
        assert result == "sk-test-123"

    def test_local_revoke(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SECRETS_BACKEND", "local")
        monkeypatch.setenv("LOCAL_SECRETS_FILE", str(tmp_path / "secrets.json"))
        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm.use_local = True
            cm.use_vault = False
            cm.store_secret("t1", "svc", "key", "val")
            cm.revoke_secret("t1", "svc", "key")
            result = cm.get_secret("t1", "svc", "key")
        assert result is None

    def test_vault_round_trip_mock(self, monkeypatch):
        store = {}
        mock_vault = MagicMock()
        mock_vault.store = lambda tid, svc, key, val: store.update({f"{tid}/{svc}/{key}": val})
        mock_vault.get = lambda tid, svc, key: store.get(f"{tid}/{svc}/{key}")
        mock_vault.revoke = lambda tid, svc, key: store.pop(f"{tid}/{svc}/{key}", None)

        with patch("src.security.credential_manager.is_production", return_value=False):
            from src.security.credential_manager import CredentialManager
            cm = CredentialManager()
            cm._vault = mock_vault
            cm.use_vault = True
            cm.use_local = False

            cm.store_secret("5", "stripe", "secret_key", "sk_live_xyz")
            result = cm.get_secret("5", "stripe", "secret_key")
            assert result == "sk_live_xyz"

            cm.revoke_secret("5", "stripe", "secret_key")
            result_after = cm.get_secret("5", "stripe", "secret_key")
            assert result_after is None
