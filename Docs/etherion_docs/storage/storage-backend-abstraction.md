# Storage Backend Abstraction

## The Pattern

Etherion abstracts storage operations behind a `StorageBackend` interface. This abstraction serves three purposes: it allows multiple implementations to coexist, it makes testing trivial (inject a local backend), and it creates a clean boundary between storage concerns and business logic.

The interface defines seven methods that every storage system must implement:

**upload(bucket, key, data, content_type).** Takes a file-like object or bytes, writes it to storage under the given bucket and key, and returns a storage URI. The caller doesn't care whether this writes to MinIO, the local filesystem, or Google Cloud Storage—the method abstracts it away.

**download(bucket, key).** Fetches the object and returns raw bytes. The caller reads the bytes into memory and processes them. For very large files, this might seem inefficient, but in practice, Etherion artifacts are typically under 50 MB. If larger files become common, a streaming variant could be added.

**delete(bucket, key).** Removes the object. Should be idempotent—deleting a non-existent object is not an error. This is called during cleanup, expiry, and tenant removal.

**exists(bucket, key).** Returns a boolean without reading the object. Useful for guards and conditionals.

**list_keys(bucket, prefix).** Lists all keys under a given prefix. This is how the system discovers all artifacts for a job, all knowledge base documents for a tenant, or all stale files for cleanup. Returns a list of strings.

**get_url(bucket, key, expiry_seconds).** Generates a URL that the caller can give to a user or client. The URL may be a presigned S3 URL (MinIO, GCS), a file:// path (local), or a temporary redirect. The expiry parameter controls how long the URL is valid.

**health_check().** Returns True if the backend is healthy and reachable. Called by monitoring systems and startup checks.

```python
class StorageBackend(ABC):
    @abstractmethod
    def upload(self, bucket: str, key: str, data: BinaryIO,
               content_type: str = "application/octet-stream") -> str:
        """Upload data and return the object URI."""

    @abstractmethod
    def download(self, bucket: str, key: str) -> bytes:
        """Download and return object bytes."""

    @abstractmethod
    def delete(self, bucket: str, key: str) -> None:
        """Delete an object."""

    @abstractmethod
    def exists(self, bucket: str, key: str) -> bool:
        """Return True if the object exists."""

    @abstractmethod
    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        """List object keys under prefix."""

    @abstractmethod
    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        """Return a (possibly pre-signed) URL for the object."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the backend is reachable."""
```

## The Factory

At application startup, a single factory function is called to initialize the storage backend. The factory reads the `STORAGE_BACKEND` environment variable and instantiates the appropriate class. This is called once and the result is cached globally or injected into services.

```python
def get_storage_backend() -> StorageBackend:
    """Factory — reads STORAGE_BACKEND env var (local | minio | gcs). Default: minio."""
    backend = os.getenv("STORAGE_BACKEND", "minio").lower()
    if backend == "gcs":
        from .storage_backend_gcs import GCSStorageBackend
        return GCSStorageBackend()
    elif backend == "local":
        from .storage_backend_local import LocalStorageBackend
        return LocalStorageBackend()
    else:
        from .storage_backend_minio import MinIOStorageBackend
        return MinIOStorageBackend()
```

The factory defaults to MinIO, which is the production choice. Setting `STORAGE_BACKEND=local` switches to development mode. For users still on GCS, `STORAGE_BACKEND=gcs` is available, but new installations should not use it.

## MinIO Implementation

The MinIO backend speaks S3 API to a MinIO instance. It handles presigned URL generation, multipart uploads for large objects, and bucket creation on demand. It returns S3 URIs (`s3://bucket/key`) from upload, allowing persistent storage in PostgreSQL.

```python
class MinIOStorageBackend(StorageBackend):
    def upload(self, bucket: str, key: str, data: BinaryIO,
               content_type: str = "application/octet-stream") -> str:
        self._ensure_bucket(bucket)
        content = data.read() if hasattr(data, "read") else data
        self._client.put_object(bucket, key, io.BytesIO(content),
                                len(content), content_type=content_type)
        return f"s3://{bucket}/{key}"

    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        return self._client.presigned_get_object(bucket, key,
                                                 expires=timedelta(seconds=expiry_seconds))
```

## Local Filesystem Implementation

For development, the local backend stores everything in a directory on the developer's machine. It's fast, requires no external services, and files are human-inspectable. It returns `file://` URIs.

```python
class LocalStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self.root = Path(os.getenv("STORAGE_LOCAL_ROOT", "/tmp/etherion-storage"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, bucket: str, key: str) -> Path:
        p = self.root / bucket / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def upload(self, bucket: str, key: str, data: BinaryIO,
               content_type: str = "application/octet-stream") -> str:
        dest = self._path(bucket, key)
        content = data.read() if hasattr(data, "read") else data
        dest.write_bytes(content)
        return f"file://{dest}"

    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        return f"file://{self._path(bucket, key)}"
```

The local backend creates bucket directories automatically and organizes files hierarchically. The `file://` URLs are absolute paths, which work fine for server-side operations. For web clients, you'd need to proxy these through an HTTP endpoint or use the backend's download method instead.

## GCS Implementation (Legacy)

For users who deployed with Google Cloud Storage before the MinIO migration, the GCS backend is available as a bridge. It wraps the Google Cloud Storage Python client and generates signed URLs valid for the specified expiry.

```python
class GCSStorageBackend(StorageBackend):
    def upload(self, bucket: str, key: str, data: BinaryIO,
               content_type: str = "application/octet-stream") -> str:
        blob = self._bucket(bucket).blob(key)
        content = data.read() if hasattr(data, "read") else data
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{bucket}/{key}"

    def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
        blob = self._bucket(bucket).blob(key)
        return blob.generate_signed_url(expiration=timedelta(seconds=expiry_seconds),
                                        version="v4")
```

GCS is designed for users already operating in Google Cloud. It handles authentication via the `GOOGLE_CLOUD_PROJECT` environment variable and assumes the Pod or VM has GCP credentials mounted. New deployments should not use GCS; use MinIO instead for self-hosted independence.

## Usage in Business Logic

Business logic never directly instantiates a backend. Instead, services receive a backend as a dependency:

```python
from src.core.storage_backend import get_storage_backend

class ArtifactService:
    def __init__(self):
        self.storage = get_storage_backend()

    def store_job_output(self, job_id: str, output_bytes: bytes) -> str:
        key = f"job-outputs/{job_id}/result.json"
        uri = self.storage.upload("etherion-artifacts", key,
                                  io.BytesIO(output_bytes),
                                  content_type="application/json")
        # Store URI in PostgreSQL
        return uri

    def get_download_url(self, artifact_uri: str, expiry_hours: int = 24) -> str:
        # Parse S3/GCS/file URI to extract bucket and key
        parts = artifact_uri.split("/", 2)
        bucket, key = parts[1], parts[2]
        return self.storage.get_url(bucket, key, expiry_seconds=expiry_hours * 3600)
```

This pattern keeps storage concerns isolated. If the backend changes, the service logic doesn't. Tests can inject a mock or local backend. Code is testable and maintainable.

## URI Parsing

The storage system persists URIs, not bucket-key pairs, because URIs encode the backend type. An S3 URI (`s3://bucket/key`) is parsed differently than a GCS URI (`gs://bucket/key`) or a file URI (`file:///path`). When retrieving an object, parse the URI to determine the bucket and key, then call the backend. The factory pattern ensures the backend is available.

For production systems handling multiple backends simultaneously (e.g., during migration), a more sophisticated factory could inspect the URI scheme and instantiate the appropriate backend on-the-fly. For Etherion, a single backend is active at any time, so the global factory pattern works.
