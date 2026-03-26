"""HashiCorp Vault credential backend."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VAULT_MOUNT = os.getenv("VAULT_MOUNT", "secret")


class VaultCredentialBackend:
    """KV v2 credential backend backed by HashiCorp Vault."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        import hvac

        addr = os.getenv("VAULT_ADDR", "http://localhost:8200")
        client = hvac.Client(url=addr)

        # Token auth (dev mode or explicit token)
        token = os.getenv("VAULT_TOKEN")
        if token:
            client.token = token
        else:
            # AppRole auth
            role_id = os.getenv("VAULT_ROLE_ID")
            secret_id = os.getenv("VAULT_SECRET_ID")
            if not role_id or not secret_id:
                raise ValueError("VAULT_ROLE_ID and VAULT_SECRET_ID must be set when VAULT_TOKEN is not provided.")
            client.auth.approle.login(role_id=role_id, secret_id=secret_id)

        if not client.is_authenticated():
            raise RuntimeError("Vault authentication failed.")

        self._client = client
        return client

    def write(self, path: str, data: Dict[str, Any]) -> None:
        self._get_client().secrets.kv.v2.create_or_update_secret(
            path=path, secret=data, mount_point=_VAULT_MOUNT
        )

    def read(self, path: str) -> Dict[str, Any]:
        response = self._get_client().secrets.kv.v2.read_secret_version(
            path=path, mount_point=_VAULT_MOUNT
        )
        return response["data"]["data"]

    def delete(self, path: str) -> None:
        self._get_client().secrets.kv.v2.delete_metadata_and_all_versions(
            path=path, mount_point=_VAULT_MOUNT
        )

    def list_paths(self, prefix: str) -> List[str]:
        try:
            response = self._get_client().secrets.kv.v2.list_secrets(
                path=prefix, mount_point=_VAULT_MOUNT
            )
            return response["data"].get("keys", [])
        except Exception:
            return []

    def health_check(self) -> bool:
        try:
            return self._get_client().sys.is_initialized()
        except Exception:
            return False
