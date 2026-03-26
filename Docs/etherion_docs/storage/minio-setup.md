# MinIO Setup and Configuration

## Deployment Overview

MinIO is deployed as a standalone service on your infrastructure, typically on the same private network as the Etherion backend. It exposes an S3-compatible API on port 9000 and a management console on port 9001. The backend connects to MinIO via the MinIO Python SDK, which handles authentication, object operations, and presigned URL generation.

Unlike cloud object storage where you authenticate via service accounts and project IDs, MinIO uses access keys—think of them as username and password for S3 API calls. These credentials allow the backend to upload, download, and delete objects. Users never authenticate directly to MinIO; they receive presigned URLs from the backend, which are time-limited, read-only links to specific objects.

## Configuration via Environment Variables

The MinIO backend reads configuration from six environment variables:

**MINIO_ENDPOINT.** The hostname and port where MinIO listens, e.g., `minio.internal:9000` or `10.0.0.5:9000`. The MinIO SDK expects `host:port` without a protocol prefix. If the endpoint includes `http://` or `https://`, the backend strips it automatically.

**MINIO_SECURE.** Set to `true` to connect to MinIO over HTTPS with certificate verification, or `false` for plain HTTP. In development, this is typically `false`. In production behind TLS termination, set it to `true`.

**MINIO_ACCESS_KEY.** The access key ID used for authentication. This is like an S3 access key. Default is `minioadmin` in development; change it in production.

**MINIO_SECRET_KEY.** The secret key corresponding to the access key. Default is `minioadmin` in development; generate a strong random value in production.

**MINIO_REGION.** The region identifier for the MinIO deployment, e.g., `us-east-1`. This is used for S3 API compatibility and signing requests. Default is `us-east-1`.

Here's an example configuration for production:

```bash
export STORAGE_BACKEND=minio
export MINIO_ENDPOINT=minio.etherion.internal:9000
export MINIO_SECURE=true
export MINIO_ACCESS_KEY=etherion-prod-key
export MINIO_SECRET_KEY=$(openssl rand -base64 32)
export MINIO_REGION=us-east-1
```

The backend initializes the MinIO client in its constructor. If MinIO is unreachable or credentials are invalid, the client will fail when the first operation is attempted, not at startup. This allows graceful degradation—the backend logs a warning, but startup continues. Health checks will fail, alerting operators to the problem.

```python
class MinIOStorageBackend(StorageBackend):
    def __init__(self) -> None:
        from minio import Minio

        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        # Strip http:// or https:// prefix — minio SDK takes host:port
        for scheme in ("https://", "http://"):
            if endpoint.startswith(scheme):
                endpoint = endpoint[len(scheme):]
                break

        secure = os.getenv("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
        self._client = Minio(
            endpoint,
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            region=os.getenv("MINIO_REGION", "us-east-1"),
            secure=secure,
        )
```

## Bucket Initialization

When a file is first uploaded to a bucket, MinIO checks whether the bucket exists. If not, it creates it. This lazy initialization means you don't need to pre-create buckets—they spring into existence on first use. However, in production, you may want to create buckets explicitly with versioning, lifecycle policies, or encryption enabled, then disable the ability to create new buckets to prevent accidental bucket proliferation.

```python
def _ensure_bucket(self, bucket: str) -> None:
    if not self._client.bucket_exists(bucket):
        self._client.make_bucket(bucket)

def upload(self, bucket: str, key: str, data: BinaryIO,
           content_type: str = "application/octet-stream") -> str:
    self._ensure_bucket(bucket)
    content = data.read() if hasattr(data, "read") else data
    self._client.put_object(bucket, key, io.BytesIO(content),
                            len(content), content_type=content_type)
    return f"s3://{bucket}/{key}"
```

The upload method returns an S3 URI (`s3://bucket/key`) for storage in PostgreSQL. When the backend needs to retrieve the object later, it parses this URI to extract the bucket and key.

## Presigned URL Generation

The most critical feature for user experience is presigned URLs. When a user wants to download a file or a client-side application needs to fetch an artifact, the backend generates a time-limited, cryptographically signed URL. The user or client can then fetch the URL directly from MinIO without needing credentials.

```python
def get_url(self, bucket: str, key: str, expiry_seconds: int = 3600) -> str:
    return self._client.presigned_get_object(bucket, key,
                                             expires=timedelta(seconds=expiry_seconds))
```

The expiry defaults to one hour. For short-lived artifacts or user downloads, this is reasonable. For long-term archive access, you might adjust it to 24 hours. The presigned URL includes a cryptographic signature derived from the object's key, bucket name, and expiry time, computed with the secret key. MinIO validates the signature when the URL is accessed, ensuring that no one can forge a URL to access an object they shouldn't.

An example presigned URL looks like:

```
http://minio.internal:9000/etherion-artifacts/job-456/output.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...&X-Amz-Signature=...
```

The query parameters are the S3 signature. The URL is valid for exactly one hour (or whatever expiry is set), then becomes invalid.

## Operations and Monitoring

Upload stores the object with a specified content type, which MinIO tracks as metadata. This allows the browser to render PDFs correctly or download CSVs with the right extension. Download retrieves the bytes and closes the connection cleanly. Delete removes the object; if it doesn't exist, MinIO returns a no-op success (important for idempotent cleanup). Exists checks if an object is present. List_keys retrieves all keys under a prefix, useful for scanning for stale files or auditing contents.

Health check is the canary—if it fails, storage is down. The implementation simply lists buckets:

```python
def health_check(self) -> bool:
    try:
        self._client.list_buckets()
        return True
    except Exception:
        return False
```

If this fails, the system should return an error to health check endpoints, preventing new requests from being routed to an unhealthy backend. In Kubernetes, this drives pod readiness probes. In systemd, this can drive service restart policies.

## Performance Considerations

MinIO is designed for throughput. Multi-part uploads for large objects, concurrent downloads, and erasure coding across multiple disks or nodes are all supported. For typical Etherion deployments, a single MinIO node is sufficient. As scale grows, add more nodes and enable erasure coding for durability.

Presigned URLs are generated on-demand; there's no caching layer. For high concurrency (thousands of users downloading at once), generate URLs in batches if possible. For streaming large objects, consider enabling range requests so clients can resume interrupted downloads.
