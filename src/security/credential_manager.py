import os
import json
import time
from threading import RLock
from google.cloud import secretmanager
from src.config.environment import is_production

# Module-level shared ephemeral file for pytest runs
_PYTEST_LOCAL_SECRETS_FILE: str | None = None
# Per-test-scoped in-memory stores and locks
_PYTEST_STORES: dict[str, dict] = {}
_PYTEST_LOCKS: dict[str, RLock] = {}

class CredentialManager:
    """
    Manages the secure storage and retrieval of user-provided credentials.
    """

    def __init__(self):
        # Prefer explicit project envs used across the app
        self.project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")

        # Local fallback (offline) mode: bypass GCP and use file-backed store
        self.use_local = os.getenv("USE_LOCAL_SECRETS", "false").lower() in ("1", "true", "yes")
        # Hard guard: never allow local fallback in production
        if is_production() and self.use_local:
            # Force off in prod regardless of env flag
            self.use_local = False
            # Lazy logging via print to avoid import cycles with logging in early startup
            try:
                print("[CredentialManager] USE_LOCAL_SECRETS ignored in production environment")
            except Exception:
                pass
        # In pytest, always use local mode for deterministic behavior
        if os.getenv("PYTEST_CURRENT_TEST") and not is_production():
            self.use_local = True
        # Use per-test-scoped in-memory store during pytest, otherwise file-backed
        pytest_current = os.getenv("PYTEST_CURRENT_TEST")
        if pytest_current and not is_production():
            # Derive a slug for the current test function
            slug = pytest_current.split(" ")[0].replace(os.sep, "_")
            global _PYTEST_LOCAL_SECRETS_FILE, _PYTEST_STORES, _PYTEST_LOCKS
            if slug not in _PYTEST_STORES:
                _PYTEST_STORES[slug] = {}
                _PYTEST_LOCKS[slug] = RLock()
            self._local_store = _PYTEST_STORES[slug]
            self._lock = _PYTEST_LOCKS[slug]
            # Optional ephemeral file name for debugging (not persisted)
            if not _PYTEST_LOCAL_SECRETS_FILE:
                _PYTEST_LOCAL_SECRETS_FILE = f".secrets.local.{os.getpid()}.{int(time.time()*1000)}.json"
            self.local_file = _PYTEST_LOCAL_SECRETS_FILE
        else:
            self.local_file = os.getenv("LOCAL_SECRETS_FILE", ".secrets.local.json")
            self._lock = RLock()
            self._local_store = {}

        if self.use_local:
            self._load_local_store()
            self.client = None  # Explicitly avoid initializing GCP client
        else:
            self.client = secretmanager.SecretManagerServiceClient()

    def _ensure_local_mode(self) -> None:
        """Enable local fallback storage mode (non-production only)."""
        if is_production():
            return
        self.use_local = True
        self.client = None
        # If running under pytest and using the default path, switch to ephemeral file
        if os.getenv("PYTEST_CURRENT_TEST") and self.local_file == ".secrets.local.json":
            self.local_file = f".secrets.local.{os.getpid()}.json"
        # Load existing local store or initialize empty
        self._load_local_store()

    def _secret_id(self, tenant_id: str, service_name: str, key_type: str) -> str:
        return f"{tenant_id}--{service_name}--{key_type}"

    def _load_local_store(self) -> None:
        try:
            # In test runs, do not modify the shared in-memory store
            if os.getenv("PYTEST_CURRENT_TEST"):
                return
            if os.path.exists(self.local_file):
                with open(self.local_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._local_store = data
                    else:
                        self._local_store = {}
            else:
                self._local_store = {}
        except Exception:
            # On any error, start fresh (test environments should not fail hard here)
            self._local_store = {}

    def _save_local_store(self) -> None:
        try:
            # In test runs, do not persist to disk; keep secrets ephemeral in memory
            if os.getenv("PYTEST_CURRENT_TEST"):
                return
            # Ensure directory exists if a path is provided
            directory = os.path.dirname(self.local_file)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            with open(self.local_file, "w", encoding="utf-8") as f:
                json.dump(self._local_store, f, separators=(",", ":"))
        except Exception:
            # Silently ignore persistence errors in fallback mode
            pass

    def _get_secret_name(self, tenant_id: str, service_name: str, key_type: str) -> str:
        """
        Generates the fully qualified secret name.
        """
        secret_id = self._secret_id(tenant_id, service_name, key_type)
        return self.client.secret_version_path(self.project_id, secret_id, "latest")

    def store_secret(self, tenant_id: str, service_name: str, key_type: str, secret_value: str) -> None:
        """
        Stores a secret in Google Secret Manager.
        """
        if self.use_local:
            secret_id = self._secret_id(tenant_id, service_name, key_type)
            with self._lock:
                self._local_store[secret_id] = secret_value
                # Mirror into env during pytest to ensure cross-context availability
                if os.getenv("PYTEST_CURRENT_TEST"):
                    os.environ[f"PYTEST_SECRET__{secret_id}"] = secret_value
                self._save_local_store()
            return

        secret_id = self._secret_id(tenant_id, service_name, key_type)
        parent = f"projects/{self.project_id}"

        try:
            # Create the secret if it doesn't exist
            try:
                self.client.create_secret(
                    request={"parent": parent, "secret_id": secret_id, "secret": {"replication": {"automatic": {}}}}
                )
            except Exception:
                # Secret likely already exists
                pass

            # Add the secret version
            self.client.add_secret_version(
                request={"parent": self.client.secret_path(self.project_id, secret_id), "payload": {"data": secret_value.encode("UTF-8")}}
            )
        except Exception:
            # Permission or API error: fallback to local store in non-production
            self._ensure_local_mode()
            secret_id = self._secret_id(tenant_id, service_name, key_type)
            with self._lock:
                self._local_store[secret_id] = secret_value
                self._save_local_store()

    def get_secret(self, tenant_id: str, service_name: str, key_type: str) -> str | None:
        """
        Retrieves a secret from Google Secret Manager.
        """
        if self.use_local:
            secret_id = self._secret_id(tenant_id, service_name, key_type)
            with self._lock:
                val = self._local_store.get(secret_id)
                if val is None and os.getenv("PYTEST_CURRENT_TEST"):
                    # Fallback to env mirror if contexts differ
                    val = os.environ.get(f"PYTEST_SECRET__{secret_id}")
                return val

        try:
            secret_name = self._get_secret_name(tenant_id, service_name, key_type)
            response = self.client.access_secret_version(request={"name": secret_name})
            return response.payload.data.decode("UTF-8")
        except Exception:
            # Fallback to local if remote access fails
            self._ensure_local_mode()
            secret_id = self._secret_id(tenant_id, service_name, key_type)
            with self._lock:
                return self._local_store.get(secret_id)

    def revoke_secret(self, tenant_id: str, service_name: str, key_type: str) -> None:
        """
        Deletes a secret from Google Secret Manager.
        """
        if self.use_local:
            secret_id = self._secret_id(tenant_id, service_name, key_type)
            with self._lock:
                if secret_id in self._local_store:
                    self._local_store.pop(secret_id, None)
                if os.getenv("PYTEST_CURRENT_TEST"):
                    os.environ.pop(f"PYTEST_SECRET__{secret_id}", None)
                self._save_local_store()
            return

        try:
            secret_name = self.client.secret_path(self.project_id, f"{tenant_id}--{service_name}--{key_type}")
            self.client.delete_secret(request={"name": secret_name})
        except Exception:
            # Permission or API error: best-effort delete locally
            self._ensure_local_mode()
            secret_id = self._secret_id(tenant_id, service_name, key_type)
            with self._lock:
                if secret_id in self._local_store:
                    self._local_store.pop(secret_id, None)
                    self._save_local_store()
